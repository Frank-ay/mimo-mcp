"""音色库 / 克隆 / 设计 路由。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from mimo_mcp.api import voice_clone, voice_design
from mimo_mcp.config import get_settings
from mimo_mcp.models import (
    VoiceCloneCreateRequest,
    VoiceDesignCreateRequest,
    VoiceSource,
)

router = APIRouter()


@router.get("")
async def list_voices(request: Request, source: str | None = None) -> list[dict]:
    src = VoiceSource(source) if source else None
    voices = await request.app.state.storage.list_voices(src)
    return [v.model_dump(mode="json") for v in voices]


@router.delete("/{voice_id}")
async def delete_voice(request: Request, voice_id: str) -> dict[str, bool]:
    ok = await request.app.state.storage.delete_voice(voice_id)
    if not ok:
        raise HTTPException(status_code=404, detail="voice_id 不存在")
    return {"deleted": True}


@router.post("/clone")
async def create_clone(
    request: Request,
    file: UploadFile,
    name: str = Form(...),
    description: str | None = Form(None),
) -> dict:
    settings = get_settings()
    voice_refs = settings.artifacts_dir / "voice_refs"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_ext = Path(file.filename or "ref.wav").suffix or ".wav"
    saved = voice_refs / f"{ts}_{name}{safe_ext}"
    saved.write_bytes(await file.read())

    req = VoiceCloneCreateRequest(
        reference_audio_path=str(saved),
        name=name,
        description=description,
    )
    record = await voice_clone.create_clone(req, request.app.state.storage)
    return record.model_dump(mode="json")


@router.post("/design")
async def create_design(
    request: Request,
    voice_prompt: str = Form(...),
    name: str = Form(...),
    sample_text: str | None = Form(None),
    optimize_text_preview: bool = Form(False),
) -> dict:
    # sample_text 为空时不传,让 VoiceDesignCreateRequest 用其默认样本文本
    payload: dict[str, object] = {
        "voice_prompt": voice_prompt,
        "name": name,
        "optimize_text_preview": optimize_text_preview,
    }
    if sample_text:
        payload["sample_text"] = sample_text
    req = VoiceDesignCreateRequest(**payload)
    record = await voice_design.create_design(req, request.app.state.storage)
    return record.model_dump(mode="json")
