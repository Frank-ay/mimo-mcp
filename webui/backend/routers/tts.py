"""F4 TTS Web 路由(增量任务 1)。

端点:
- POST /api/tts/synthesize  单段一次性,返回 JSON,含 audio_url(可直接给 <audio src>)
- POST /api/tts/batch       长文切段,SSE 流,逐段推送事件
- GET  /api/tts/audio/{filename}  把 data/artifacts/tts 下的产物反代给前端
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from mimo_mcp.api import chat as api_chat
from mimo_mcp.api import tts as api_tts
from mimo_mcp.config import get_settings
from mimo_mcp.models import AuditLogEntry, ChatMessage, ChatRequest, TTSRequest

from ..sse import sse_event

router = APIRouter()


class TTSBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    voice: str | None = None
    voice_id: str | None = None
    audio_format: Literal["wav", "mp3"] = "wav"
    instructions: str | None = None  # v2.5 自然语言风格指令(导演模式)
    style: str | None = None


class BatchBody(TTSBody):
    segment_max_chars: int = Field(default=120, ge=20, le=500)


class RefineBody(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    style: str | None = Field(
        default=None,
        description="可选风格提示,例如'纪录片旁白'/'活泼播报'/'古典朗诵'",
    )


# 系统提示:让 v2.5-pro 把书面语改写成"适合 TTS 朗读"的版本
# 实测发现 MiMo TTS 不识别 <emotion> / [tag] 等 inline 控制标签,
# 但对标点 + 口语化文字敏感(自动从标点推断情感)。所以这里的策略:
#   只动文字本身和标点,不加任何标签。
_REFINE_SYSTEM = """\
你是 MiMo TTS 的文本预处理专家。我会给你一段原文,你的任务是把它改写成
"更适合朗读"的版本。MiMo TTS 会从标点和句子结构自动推断情感、节奏、停顿,
所以**改写的核心是把文字打磨得更口语化、更易于自然朗读**。

允许做(应该做):
- 把书面语改成口语,使其念出来通顺、不拗口
- 补全合理的标点(逗号、句号、问号、感叹号、顿号、省略号、破折号)
- 把数字 / 缩写 / 单位改成口语形式:"2026" → "二零二六","AI" → "人工智能",
  "10kg" → "十公斤"
- 把易错字、同音字、错别字改对(他/她/它,的/得/地)
- 长句子拆短;过短的句子如果朗读突兀可适当补连接词
- 可以加 "(停顿)" / "嗯..." / "啊..." 之类拟声词,**前提是内嵌后读起来自然**

不要做:
- 不改变原意 / 不删减重要信息
- 不要加任何 XML / HTML / markdown 标记(<emotion>、[laugh] 等会被当字面读出来,效果反而差)
- 不要写解释、注释、前后缀(直接输出改写结果即可)
- 不要把英文人名 / 专有名词强行翻译

