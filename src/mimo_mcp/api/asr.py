"""F7 ASR 语音转写。

2026-06-27 实测:Token Plan 套餐含 `mimo-v2.5-asr`,走 OpenAI 兼容
`/audio/transcriptions`(multipart)。决策 PRD §15-Q6「仅 MiMo 云端」依然成立,
区别是云端 ASR 已开放,不再返回 unavailable。

- 入参:`audio_path`(本地文件)或 `audio_url`(直链,内部下载后上传)二选一。
- `with_timestamps=True` → `response_format=verbose_json`,返回分段时间戳。
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from ..client import MimoClient
from ..config import get_settings
from ..models import ASRRequest

log = logging.getLogger(__name__)

# 防御性上限:音频过大直接报错,而非把巨量字节塞进 multipart 空转
_MAX_AUDIO_BYTES = 100 * 1024 * 1024


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
    """转写音频,返回结构化结果。"""
    settings = get_settings()
    audio_bytes, filename, content_type = await _load_audio(req)

    size_mb = len(audio_bytes) // 1024 // 1024
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise ValueError(
            f"音频过大({size_mb} MB),超过 {_MAX_AUDIO_BYTES // 1024 // 1024} MB 上限。"
        )

    response_format = "verbose_json" if req.with_timestamps else "json"
    async with MimoClient(settings) as client:
        raw = await client.transcribe(
            audio_bytes,
            filename,
            model=settings.default_asr_model,
            language=req.language,
            response_format=response_format,
            timestamp_granularity="segment" if req.with_timestamps else None,
            prompt=req.prompt,
            content_type=content_type,
        )

    result: dict[str, Any] = {
        "text": raw.get("text", ""),
        "model": settings.default_asr_model,
        "language": raw.get("language"),
        "duration": raw.get("duration"),
    }
    if req.with_timestamps:
        result["segments"] = [
            {
                "start": seg.get("start"),
                "end": seg.get("end"),
                "text": seg.get("text", ""),
            }
            for seg in raw.get("segments", [])
        ]
    return result


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
    except Exception as e:  # noqa: BLE001 - 探测失败即视为不可用
        log.warning("ASR 可用性探测失败:%s", e)
        return False
    return settings.default_asr_model in models
