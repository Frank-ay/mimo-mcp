"""图像 / 视频理解 Web 路由。

视频端点(2026-04-30 升级)同时接受三种输入,前端二选一即可:
- multipart 文件上传(本地视频)
- form 字段 ``video_url``:直链 mp4 / B 站 / YouTube / 抖音 等
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel

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
    prompt: str = Form(...),
    model: str | None = Form(None),
    video_url: str | None = Form(None),
    file: UploadFile | None = None,
) -> dict:
    """同时支持文件上传 / URL 两种输入,二选一。"""
    if file is not None and getattr(file, "filename", None):
        target = _save_upload(file, "vid")
        target.write_bytes(await file.read())
        return await vision.video_understand(str(target), prompt, model=model)

    if video_url:
        return await vision.video_understand(video_url, prompt, model=model)

    raise HTTPException(
        status_code=400,
        detail="必须提供 file(本地视频)或 video_url(直链 / B 站等)之一",
    )


class VideoUrlBody(BaseModel):
    video_url: str
    prompt: str
    model: str | None = None


@router.post("/video/url")
async def video_via_json(body: VideoUrlBody) -> dict:
    """JSON 路径:让脚本/curl 调用更顺手。"""
    return await vision.video_understand(body.video_url, body.prompt, model=body.model)
