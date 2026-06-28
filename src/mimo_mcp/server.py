"""FastMCP stdio server。注册 PRD §7 中的 11 个 tool。

启动:
    uv run mimo-mcp                  # 由 [project.scripts] 入口
    python -m mimo_mcp.server        # 直接模块方式

向 Claude Code / Codex 注册见 README §3。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .api import asr as api_asr
from .api import chat as api_chat
from .api import tts as api_tts
from .api import usage as api_usage
from .api import vision as api_vision
from .api import voice_clone as api_voice_clone
from .api import voice_design as api_voice_design
from .config import get_settings
from .logging_setup import configure_logging
from .models import (
    ASRRequest,
    AuditLogEntry,
    ChatMessage,
    ChatRequest,
    ImageInput,
    TTSRequest,
    VoiceCloneCreateRequest,
    VoiceDesignCreateRequest,
    VoiceSource,
)
from .storage import Storage

log = logging.getLogger("mimo_mcp.server")

INSTRUCTIONS = """\
小米 MiMo MCP Server。提供 11 个 tool:

- mimo.chat / mimo.image_understand / mimo.video_understand:基于 MiMo-V2.5 全模态对话与理解
- mimo.tts / mimo.voice_clone_create / mimo.voice_design_create:语音合成与音色管理
- mimo.voice_list / mimo.voice_delete:本地音色库
- mimo.asr:语音转写(mimo-v2.5-asr,支持本地路径 / 直链,language 可选 auto/zh/en)
- mimo.health / mimo.usage:健康检查与用量

