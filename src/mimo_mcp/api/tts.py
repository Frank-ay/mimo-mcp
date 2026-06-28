"""F4 TTS / 三模型(default / clone / design)统一路由。

调用语义:`mimo.tts(text, voice_id=...)` 自动按 voice 库的 source 字段走对应模型。
- VoiceSource.DEFAULT → mimo-v2.5-tts,audio.voice = 预置名
- VoiceSource.CLONE   → mimo-v2.5-tts-voiceclone,audio.voice = reference DataURL
- VoiceSource.DESIGN  → mimo-v2.5-tts-voicedesign,user 消息 = 已存 prompt

批量(2026-04-30 新增):
- synthesize_batch:按句号 / 问号 / 感叹号 / 换行切段,每段独立合成
"""

from __future__ import annotations

import base64
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..client import MimoClient
from ..config import get_settings
from ..models import TTSRequest, VoiceRecord, VoiceSource, VoiceStatus
from ..storage import Storage
from ._media import audio_data_url

log = logging.getLogger(__name__)

# M1 实测从 400 错误响应里捞出的预置 voice 列表
DEFAULT_VOICES: list[tuple[str, str]] = [
    ("mimo_default", "默认音色 — 中性、清晰"),
    ("冰糖", "中文女声 · 温暖甜润"),
    ("茉莉", "中文女声 · 端庄大方"),
    ("苏打", "中文男声 · 活泼明亮"),
    ("白桦", "中文男声 · 沉稳磁性"),
    ("Mia", "英文女声 · clear & natural"),
    ("Chloe", "英文女声 · soft & warm"),
    ("Milo", "英文男声 · friendly & casual"),
    ("Dean", "英文男声 · deep & authoritative"),
]


def output_path(audio_format: str = "wav") -> Path:
    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "tts" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{uuid.uuid4().hex}.{audio_format}"


def _build_instructions(req: TTSRequest) -> str | None:
    """v2.5 风格控制:优先用 instructions(完整自然语言 / 导演模式指令);
    否则把简易 style 词转成一句指令。

    注:v2.5 通过 user 消息(自然语言)控制风格,没有 audio.speed / audio.style
    这类参数(旧透传实测无效),故 speed 字段已废弃、不再下发。
    """
    if req.instructions:
        return req.instructions
    if req.style:
        return f"请用「{req.style}」的风格和语气来朗读。"
    return None


async def synthesize(req: TTSRequest, storage: Storage | None = None) -> dict[str, str | int]:
    """合成音频 → 写盘 → 返回 {audio_path, voice, source, model, bytes, transcript_id}。"""
    settings = get_settings()
    voice_token = req.voice or req.voice_id or "mimo_default"
    audio_format = req.audio_format or "wav"
    instructions = _build_instructions(req)

    record: VoiceRecord | None = None
    if storage is not None:
        record = await storage.get_voice(voice_token)

    async with MimoClient(settings) as client:
        if record and record.source == VoiceSource.CLONE:
            if not record.reference_path or not Path(record.reference_path).is_file():
                raise FileNotFoundError(
                    f"克隆音色 {voice_token} 的参考音频已丢失:{record.reference_path}"
                )
            resp = await client.voice_clone(
                text=req.text,
                reference_data_url=audio_data_url(Path(record.reference_path)),
                model=settings.default_voice_clone_model,
                audio_format=audio_format,
                instructions=instructions,
            )
            used_model = settings.default_voice_clone_model
            used_source = "clone"

        elif record and record.source == VoiceSource.DESIGN:
            # voicedesign 是 stateless 的:用 prompt 重新生成会导致音色每次漂移
            # (实测同文本两次字节差 ~41%)。创建时已把试听音频固化到 reference_path,
            # 朗读新文本时改用它走 voiceclone 复刻,锁定为“创建时那一版”音色,
            # 保证 MCP / Web / 多次调用之间一致(实测降到 ~7%)。
            if record.reference_path and Path(record.reference_path).is_file():
                resp = await client.voice_clone(
                    text=req.text,
                    reference_data_url=audio_data_url(Path(record.reference_path)),
                    model=settings.default_voice_clone_model,
                    audio_format=audio_format,
                    instructions=instructions,
                )
                used_model = settings.default_voice_clone_model
            elif record.voice_prompt:
                # 试听音频缺失才回退 prompt 重新设计(音色可能漂移,记日志告警)
                log.warning(
                    "design 音色 %s 试听音频缺失,回退 voicedesign 重新生成(音色可能不一致)",
                    voice_token,
                )
                resp = await client.voice_design(
                    voice_prompt=record.voice_prompt,
                    sample_text=req.text,
                    model=settings.default_voice_design_model,
                    audio_format=audio_format,
                )
                used_model = settings.default_voice_design_model
            else:
                raise ValueError(f"设计音色 {voice_token} 既无试听音频也无 voice_prompt")
            used_source = "design"

        else:
            # default 路由:不在库里的字符串也按预置名直接发,失败由 MiMo 服务返回
            resp = await client.tts(
                text=req.text,
                voice=voice_token,
                model=settings.default_tts_model,
                audio_format=audio_format,
                instructions=instructions,
            )
            used_model = settings.default_tts_model
            used_source = "default"

    audio = resp["choices"][0]["message"]["audio"]
    audio_bytes = base64.b64decode(audio["data"])
    out = output_path(audio_format)
    out.write_bytes(audio_bytes)

    return {
        "audio_path": str(out),
        "voice": voice_token,
        "source": used_source,
        "model": used_model,
        "bytes": len(audio_bytes),
        "transcript_id": audio.get("id") or "",
        "audio_format": audio_format,
    }


