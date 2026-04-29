"""图像 / 视频理解。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, UploadFile

from mimo_mcp.api import vision
from mimo_mcp.config import get_settings
from mimo_mcp.models import ImageInput

router = APIRouter()


def _save_upload(file: UploadFile, prefix: str) -> Path:
    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "uploads" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix or ".bin"
    target = out_dir / f"{prefix}_{datetime.now(timezone.utc).strftime('%H%M%S')}{ext}"
    return target


@router.post("/image")
async def image(
    file: UploadFile,
    prompt: str = Form(...),
    model: str | None = Form(None),
) -> dict:
    target = _save_upload(file, "img")
    target.write_bytes(await file.read())
    img = ImageInput(path=str(target), mime_type=file.content_type or "image/jpeg")
    return await vision.image_understand([img], prompt, model=model)


@router.post("/video")
async def video(
    video_url: str = Form(...),
    prompt: str = Form(...),
    model: str | None = Form(None),
) -> dict:
    return await vision.video_understand(video_url, prompt, model=model)
