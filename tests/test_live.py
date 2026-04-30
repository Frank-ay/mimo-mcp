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


# ---------------------------------------------------------------------------
# 增量任务 1:Web TTS 高级路径联网测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_tts_mp3_format() -> None:
    """合成 mp3,验证 magic 不是 RIFF 而是 MPEG ADTS / ID3。"""
    from mimo_mcp.api import tts as api_tts
    from mimo_mcp.config import get_settings
    from mimo_mcp.models import TTSRequest
    from mimo_mcp.storage import Storage

    s = get_settings()
    storage = Storage(s.db_path)
    await storage.init()

    out = await api_tts.synthesize(
        TTSRequest(text="MP3 测试。", voice="mimo_default", audio_format="mp3"),
        storage,
    )
    p = Path(out["audio_path"])
    assert p.is_file()
    assert p.suffix == ".mp3"
    head = p.read_bytes()[:4]
    # MPEG ADTS 帧头(0xFFFx)或 ID3 标签
    assert head[:3] == b"ID3" or (head[0] == 0xFF and (head[1] & 0xE0) == 0xE0), (
        f"非 MP3 文件,magic={head!r}"
    )


@pytest.mark.asyncio
async def test_live_video_local_path() -> None:
    """本地 mp4 → base64 DataURL → MiMo 视频理解。"""
    from mimo_mcp.api.vision import video_understand

    video = Path("data/artifacts/uploads/_test_video.mp4")
    if not video.is_file():
        pytest.skip("缺少测试视频 data/artifacts/uploads/_test_video.mp4")

    # 注意:不要让 thinking 模型死磕字数,会反复 refining 耗光 token
    resp = await video_understand(
        str(video),
        "简单描述这段视频里的角色和场景,一两句话即可。",
        max_tokens=6000,
    )
    text = (resp["choices"][0]["message"].get("content") or "").strip()
    assert len(text) > 0, f"识别为空,finish={resp['choices'][0]['finish_reason']}"
    # 视频里是 Big Buck Bunny 兔子 / 草地 / 蝴蝶
    assert any(kw in text for kw in ("兔", "草", "蝴蝶", "动物")), f"识别异常:{text!r}"


@pytest.mark.asyncio
async def test_live_tts_batch() -> None:
    """长文按段切分,所有段都成功合成且每段是合法 wav。"""
    from mimo_mcp.api import tts as api_tts
    from mimo_mcp.config import get_settings
    from mimo_mcp.storage import Storage

    s = get_settings()
    storage = Storage(s.db_path)
    await storage.init()
    await api_tts.seed_default_voices(storage)

    text = (
        "今天是星期三,天气晴朗。"
        "我打算去公园里散步,顺便看看花。"
        "傍晚回家后,我会做一顿丰盛的晚餐。"
    )
    segments = []
    async for seg in api_tts.synthesize_batch(
        text,
        voice="mimo_default",
        segment_max_chars=20,
        storage=storage,
    ):
        segments.append(seg)

    assert len(segments) >= 2, f"期望切出 ≥2 段,实际 {len(segments)}"
    for seg in segments:
        p = Path(seg.audio_path)
        assert p.is_file(), f"段 {seg.index} 文件不存在"
        assert p.read_bytes()[:4] == b"RIFF", f"段 {seg.index} 非 WAV"
        assert seg.bytes > 1000, f"段 {seg.index} 体积异常({seg.bytes})"


