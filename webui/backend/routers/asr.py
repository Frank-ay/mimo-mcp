"""ASR 路由:语音转写(mimo-v2.5-asr,token-plan 实测可用)。

- POST /api/asr          单段一次性,返回 {text, model, language}
- POST /api/asr/chunked  长音频分段转写,SSE 流式(plan/segment/summary/done)
- POST /api/asr/diarize  说话人分离转写(sherpa-onnx + MiMo),SSE 流式
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from mimo_mcp.api import asr, diarization
from mimo_mcp.client import MimoAPIError
from mimo_mcp.config import get_settings
from mimo_mcp.models import ASRRequest

from ..sse import sse_event

router = APIRouter()


def _save_upload(file: UploadFile, content: bytes) -> Path:
    """把上传音频落到 data/artifacts/uploads/<日期>/ 下,返回路径。"""
    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "uploads" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "audio.wav").suffix or ".wav"
    target = out_dir / f"asr_{datetime.now(timezone.utc).strftime('%H%M%S%f')}{ext}"
    target.write_bytes(content)
    return target


@router.post("")
async def transcribe(
    file: UploadFile,
    language: str = Form("auto"),
) -> dict:
    target = _save_upload(file, await file.read())
    req = ASRRequest(audio_path=str(target), language=language)
    try:
        return await asr.transcribe(req)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MimoAPIError as e:
        # MiMo 服务端 4xx 透传,其余按 502
        status = e.status if 400 <= e.status < 500 else 502
        raise HTTPException(status_code=status, detail=str(e)) from e


async def _chunked_stream(req: ASRRequest, segment_seconds: int) -> Any:
    """把 transcribe_chunked 的 yield 包装成 SSE 文本流。"""
    try:
        async for evt in asr.transcribe_chunked(req, segment_seconds=segment_seconds):
            yield sse_event(evt["kind"], evt)
    except (ValueError, FileNotFoundError) as e:
        yield sse_event("error", {"status": 400, "message": str(e)})
    except RuntimeError as e:
        yield sse_event("error", {"status": 502, "message": str(e)})
    except MimoAPIError as e:
        yield sse_event("error", {"status": e.status, "message": str(e)})
    except Exception as e:
        yield sse_event("error", {"status": 500, "message": f"未知错误:{e}"})
    yield sse_event("done", {})


@router.post("/chunked")
async def transcribe_chunked_route(
    file: UploadFile,
    language: str = Form("auto"),
    segment_seconds: int = Form(120),
) -> StreamingResponse:
    """长音频分段转写:切段 → 逐段转写 → 合并,SSE 流式返回进度与结果。"""
    if not (30 <= segment_seconds <= 240):
        raise HTTPException(
            status_code=400, detail="segment_seconds 必须在 30-240 秒之间"
        )
    target = _save_upload(file, await file.read())
    req = ASRRequest(audio_path=str(target), language=language)
    return StreamingResponse(
        _chunked_stream(req, segment_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _diarize_stream(audio_path: str, language: str, num_speakers: int) -> Any:
    """把 transcribe_diarized 的 yield 包装成 SSE 文本流。"""
    try:
        async for evt in diarization.transcribe_diarized(
            audio_path, language=language, num_speakers=num_speakers
        ):
            yield sse_event(evt["kind"], evt)
    except (ValueError, FileNotFoundError) as e:
        yield sse_event("error", {"status": 400, "message": str(e)})
    except RuntimeError as e:
        # 模型缺失 / ffmpeg 缺失等
        yield sse_event("error", {"status": 502, "message": str(e)})
    except MimoAPIError as e:
        yield sse_event("error", {"status": e.status, "message": str(e)})
    except Exception as e:
        yield sse_event("error", {"status": 500, "message": f"未知错误:{e}"})
    yield sse_event("done", {})


@router.post("/diarize")
async def diarize_route(
    file: UploadFile,
    language: str = Form("auto"),
    num_speakers: int = Form(-1),
) -> StreamingResponse:
    """说话人分离转写:sherpa-onnx 分离说话人 + MiMo 逐段转写,SSE 流式。

    num_speakers <= 0 时自动聚类推断说话人数。
    """
    target = _save_upload(file, await file.read())
    return StreamingResponse(
        _diarize_stream(str(target), language, num_speakers),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
