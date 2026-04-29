"""ASR 路由(M1 实测后填充)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, UploadFile

from mimo_mcp.api import asr
from mimo_mcp.config import get_settings
from mimo_mcp.models import ASRRequest

router = APIRouter()


@router.post("")
async def transcribe(
    file: UploadFile,
    language: str = Form("auto"),
    with_timestamps: bool = Form(False),
) -> dict:
    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "uploads" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "audio.wav").suffix or ".wav"
    target = out_dir / f"asr_{datetime.now(timezone.utc).strftime('%H%M%S')}{ext}"
    target.write_bytes(await file.read())

    req = ASRRequest(audio_path=str(target), language=language,
                     with_timestamps=with_timestamps)
    try:
        return await asr.transcribe(req)
    except NotImplementedError as e:
        return {"status": "unavailable", "reason": str(e)}
