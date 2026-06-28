"""F5 声音克隆。

M1 实测确认:走 /chat/completions,model=mimo-v2.5-tts-voiceclone,
audio.voice 必须是 DataURL `data:audio/wav;base64,<...>`。
**stateless**:每次合成都要传 reference,无独立 voice_id。

本仓库语义:
- create_clone:把用户的参考音频拷贝到 data/artifacts/voice_refs/,生成本地 voice_id,
  立即跑一次试听验证可用性,把试听音频和元数据入库。
- 之后 mimo.tts(voice_id=<clone_voice_id>) 会从库里读出 reference_path,
  自动构造 DataURL 调 voiceclone 模型(由 api/tts.synthesize 路由)。
"""

from __future__ import annotations

import base64
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..client import MimoClient
from ..config import get_settings
from ..models import VoiceCloneCreateRequest, VoiceRecord, VoiceSource, VoiceStatus
from ..storage import Storage
from ._media import audio_data_url

SAMPLE_TEXT = "你好,这是 MiMo voice clone 的试听样本。"


def _ref_target(voice_id: str, src_suffix: str) -> Path:
    settings = get_settings()
    out = settings.artifacts_dir / "voice_refs"
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{voice_id}{src_suffix or '.wav'}"


async def create_clone(req: VoiceCloneCreateRequest, storage: Storage) -> VoiceRecord:
    """落地参考音频 → 立即跑一次试听 → 入库 → 返回 VoiceRecord。"""
    settings = get_settings()
    src = Path(req.reference_audio_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"参考音频不存在:{src}")

    voice_id = f"clone_{uuid.uuid4().hex[:12]}"
    target = _ref_target(voice_id, src.suffix)

    if target.resolve() != src.resolve():
        shutil.copyfile(src, target)

    data_url = audio_data_url(target)

    async with MimoClient(settings) as client:
        resp = await client.voice_clone(
            text=SAMPLE_TEXT,
            reference_data_url=data_url,
            model=settings.default_voice_clone_model,
        )

    audio = resp["choices"][0]["message"]["audio"]
    sample_bytes = base64.b64decode(audio["data"])
    sample_out = settings.artifacts_dir / "tts" / datetime.now(timezone.utc).strftime("%Y%m%d") / f"{voice_id}_sample.wav"
    sample_out.parent.mkdir(parents=True, exist_ok=True)
    sample_out.write_bytes(sample_bytes)

    now = datetime.now(timezone.utc)
    record = VoiceRecord(
        voice_id=voice_id,
        name=req.name,
        source=VoiceSource.CLONE,
        status=VoiceStatus.READY,
        description=req.description,
        reference_path=str(target),
        created_at=now,
        updated_at=now,
    )
    await storage.upsert_voice(record)
    return record
