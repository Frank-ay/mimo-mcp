"""M0 冒烟测试:模块可 import / 配置可读 / Storage 可用 / 11 个 tool 已注册。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest


def test_package_imports() -> None:
    import mimo_mcp  # noqa: F401
    import mimo_mcp.api.chat  # noqa: F401
    import mimo_mcp.api.vision  # noqa: F401
    import mimo_mcp.api.tts  # noqa: F401
    import mimo_mcp.api.voice_clone  # noqa: F401
    import mimo_mcp.api.voice_design  # noqa: F401
    import mimo_mcp.api.asr  # noqa: F401
    import mimo_mcp.api.usage  # noqa: F401
    import mimo_mcp.client  # noqa: F401
    import mimo_mcp.config  # noqa: F401
    import mimo_mcp.models  # noqa: F401
    import mimo_mcp.server  # noqa: F401
    import mimo_mcp.storage  # noqa: F401
    import webui.backend.main  # noqa: F401


def test_settings_default(tmp_path: Path) -> None:
    from mimo_mcp.config import get_settings

    settings = get_settings()
    assert settings.base_url.startswith("https://")
    assert settings.default_text_model.startswith("mimo-")
    assert settings.db_path == settings.data_dir / "mimo.db"
    assert (settings.artifacts_dir / "voice_refs").is_dir()


@pytest.mark.asyncio
async def test_storage_roundtrip() -> None:
    from mimo_mcp.config import get_settings
    from mimo_mcp.models import AuditLogEntry, VoiceRecord, VoiceSource, VoiceStatus
    from mimo_mcp.storage import Storage

    settings = get_settings()
    storage = Storage(settings.db_path)
    await storage.init()

    now = datetime.now(timezone.utc)
    record = VoiceRecord(
        voice_id="test_001",
        name="冒烟测试",
        source=VoiceSource.CLONE,
        status=VoiceStatus.READY,
        description="smoke",
        reference_path=None,
        created_at=now,
        updated_at=now,
    )
    await storage.upsert_voice(record)

    fetched = await storage.get_voice("test_001")
    assert fetched is not None
    assert fetched.name == "冒烟测试"

    voices = await storage.list_voices()
    assert any(v.voice_id == "test_001" for v in voices)

    log_id = await storage.append_audit(
        AuditLogEntry(ts=now, channel="mcp", tool="mimo.health", status="ok")
    )
    assert log_id > 0

    rows = await storage.recent_audit(limit=5)
    assert any(r["tool"] == "mimo.health" for r in rows)

    deleted = await storage.delete_voice("test_001")
    assert deleted is True
    assert await storage.get_voice("test_001") is None


@pytest.mark.asyncio
async def test_health_check_without_real_api() -> None:
    """没有真实网络/key 时,health_check 至少不抛异常,且字段完整。"""
    from mimo_mcp.api.usage import health_check

    result = await health_check()
    assert result.api_key_configured in (True, False)
    assert result.base_url.startswith("https://")
    assert isinstance(result.notes, list)


def test_split_text_segmentation() -> None:
    """切段算法不需要联网,纯逻辑覆盖。"""
    from mimo_mcp.api.tts import split_text

    # 5 个句子,每段 max_chars=10 → 至少切 3 段(贪心合并)
    text = "句子一。句子二!句子三?换行\n句子五。"
    segs = split_text(text, max_chars=10)
    assert len(segs) >= 3, f"期望 ≥3 段,实际 {len(segs)}: {segs}"
    assert all(seg.strip() for seg in segs)
    assert all(len(seg) <= 10 for seg in segs)

    # max_chars 充足时整段保留
    assert split_text("一句话。", max_chars=120) == ["一句话。"]
    # 空白
    assert split_text("   \n  ", max_chars=120) == []
    # 超长无标点 → 按字符硬切
    long_text = "a" * 250
    segs2 = split_text(long_text, max_chars=100)
    assert all(len(s) <= 100 for s in segs2)
    assert sum(len(s) for s in segs2) == 250
    # max_chars 过小 → 抛错
    with pytest.raises(ValueError):
        split_text("hi", max_chars=5)


def test_mcp_server_registers_all_tools() -> None:
    """PRD §7 的 11 个 tool 必须全部注册到 FastMCP。"""
    import asyncio

    from mimo_mcp.server import mcp

    expected = {
        "mimo.chat",
        "mimo.image_understand",
        "mimo.video_understand",
        "mimo.tts",
        "mimo.voice_clone_create",
        "mimo.voice_design_create",
        "mimo.voice_list",
        "mimo.voice_delete",
        "mimo.asr",
        "mimo.health",
        "mimo.usage",
    }
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    missing = expected - names
    assert not missing, f"缺失 tool:{missing}"
