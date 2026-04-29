"""F4 TTS / 三模型(default / clone / design)统一路由。

调用语义:`mimo.tts(text, voice_id=...)` 自动按 voice 库的 source 字段走对应模型。
- VoiceSource.DEFAULT → mimo-v2.5-tts,audio.voice = 预置名
- VoiceSource.CLONE   → mimo-v2.5-tts-voiceclone,audio.voice = reference DataURL
- VoiceSource.DESIGN  → mimo-v2.5-tts-voicedesign,user 消息 = 已存 prompt
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..client import MimoClient
from ..config import get_settings
from ..models import TTSRequest, VoiceRecord, VoiceSource, VoiceStatus
from ..storage import Storage

# M1 实测从 400 错误响应里捞出的预置 voice 列表
DEFAULT_VOICES: list[tuple[str, str]] = [
    ("mimo_default", "默认音色 — 中性、清晰"),
    ("冰糖", "中文女声 · 温暖甜润"),
    ("茉莉", "中文女声 · 端庄大方"),
    ("苏打", "中文女声 · 活泼明亮"),
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


def _data_url(path: Path, mime: str = "audio/wav") -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


async def synthesize(req: TTSRequest, storage: Storage | None = None) -> dict[str, str | int]:
    """合成音频 → 写盘 → 返回 {audio_path, voice, source, model, bytes, transcript_id}。"""
    settings = get_settings()
    voice_token = req.voice or req.voice_id or "mimo_default"
    audio_format = req.audio_format or "wav"

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
                reference_data_url=_data_url(Path(record.reference_path)),
                model=settings.default_voice_clone_model,
                audio_format=audio_format,
            )
            used_model = settings.default_voice_clone_model
            used_source = "clone"

        elif record and record.source == VoiceSource.DESIGN:
            if not record.voice_prompt:
                raise ValueError(f"设计音色 {voice_token} 缺失 voice_prompt")
            resp = await client.voice_design(
                voice_prompt=record.voice_prompt,
                sample_text=req.text,
                model=settings.default_voice_design_model,
                audio_format=audio_format,
            )
            used_model = settings.default_voice_design_model
            used_source = "design"

        else:
            # default 路由:不在库里的字符串也按预置名直接发,失败由 MiMo 服务返回
            resp = await client.tts(
                text=req.text,
                voice=voice_token,
                model=settings.default_tts_model,
                audio_format=audio_format,
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
    }


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