# ---------------------------------------------------------------------------
# 批量切段合成(增量任务 1)
# ---------------------------------------------------------------------------

# 中英文句末标点 + 换行(切完保留分隔符在前一段尾部)
_BREAKERS = "。!?;.!?;\n"


@dataclass(frozen=True)
class BatchSegment:
    """一段批量合成结果。"""

    index: int
    total: int
    text: str
    audio_path: str
    voice: str
    source: str
    model: str
    bytes: int


def split_text(text: str, max_chars: int = 120) -> list[str]:
    """按句末标点切段,二次合并保证每段 ≤ max_chars。"""
    if not text.strip():
        return []
    if max_chars < 10:
        raise ValueError("max_chars 至少 10")

    # 第一步:按句末标点 / 换行切成"原子段"(切完包含分隔符)
    atoms: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in _BREAKERS:
            atom = "".join(buf)
            if atom.strip():
                atoms.append(atom)
            buf = []
    tail = "".join(buf)
    if tail.strip():
        atoms.append(tail)

    # 第二步:贪心合并,保证每段 ≤ max_chars
    merged: list[str] = []
    cur = ""
    for atom in atoms:
        if not cur:
            cur = atom
        elif len(cur) + len(atom) <= max_chars:
            cur += atom
        else:
            merged.append(cur.strip())
            cur = atom
    if cur.strip():
        merged.append(cur.strip())

    # 第三步:单段仍超长时按字符硬切
    final: list[str] = []
    for seg in merged:
        if len(seg) <= max_chars:
            final.append(seg)
            continue
        for i in range(0, len(seg), max_chars):
            chunk = seg[i : i + max_chars]
            if chunk.strip():
                final.append(chunk)
    return final


async def synthesize_batch(
    text: str,
    *,
    voice: str | None = None,
    voice_id: str | None = None,
    audio_format: str = "wav",
    instructions: str | None = None,
    segment_max_chars: int = 120,
    storage: Storage | None = None,
) -> AsyncIterator[BatchSegment]:
    """长文按段切分,顺序合成,逐段 yield。instructions 对每段统一生效。"""
    segments = split_text(text, segment_max_chars)
    total = len(segments)
    if total == 0:
        return

    for idx, seg_text in enumerate(segments):
        result = await synthesize(
            TTSRequest(
                text=seg_text,
                voice=voice,
                voice_id=voice_id,
                audio_format=audio_format,
                instructions=instructions,
            ),
            storage,
        )
        yield BatchSegment(
            index=idx,
            total=total,
            text=seg_text,
            audio_path=str(result["audio_path"]),
            voice=str(result["voice"]),
            source=str(result["source"]),
            model=str(result["model"]),
            bytes=int(result["bytes"]),
        )


async def seed_default_voices(storage: Storage) -> int:
    """把 9 个预置 voice 写入本地 SQLite。已存在的会做幂等更新。"""
    now = datetime.now(timezone.utc)
    written = 0
    for voice_id, desc in DEFAULT_VOICES:
        await storage.upsert_voice(
            VoiceRecord(
                voice_id=voice_id,
                name=voice_id,
                source=VoiceSource.DEFAULT,
                status=VoiceStatus.READY,
                description=desc,
                created_at=now,
                updated_at=now,
            )
        )
        written += 1
    return written
