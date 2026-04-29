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
    try:
        record = await voice_clone.create_clone(req, request.app.state.storage)
        return record.model_dump(mode="json")
    except NotImplementedError:
        # M0 阶段:返回 stub 让前端能显示流程
        return voice_clone.stub_record(req).model_dump(mode="json")


@router.post("/design")
async def create_design(
    request: Request,
    voice_prompt: str = Form(...),
    name: str = Form(...),
) -> dict:
    req = VoiceDesignCreateRequest(voice_prompt=voice_prompt, name=name)
    try:
        record = await voice_design.create_design(req, request.app.state.storage)
        return record.model_dump(mode="json")
    except NotImplementedError:
        return voice_design.stub_record(req).model_dump(mode="json")