调用约定:大文件请传"本地路径"或"http(s) URL",不要在 stdio 协议里塞 base64 大对象。
"""

mcp = FastMCP(name="mimo-mcp", instructions=INSTRUCTIONS)
_storage: Storage | None = None


def _get_storage() -> Storage:
    global _storage
    if _storage is None:
        settings = get_settings()
        _storage = Storage(settings.db_path)
    return _storage


async def _audit(tool: str, status: str, *, error: str | None = None,
                 model: str | None = None, latency_ms: int | None = None) -> None:
    try:
        storage = _get_storage()
        await storage.append_audit(
            AuditLogEntry(
                ts=datetime.now(timezone.utc),
                channel="mcp",
                tool=tool,
                model=model,
                latency_ms=latency_ms,
                status=status,  # type: ignore[arg-type]
                error=error,
            )
        )
    except Exception as e:  # pragma: no cover
        log.warning("audit log 写入失败:%s", e)


# ---------------------------------------------------------------------------
# F1 Chat
# ---------------------------------------------------------------------------
@mcp.tool(name="mimo.chat", description="多模态对话。messages 兼容 OpenAI 格式,可混入图像/视频。")
async def mimo_chat(
    messages: Annotated[list[dict[str, Any]], Field(description="OpenAI 风格 messages 数组")],
    model: Annotated[str | None, Field(description="覆盖默认 mimo-v2.5-pro")] = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    req = ChatRequest(
        messages=[ChatMessage(**m) for m in messages],
        model=model,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        tools=tools,
    )
    try:
        result = await api_chat.chat_completion(req)
        await _audit("mimo.chat", "ok", model=req.model)
        return result
    except Exception as e:
        await _audit("mimo.chat", "error", error=str(e))
        raise


# ---------------------------------------------------------------------------
# F2 Image
# ---------------------------------------------------------------------------
@mcp.tool(name="mimo.image_understand", description="图像理解。images 数组每项可选 url/path/base64。")
async def mimo_image_understand(
    images: list[dict[str, Any]],
    prompt: str,
    model: str | None = None,
) -> dict[str, Any]:
    inputs = [ImageInput(**i) for i in images]
    try:
        result = await api_vision.image_understand(inputs, prompt, model=model)
        await _audit("mimo.image_understand", "ok", model=model)
        return result
    except Exception as e:
        await _audit("mimo.image_understand", "error", error=str(e))
        raise


# ---------------------------------------------------------------------------
# F3 Video
# ---------------------------------------------------------------------------
@mcp.tool(
    name="mimo.video_understand",
    description=(
        "视频理解。video 参数支持 4 种形式自动识别:"
        "(a) 直链 mp4 URL;(b) B 站/YouTube/抖音/小红书等视频站链接(yt-dlp 自动下载);"
        "(c) 本地路径(绝对/相对/~);(d) data:video/mp4;base64,... DataURL。"
    ),
)
async def mimo_video_understand(
    video: str,
    prompt: str,
    model: str | None = None,
) -> dict[str, Any]:
    try:
        result = await api_vision.video_understand(video, prompt, model=model)
        await _audit("mimo.video_understand", "ok", model=model)
        return result
    except Exception as e:
        await _audit("mimo.video_understand", "error", error=str(e))
        raise


# ---------------------------------------------------------------------------
# F4 TTS
# ---------------------------------------------------------------------------
@mcp.tool(
    name="mimo.tts",
    description=(
        "文本合成语音。voice 选预置(mimo_default/冰糖/茉莉/苏打/白桦/Mia/Chloe/Milo/Dean)"
        "或自建 voice_id;instructions 可传自然语言风格指令(v2.5 导演模式:角色/场景/指导);"
        "文本里也可嵌 (风格)/[音频标签]/(唱歌) 标签。返回本地 wav 路径。"
    ),
)
async def mimo_tts(
    text: str,
    voice_id: str | None = None,
    voice: str | None = None,
    audio_format: Literal["wav", "mp3", "opus"] = "wav",
    instructions: str | None = None,
    style: str | None = None,
) -> dict[str, str | int]:
    req = TTSRequest(
        text=text,
        voice_id=voice_id,
        voice=voice,
        audio_format=audio_format,
        instructions=instructions,
        style=style,
    )
    try:
        result = await api_tts.synthesize(req, _get_storage())
        await _audit("mimo.tts", "ok", model=str(result.get("model")))
        return result
    except Exception as e:
        await _audit("mimo.tts", "error", error=str(e))
        raise


# ---------------------------------------------------------------------------
# F5 Voice Clone
# ---------------------------------------------------------------------------
@mcp.tool(name="mimo.voice_clone_create", description="上传参考音频创建克隆音色。立即跑一次试听验证。返回 voice_id 后,在 mimo.tts 里直接传 voice_id=<返回值> 即可用克隆音色朗读任意文本。")
async def mimo_voice_clone_create(
    reference_audio_path: str,
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    req = VoiceCloneCreateRequest(
        reference_audio_path=reference_audio_path,
        name=name,
        description=description,
    )
    try:
        record = await api_voice_clone.create_clone(req, _get_storage())
        await _audit("mimo.voice_clone_create", "ok", model="mimo-v2.5-tts-voiceclone")
        return record.model_dump(mode="json")
    except Exception as e:
        await _audit("mimo.voice_clone_create", "error", error=str(e))
        raise


@mcp.tool(name="mimo.voice_design_create", description="文字描述生成自定义音色 + 试听。MiMo voicedesign 是 stateless 的,本工具会把 prompt 入库以便复用,但每次朗读会基于 prompt 重新合成。")
async def mimo_voice_design_create(
    voice_prompt: str,
    name: str,
    sample_text: str = "你好,这是 MiMo voice design 的试听样本,欢迎使用。",
    optimize_text_preview: bool = False,
) -> dict[str, Any]:
    req = VoiceDesignCreateRequest(
        voice_prompt=voice_prompt,
        name=name,
        sample_text=sample_text,
        optimize_text_preview=optimize_text_preview,
    )
    try:
        record = await api_voice_design.create_design(req, _get_storage())
        await _audit("mimo.voice_design_create", "ok", model="mimo-v2.5-tts-voicedesign")
        return record.model_dump(mode="json")
    except Exception as e:
        await _audit("mimo.voice_design_create", "error", error=str(e))
        raise


@mcp.tool(name="mimo.voice_list", description="列出本地音色库(默认 + 克隆 + 设计)。")
async def mimo_voice_list(source: str | None = None) -> list[dict[str, Any]]:
    src = VoiceSource(source) if source else None
    voices = await _get_storage().list_voices(src)
    await _audit("mimo.voice_list", "ok")
    return [v.model_dump(mode="json") for v in voices]


@mcp.tool(name="mimo.voice_delete", description="从本地音色库删除。")
async def mimo_voice_delete(voice_id: str) -> dict[str, bool]:
    ok = await _get_storage().delete_voice(voice_id)
    await _audit("mimo.voice_delete", "ok" if ok else "error",
                 error=None if ok else "not_found")
    return {"deleted": ok}


# ---------------------------------------------------------------------------
# F7 ASR
# ---------------------------------------------------------------------------
@mcp.tool(
    name="mimo.asr",
    description=(
        "语音转写(F7)。传 audio_path(本地文件)或 audio_url(直链)之一,"
        "language 可选 auto / zh / en。默认走 mimo-v2.5-asr,返回纯文本。"
    ),
)
async def mimo_asr(
    audio_path: str | None = None,
    audio_url: str | None = None,
    language: str = "auto",
) -> dict[str, Any]:
    req = ASRRequest(
        audio_path=audio_path,
        audio_url=audio_url,
        language=language,
    )
    try:
        result = await api_asr.transcribe(req)
        await _audit("mimo.asr", "ok", model=result.get("model"))
        return result
    except Exception as e:
        await _audit("mimo.asr", "error", error=str(e))
        raise


# ---------------------------------------------------------------------------
# F8 Health & Usage
# ---------------------------------------------------------------------------
@mcp.tool(name="mimo.health", description="健康检查:配置 / 网络 / 鉴权 / ASR 云端可用性。")
async def mimo_health() -> dict[str, Any]:
    result = await api_usage.health_check()
    await _audit("mimo.health", "ok")
    return result.model_dump(mode="json")


@mcp.tool(name="mimo.usage", description="本地 audit_log 聚合的最近用量。")
async def mimo_usage(since_hours: int = 24) -> dict[str, Any]:
    return await api_usage.usage_summary(since_hours, _get_storage())


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
async def _bootstrap() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, stderr_only=True)
    storage = _get_storage()
    await storage.init()
    seeded = await api_tts.seed_default_voices(storage)
    log.info("mimo-mcp 启动:base_url=%s key=%s default_voices=%d",
             settings.base_url, "set" if settings.has_api_key else "MISSING", seeded)


def main() -> None:
    asyncio.run(_bootstrap())
    mcp.run()  # 默认 stdio transport


if __name__ == "__main__":
    main()
