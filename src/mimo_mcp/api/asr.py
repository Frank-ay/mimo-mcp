"""F7 ASR 语音转写。

2026-06-27 复核:Token Plan 套餐含 `mimo-v2.5-asr`,走 OpenAI 兼容
`/chat/completions`(音频以 base64 `input_audio` 传入,**不是** `/audio/transcriptions`
—— 后者在 MiMo 网关返回 404)。`asr_options.language` 仅支持 auto/zh/en(方言靠 auto
自动检测);返回普通 chat completion,转写文本在 choices[0].message.content,不含分段
时间戳 / duration。

- 入参:`audio_path`(本地文件)或 `audio_url`(直链,内部下载后上传)二选一。
- 单段上限:base64 后约 10MB(原始约 7.5MB);更大的音频用 `transcribe_chunked`
  按时间切段、逐段转写、合并文本。
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..client import MimoClient
from ..config import get_settings
from ..models import ASRRequest
from ._media import probe_duration

log = logging.getLogger(__name__)

# MiMo ASR 走 /chat/completions,音频 base64 后上限 10MB → 原始约 7.5MB,这里保守取 7MB
_MAX_AUDIO_BYTES = 7 * 1024 * 1024


async def _load_audio(req: ASRRequest) -> tuple[bytes, str, str]:
    """把音频来源归一化为 (字节, 文件名, content_type)。"""
    if req.audio_path:
        path = Path(req.audio_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"音频文件不存在:{path}")
        mime = mimetypes.guess_type(path.name)[0] or "audio/wav"
        return path.read_bytes(), path.name, mime

    if req.audio_url:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as dl:
            resp = await dl.get(req.audio_url)
            resp.raise_for_status()
        name = Path(urlparse(req.audio_url).path).name or "audio.wav"
        mime = (
            resp.headers.get("content-type", "").split(";")[0].strip()
            or mimetypes.guess_type(name)[0]
            or "audio/wav"
        )
        return resp.content, name, mime

    raise ValueError("ASR 需要 audio_path 或 audio_url 之一")


async def transcribe(req: ASRRequest) -> dict[str, Any]:
    """转写音频(单段),返回 {text, model, language}。"""
    settings = get_settings()
    audio_bytes, _filename, content_type = await _load_audio(req)

    size_mb = len(audio_bytes) // 1024 // 1024
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise ValueError(
            f"音频过大({size_mb} MB),base64 编码后超过 MiMo ASR 的 10 MB 上限,"
            "请改用「长音频分段转写」。"
        )

    async with MimoClient(settings) as client:
        raw = await client.transcribe(
            audio_bytes,
            model=settings.default_asr_model,
            language=req.language,
            content_type=content_type,
        )

    return {
        "text": _extract_text(raw),
        "model": settings.default_asr_model,
        "language": req.language,
    }


def _extract_text(raw: dict[str, Any]) -> str:
    """从 chat completion 响应里取转写文本。"""
    choices = raw.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


# ---------------------------------------------------------------------------
# 长音频分段转写:音频过大 → 按时间切段 → 逐段转写 → 合并文本
# ---------------------------------------------------------------------------

# 每段统一转成 16kHz mono PCM(ASR 足够),320 KB/s x 120s 约 3.8MB,base64 约 5MB,
# 远低于 10MB 上限;段时长越长段数越少越快,但要给边界留余量,默认 120s。
_CHUNK_SR = 16000


async def _ffmpeg_segment_audio(
    src: Path, segment_seconds: int
) -> list[tuple[Path, float, float]]:
    """ffmpeg 把音频切成多段(统一 16kHz mono wav),返回 [(段路径, start, end)]。"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("分段转写需要 ffmpeg,请先 `brew install ffmpeg` 后重试。")

    duration = await probe_duration(src)
    out_dir = src.parent / f"{src.stem}_asrchunks_{uuid.uuid4().hex[:6]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "part_%03d.wav")

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-ac", "1", "-ar", str(_CHUNK_SR), "-c:a", "pcm_s16le",
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-reset_timestamps", "1",
        out_template,
    ]
    log.info("ffmpeg 音频切段:%s → %s/(每段 %ds)", src.name, out_dir.name, segment_seconds)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 音频切段失败:{stderr.decode('utf-8', errors='replace')[:300]}"
        )

    parts = sorted(out_dir.glob("part_*.wav"))
    if not parts:
        raise RuntimeError("切段成功但找不到产物文件,可能音频太短或格式损坏。")

    result: list[tuple[Path, float, float]] = []
    for i, p in enumerate(parts):
        start = float(i * segment_seconds)
        end = start + float(segment_seconds)
        if duration > 0:
            end = min(end, duration)
        result.append((p, start, end))
    return result


async def transcribe_chunked(
    req: ASRRequest, *, segment_seconds: int = 120
) -> AsyncIterator[dict[str, Any]]:
    """长音频分段转写。

    切段 → 逐段调 /chat/completions ASR → 合并文本。yield 事件(``kind`` 区分):
    - ``plan``:总段数 + 每段时间区间
    - ``segment``:单段转写完(含 text)
    - ``summary``:合并后的完整文本
    """
    settings = get_settings()
    audio_bytes, filename, _ct = await _load_audio(req)

    tmp_dir = settings.artifacts_dir / "uploads" / "asr_chunk_src"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "audio.wav"
    src = tmp_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    src.write_bytes(audio_bytes)

    chunk_dir: Path | None = None
    try:
        chunks = await _ffmpeg_segment_audio(src, segment_seconds)
        chunk_dir = chunks[0][0].parent
        total = len(chunks)
        duration = chunks[-1][2] if chunks else 0.0

        yield {
            "kind": "plan",
            "total": total,
            "duration": duration,
            "segment_seconds": segment_seconds,
            "segments": [
                {"index": i, "start": s, "end": e, "bytes": p.stat().st_size}
                for i, (p, s, e) in enumerate(chunks)
            ],
        }

        texts: list[str] = []
        async with MimoClient(settings) as client:
            for i, (chunk_path, start, end) in enumerate(chunks):
                try:
                    raw = await client.transcribe(
                        chunk_path.read_bytes(),
                        model=settings.default_asr_model,
                        language=req.language,
                        content_type="audio/wav",
                    )
                    seg_text = _extract_text(raw).strip()
                except Exception as e:  # 单段失败不应中断整体
                    seg_text = ""
                    log.warning("ASR 段 %d/%d 失败:%s", i + 1, total, e)
                texts.append(seg_text)
                yield {
                    "kind": "segment",
                    "index": i,
                    "start": start,
                    "end": end,
                    "text": seg_text,
                }

        merged = "".join(t for t in texts if t)
        yield {
            "kind": "summary",
            "text": merged,
            "total": total,
            "duration": duration,
        }
    finally:
        # 清理临时切段产物与源副本,避免 data/ 堆积
        if chunk_dir is not None:
            shutil.rmtree(chunk_dir, ignore_errors=True)
        src.unlink(missing_ok=True)


async def cloud_available(client: MimoClient | None = None) -> bool:
    """探测账号是否真的能用 ASR:default_asr_model 是否在 /models 列表里。

    传入复用的 client 可避免重复建连(health_check 已持有一个)。
    网络/鉴权异常一律保守判定不可用,不向上抛。
    """
    settings = get_settings()
    try:
        if client is not None:
            models = await client.list_models()
        else:
            async with MimoClient(settings) as owned:
                models = await owned.list_models()
    except Exception as e:  # 探测失败即视为不可用
        log.warning("ASR 可用性探测失败:%s", e)
        return False
    return settings.default_asr_model in models
