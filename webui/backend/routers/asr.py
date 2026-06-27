"""ASR 路由:语音转写(mimo-v2.5-asr,token-plan 实测可用)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile

from mimo_mcp.api import asr
from mimo_mcp.client import MimoAPIError
from mimo_mcp.config import get_settings
from mimo_mcp.models import ASRRequest

router = APIRouter()


@router.post("")
async def transcribe(
    file: UploadFile,
    language: str = Form("auto"),
    with_timestamps: bool = Form(False),
    prompt: str | None = Form(None),
) -> dict:
    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "uploads" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "audio.wav").suffix or ".wav"
    target = out_dir / f"asr_{datetime.now(timezone.utc).strftime('%H%M%S')}{ext}"
    target.write_bytes(await file.read())

    req = ASRRequest(
        audio_path=str(target),
        language=language,
        with_timestamps=with_timestamps,
        prompt=prompt,
    )
    try:
        return await asr.transcribe(req)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except MimoAPIError as e:
        # MiMo 服务端 4xx 透传,其余按 502
        status = e.status if 400 <= e.status < 500 else 502
        raise HTTPException(status_code=status, detail=str(e)) from e
