"""F6 声音设计:文字描述 → 自定义音色试听。

M1 实测确认:走 /chat/completions,model=mimo-v2.5-tts-voicedesign。
messages = [
  {"role": "user",      "content": <音色描述 prompt>},
  {"role": "assistant", "content": <要朗读的样本文本>},
]
**关键**:MiMo 的 voicedesign 是 stateless 的,每次基于 prompt + 文本临时生成音色,
**不返回独立 voice_id**。本仓库的语义:把 prompt 当作可复用的"voice 草稿"入库,
后续要用这个音色朗读新文本,需要用相同 prompt + 新文本再调一次。
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..client import MimoClient
from ..config import get_settings
from ..models import VoiceDesignCreateRequest, VoiceRecord, VoiceSource, VoiceStatus
from ..storage import Storage


def _sample_path(voice_id: str, audio_format: str = "wav") -> Path:
    settings = get_settings()
    samples = settings.artifacts_dir / "voice_refs"
    samples.mkdir(parents=True, exist_ok=True)
    return samples / f"{voice_id}.{audio_format}"


async def create_design(req: VoiceDesignCreateRequest, storage: Storage) -> VoiceRecord:
    """创建一条声音设计记录:调 voicedesign 出试听 → 写盘 → 入库。"""
    settings = get_settings()
    voice_id = f"design_{uuid.uuid4().hex[:12]}"

    async with MimoClient(settings) as client:
        resp = await client.voice_design(
            voice_prompt=req.voice_prompt,
            sample_text=req.sample_text,
            model=settings.default_voice_design_model,
            optimize_text_preview=req.optimize_text_preview,
        )

    audio = resp["choices"][0]["message"]["audio"]
    audio_bytes = base64.b64decode(audio["data"])
    out = _sample_path(voice_id)
    out.write_bytes(audio_bytes)

    now = datetime.now(timezone.utc)
    record = VoiceRecord(
        voice_id=voice_id,
        name=req.name,
        source=VoiceSource.DESIGN,
        status=VoiceStatus.READY,
        voice_prompt=req.voice_prompt,
        reference_path=str(out),
        created_at=now,
        updated_at=now,
    )
    await storage.upsert_voice(record)
    return record
