"""F4 TTS Web 路由(增量任务 1)。

端点:
- POST /api/tts/synthesize  单段一次性,返回 JSON,含 audio_url(可直接给 <audio src>)
- POST /api/tts/batch       长文切段,SSE 流,逐段推送事件
- GET  /api/tts/audio/{filename}  把 data/artifacts/tts 下的产物反代给前端
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from mimo_mcp.api import tts as api_tts
from mimo_mcp.config import get_settings
from mimo_mcp.models import AuditLogEntry, TTSRequest

router = APIRouter()


class TTSBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    voice: str | None = None
    voice_id: str | None = None
    audio_format: Literal["wav", "mp3"] = "wav"
    speed: float | None = None
    style: str | None = None


class BatchBody(TTSBody):
    segment_max_chars: int = Field(default=120, ge=20, le=500)


def _audio_url(audio_path: str) -> str:
    """把绝对/相对 audio_path 转成可被前端 <audio src> 用的 URL。"""
    p = Path(audio_path)
    return f"/api/tts/audio/{p.name}"


async def _record_audit(
    storage: Any,
    *,
    status: Literal["ok", "error"],
    model: str | None,
    error: str | None = None,
    latency_ms: int | None = None,
) -> None:
    try:
        await storage.append_audit(
            AuditLogEntry(
                ts=datetime.now(timezone.utc),
                channel="web",
                tool="mimo.tts",
                model=model,
                latency_ms=latency_ms,
                status=status,
                error=error,
            )
        )
    except Exception:
        # 审计写入失败不影响主流程
        pass


@router.post("/synthesize")
async def synthesize(request: Request, body: TTSBody) -> dict[str, Any]:
    started = time.perf_counter()
    storage = request.app.state.storage
    try:
        result = await api_tts.synthesize(
            TTSRequest(
                text=body.text,
                voice=body.voice,
                voice_id=body.voice_id,
                audio_format=body.audio_format,
                speed=body.speed,
                style=body.style,
            ),
            storage,
        )
    except Exception as e:
        latency = int((time.perf_counter() - started) * 1000)
        await _record_audit(storage, status="error", model=None, error=str(e), latency_ms=latency)
        raise HTTPException(status_code=500, detail=f"TTS 合成失败:{e}") from e

    latency = int((time.perf_counter() - started) * 1000)
    await _record_audit(storage, status="ok", model=str(result["model"]), latency_ms=latency)

    return {
        **result,
        "audio_url": _audio_url(str(result["audio_path"])),
    }


@router.post("/batch")
async def batch(request: Request, body: BatchBody) -> StreamingResponse:
    storage = request.app.state.storage
    segments_preview = api_tts.split_text(body.text, body.segment_max_chars)

    async def event_stream() -> Any:
        # 第一帧:先告知前端总段数和切分预览,UI 可立即占位
        yield "event: plan\n" + "data: " + json.dumps(
            {"total": len(segments_preview), "segments": segments_preview},
            ensure_ascii=False,
        ) + "\n\n"

        if not segments_preview:
            yield "event: done\ndata: {}\n\n"
            return

        try:
            async for seg in api_tts.synthesize_batch(
                body.text,
                voice=body.voice,
                voice_id=body.voice_id,
                audio_format=body.audio_format,
                segment_max_chars=body.segment_max_chars,
                storage=storage,
            ):
                payload = {
                    "index": seg.index,
                    "total": seg.total,
                    "text": seg.text,
                    "audio_url": _audio_url(seg.audio_path),
                    "voice": seg.voice,
                    "source": seg.source,
                    "model": seg.model,
                    "bytes": seg.bytes,
                }
                await _record_audit(storage, status="ok", model=seg.model)
                yield "event: segment\n" + "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
        except Exception as e:
            await _record_audit(storage, status="error", model=None, error=str(e))
            yield "event: error\n" + "data: " + json.dumps(
                {"message": str(e)}, ensure_ascii=False
            ) + "\n\n"
            return

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_ALLOWED_EXT = {".wav", ".mp3", ".pcm", ".opus"}


@router.get("/audio/{filename}")
async def audio(filename: str) -> FileResponse:
    """反代 data/artifacts/tts/<日期>/<filename> 与 voice_refs/<filename>。

    路径校验:严格只允许 [a-zA-Z0-9_-.] 命名 + 白名单后缀,防越权读其他目录。
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的后缀:{suffix}")

    settings = get_settings()
    candidates: list[Path] = list((settings.artifacts_dir / "tts").rglob(filename))
    candidates.extend((settings.artifacts_dir / "voice_refs").rglob(filename))
    for c in candidates:
        if c.is_file() and c.resolve().is_relative_to(settings.artifacts_dir.resolve()):
            return FileResponse(c, media_type=_mime(suffix))
    raise HTTPException(status_code=404, detail="文件不存在")


def _mime(suffix: str) -> str:
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".pcm": "audio/L16",
        ".opus": "audio/ogg",
    }.get(suffix, "application/octet-stream")