输出格式:**只输出改写后的纯文本**,无任何说明。
"""


async def _refine_text_via_chat(text: str, style: str | None) -> tuple[str, dict]:
    """调 v2.5-pro 改写文本。返回 (改写后文本, usage 元数据)。"""
    settings = get_settings()
    user_msg = text if not style else f"风格提示:{style}\n\n原文:\n{text}"
    req = ChatRequest(
        messages=[
            ChatMessage(role="system", content=_REFINE_SYSTEM),
            ChatMessage(role="user", content=user_msg),
        ],
        model=settings.default_text_model,  # mimo-v2.5-pro
        max_tokens=8192,  # thinking 模型 + 改写,留宽预算
    )
    resp = await api_chat.chat_completion(req)
    refined = (resp["choices"][0]["message"].get("content") or "").strip()
    if not refined:
        # finish_reason=length 时 content 可能为空(reasoning 吃光),给清晰错误
        finish = resp["choices"][0].get("finish_reason")
        raise HTTPException(
            status_code=502,
            detail=(
                f"v2.5-pro 没有产出改写文本(finish={finish})。"
                "可能 max_tokens 不够或文本过长,请截短后重试。"
            ),
        )
    return refined, resp.get("usage", {})


def _audio_url(audio_path: str) -> str:
    """把绝对/相对 audio_path 转成可被前端 <audio src> 用的 URL。"""
    p = Path(audio_path)
    return f"/api/tts/audio/{p.name}"


async def _record_audit(
    storage: Any,
    *,
    status: Literal["ok", "error"],
    model: str | None,
    error: str | None = None,
    latency_ms: int | None = None,
) -> None:
    try:
        await storage.append_audit(
            AuditLogEntry(
                ts=datetime.now(timezone.utc),
                channel="web",
                tool="mimo.tts",
                model=model,
                latency_ms=latency_ms,
                status=status,
                error=error,
            )
        )
    except Exception:
        # 审计写入失败不影响主流程
        pass


@router.post("/synthesize")
async def synthesize(request: Request, body: TTSBody) -> dict[str, Any]:
    started = time.perf_counter()
    storage = request.app.state.storage
    try:
        result = await api_tts.synthesize(
            TTSRequest(
                text=body.text,
                voice=body.voice,
                voice_id=body.voice_id,
                audio_format=body.audio_format,
                instructions=body.instructions,
                style=body.style,
            ),
            storage,
        )
    except Exception as e:
        latency = int((time.perf_counter() - started) * 1000)
        await _record_audit(storage, status="error", model=None, error=str(e), latency_ms=latency)
        raise HTTPException(status_code=500, detail=f"TTS 合成失败:{e}") from e

    latency = int((time.perf_counter() - started) * 1000)
    await _record_audit(storage, status="ok", model=str(result["model"]), latency_ms=latency)

    return {
        **result,
        "audio_url": _audio_url(str(result["audio_path"])),
    }


@router.post("/batch")
async def batch(request: Request, body: BatchBody) -> StreamingResponse:
    storage = request.app.state.storage
    segments_preview = api_tts.split_text(body.text, body.segment_max_chars)

    async def event_stream() -> Any:
        # 第一帧:先告知前端总段数和切分预览,UI 可立即占位
        yield sse_event("plan", {"total": len(segments_preview), "segments": segments_preview})

        if not segments_preview:
            yield sse_event("done", {})
            return

        try:
            async for seg in api_tts.synthesize_batch(
                body.text,
                voice=body.voice,
                voice_id=body.voice_id,
                audio_format=body.audio_format,
                instructions=body.instructions,
                segment_max_chars=body.segment_max_chars,
                storage=storage,
            ):
                payload = {
                    "index": seg.index,
                    "total": seg.total,
                    "text": seg.text,
                    "audio_url": _audio_url(seg.audio_path),
                    "voice": seg.voice,
                    "source": seg.source,
                    "model": seg.model,
                    "bytes": seg.bytes,
                }
                await _record_audit(storage, status="ok", model=seg.model)
                yield sse_event("segment", payload)
        except Exception as e:
            await _record_audit(storage, status="error", model=None, error=str(e))
            yield sse_event("error", {"message": str(e)})
            return

        yield sse_event("done", {})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/refine")
async def refine_text(request: Request, body: RefineBody) -> dict[str, Any]:
    """用 v2.5-pro 把原文改写成"更适合朗读"的版本。前端可一键回填到文本框。"""
    started = time.perf_counter()
    storage = request.app.state.storage
    try:
        refined, usage = await _refine_text_via_chat(body.text, body.style)
    except HTTPException:
        raise
    except Exception as e:
        latency = int((time.perf_counter() - started) * 1000)
        await _record_audit(
            storage, status="error", model=get_settings().default_text_model,
            error=str(e), latency_ms=latency,
        )
        raise HTTPException(status_code=502, detail=f"改写失败:{e}") from e

    latency = int((time.perf_counter() - started) * 1000)
    await _record_audit(
        storage, status="ok", model=get_settings().default_text_model, latency_ms=latency,
    )
    return {
        "original": body.text,
        "refined": refined,
        "char_count_before": len(body.text),
        "char_count_after": len(refined),
        "latency_ms": latency,
        "tokens": {
            "input": usage.get("prompt_tokens"),
            "output": usage.get("completion_tokens"),
            "reasoning": usage.get("completion_tokens_details", {}).get("reasoning_tokens"),
        },
    }


_ALLOWED_EXT = {".wav", ".mp3", ".pcm", ".opus"}


@router.get("/audio/{filename}")
async def audio(filename: str) -> FileResponse:
    """反代 data/artifacts/tts/<日期>/<filename> 与 voice_refs/<filename>。

    路径校验:严格只允许 [a-zA-Z0-9_-.] 命名 + 白名单后缀,防越权读其他目录。
    """
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"不支持的后缀:{suffix}")

    settings = get_settings()
    candidates: list[Path] = list((settings.artifacts_dir / "tts").rglob(filename))
    candidates.extend((settings.artifacts_dir / "voice_refs").rglob(filename))
    for c in candidates:
        if c.is_file() and c.resolve().is_relative_to(settings.artifacts_dir.resolve()):
            return FileResponse(c, media_type=_mime(suffix))
    raise HTTPException(status_code=404, detail="文件不存在")


def _mime(suffix: str) -> str:
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".pcm": "audio/L16",
        ".opus": "audio/ogg",
    }.get(suffix, "application/octet-stream")
