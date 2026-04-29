"""真实联网集成测试。**默认 skip**,只在设置 `MIMO_RUN_LIVE=1` 时执行。

每个用例都会真实调用 MiMo API,会消耗 token plan 套餐积分。
跑法:
    MIMO_RUN_LIVE=1 uv run pytest -q tests/test_live.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

LIVE = os.environ.get("MIMO_RUN_LIVE") == "1"
pytestmark = pytest.mark.skipif(not LIVE, reason="设置 MIMO_RUN_LIVE=1 才跑真·联网测试")


@pytest.fixture(autouse=True)
def _disable_isolated_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """覆盖 conftest 的 tmp_path,使用真实 .env 的 MIMO_DATA_DIR/API_KEY。"""
    for k in ("MIMO_DATA_DIR", "MIMO_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    from mimo_mcp.config import get_settings  # noqa: WPS433

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_health_full() -> None:
    from mimo_mcp.api.usage import health_check

    r = await health_check()
    assert r.api_key_configured is True
    assert r.base_url_reachable is True
    assert r.auth_valid is True


@pytest.mark.asyncio
async def test_live_chat_v25() -> None:
    from mimo_mcp.api.chat import chat_completion
    from mimo_mcp.models import ChatMessage, ChatRequest

    req = ChatRequest(
        messages=[ChatMessage(role="user", content="一句话回答:1+1=?")],
        model="mimo-v2.5",
        max_tokens=2000,
    )
    resp = await chat_completion(req)
    text = resp["choices"][0]["message"]["content"] or ""
    assert "2" in text or "二" in text


@pytest.mark.asyncio
async def test_live_tts_default_voice() -> None:
    from mimo_mcp.api import tts as api_tts
    from mimo_mcp.config import get_settings
    from mimo_mcp.models import TTSRequest
    from mimo_mcp.storage import Storage

    s = get_settings()
    storage = Storage(s.db_path)
    await storage.init()
    await api_tts.seed_default_voices(storage)

    out = await api_tts.synthesize(
        TTSRequest(text="联网测试。", voice="mimo_default"),
        storage,
    )
    p = Path(out["audio_path"])
    assert p.is_file()
    head = p.read_bytes()[:4]
    assert head == b"RIFF", f"非 WAV 文件:{head!r}"
    assert out["model"] == "mimo-v2.5-tts"


@pytest.mark.asyncio
async def test_live_image_understand() -> None:
    from mimo_mcp.api.vision import image_understand
    from mimo_mcp.models import ImageInput

    img = Path("data/artifacts/uploads/_test_img.png")
    if not img.is_file():
        pytest.skip("缺少测试图 data/artifacts/uploads/_test_img.png(运行 B4 探针先生成)")
    resp = await image_understand(
        [ImageInput(path=str(img), mime_type="image/png")],
        prompt="只回答两个字:这张图主色是什么?",
    )
    text = (resp["choices"][0]["message"].get("content") or "")
    assert "橙" in text or "orange" in text.lower(), f"识别异常:{text!r}"
