"""图像 / 视频理解 Web 路由。

视频端点同时接受三种输入,前端二选一即可:
- multipart 文件上传(本地视频)
- form 字段 ``video_url``:直链 mp4 / B 站 / YouTube / 抖音 等

长视频分段分析(2026-05-01):
- POST /api/vision/video/chunked  SSE,绕开 50MB 上限,任意时长视频可分析
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from mimo_mcp.api import vision
from mimo_mcp.client import MimoAPIError
from mimo_mcp.config import get_settings
from mimo_mcp.models import ImageInput

from ..sse import sse_event

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


async def _video_understand_safely(video: str, prompt: str, model: str | None) -> dict:
    """统一错误转换:SDK 各类异常都转成清晰的 4xx + 中文 detail,避免 500 让用户瞎猜。"""
    try:
        return await vision.video_understand(video, prompt, model=model)
    except ValueError as e:
        # 视频过大、本地文件不存在等用户输入问题
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"视频文件不存在:{e}") from e
    except MimoAPIError as e:
        # MiMo 服务端 4xx(过大、参数错、限速等),把它的 message 透传
        status = e.status if 400 <= e.status < 500 else 502
        raise HTTPException(status_code=status, detail=str(e)) from e
    except RuntimeError as e:
        # yt-dlp 下载失败 / ffmpeg 压缩失败 / 其他外部工具问题
        raise HTTPException(status_code=502, detail=str(e)) from e


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
        return await _video_understand_safely(str(target), prompt, model)

    if video_url:
        return await _video_understand_safely(video_url, prompt, model)

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
    return await _video_understand_safely(body.video_url, body.prompt, body.model)


# ---------------------------------------------------------------------------
# 长视频分段分析(SSE 流式返回)
# ---------------------------------------------------------------------------


class ChunkedBody(BaseModel):
    video_url: str | None = None
    prompt: str = Field(..., min_length=1)
    segment_seconds: int = Field(default=50, ge=10, le=120)


async def _chunked_stream(video: str, prompt: str, segment_seconds: int) -> Any:
    """把 video_understand_chunked 的 yield 包装成 SSE 文本流。"""
    try:
        async for evt in vision.video_understand_chunked(
            video, prompt, segment_seconds=segment_seconds,
        ):
            yield sse_event(evt["kind"], evt)
    except (ValueError, FileNotFoundError) as e:
        yield sse_event("error", {"status": 400, "message": str(e)})
    except RuntimeError as e:
        yield sse_event("error", {"status": 502, "message": str(e)})
    except MimoAPIError as e:
        yield sse_event("error", {"status": e.status, "message": str(e)})
    except Exception as e:
        yield sse_event("error", {"status": 500, "message": f"未知错误:{e}"})
    yield sse_event("done", {})


@router.post("/video/chunked")
async def video_chunked_upload(
    prompt: str = Form(...),
    segment_seconds: int = Form(50),
    video_url: str | None = Form(None),
    file: UploadFile | None = None,
) -> StreamingResponse:
    """长视频分段分析(突破 50 MB 上限)。同时支持文件上传 / URL。"""
    if file is not None and getattr(file, "filename", None):
        target = _save_upload(file, "longvid")
        target.write_bytes(await file.read())
        video_input: str = str(target)
    elif video_url:
        video_input = video_url
    else:
        raise HTTPException(
            status_code=400,
            detail="必须提供 file(本地视频)或 video_url 之一",
        )

    if not (10 <= segment_seconds <= 120):
        raise HTTPException(
            status_code=400, detail="segment_seconds 必须在 10-120 秒之间"
        )

    return StreamingResponse(
        _chunked_stream(video_input, prompt, segment_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/video/chunked/url")
async def video_chunked_via_json(body: ChunkedBody) -> StreamingResponse:
    """JSON 路径(脚本/curl 友好)。"""
    if not body.video_url:
        raise HTTPException(status_code=400, detail="video_url 必填")
    return StreamingResponse(
        _chunked_stream(body.video_url, body.prompt, body.segment_seconds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# 视频元信息探针(metadata-only,不下载视频本体)
# ---------------------------------------------------------------------------


class ProbeBody(BaseModel):
    video_url: str


@router.post("/video/probe")
async def video_probe(body: ProbeBody) -> dict[str, Any]:
    """探视频元信息(仅 metadata,不下载视频)。

    前端在用户贴 URL 后调用此端点拿到时长 / 标题 / UP 主等信息,
    据此提示是否需要切到「长视频分段分析」模式。
    """
    import asyncio

    url = body.video_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="video_url 必填")

    if url.startswith("data:"):
        return {"kind": "data_url", "duration": None, "title": None}

    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="必须是 http(s) URL 或 data: URL")

    if vision._is_page_host(url):
        # B 站 / YouTube / 抖音 等:用 yt-dlp 仅拉 metadata
        import yt_dlp

        loop = asyncio.get_event_loop()

        def _do_probe() -> dict[str, Any]:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noprogress": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info or {}

        try:
            info = await loop.run_in_executor(None, _do_probe)
        except yt_dlp.utils.DownloadError as e:
            raise HTTPException(
                status_code=400,
                detail=f"无法读取该 URL 元信息(可能登录视频/反爬/失效):{e}",
            ) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"探针失败:{e}") from e

        duration = info.get("duration")
        return {
            "kind": "page",
            "duration": float(duration) if duration is not None else None,
            "title": info.get("title"),
            "uploader": info.get("uploader") or info.get("channel"),
            "thumbnail": info.get("thumbnail"),
            "extractor": info.get("extractor_key") or info.get("extractor"),
        }

    # 直链:HEAD 拿 content-length(无法可靠拿时长,只能给体积参考)
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
            resp = await c.head(url)
        ct = resp.headers.get("content-type", "")
        cl = resp.headers.get("content-length")
        return {
            "kind": "direct",
            "duration": None,
            "size": int(cl) if cl and cl.isdigit() else None,
            "content_type": ct,
        }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"无法访问 URL:{e}") from e
