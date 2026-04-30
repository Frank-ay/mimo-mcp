"""F2 图像理解 / F3 视频理解。

视频输入(2026-04-30 升级):
统一以 `video` 参数接受 4 种形式,内部自动归一为 MiMo 的 `video_url` 字段:

1. ``data:video/mp4;base64,...``  → 原样下发
2. ``https://example.com/clip.mp4``(直链)→ 原样下发
3. ``https://www.bilibili.com/...`` 等视频站 → ``yt-dlp`` 下载到本地后转 DataURL
4. ``/path/to/local.mp4``(绝对/相对路径,~ 也可)→ 读文件后转 DataURL

DataURL 路线已 Phase 0 实测可行(见 docs/api-research.md)。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..client import MimoClient
from ..config import get_settings
from ..models import ImageInput

log = logging.getLogger(__name__)

# 已知"页面型"视频网站:不能直接喂给 MiMo,要先 yt-dlp 下载
_PAGE_HOSTS: tuple[str, ...] = (
    "bilibili.com",
    "b23.tv",
    "youtube.com",
    "youtu.be",
    "douyin.com",
    "iesdouyin.com",
    "tiktok.com",
    "vimeo.com",
    "weibo.com",
    "xiaohongshu.com",
    "ixigua.com",
    "v.qq.com",
)

# DataURL 规模上限(50 MB 原始字节,base64 后 ~67 MB)
_MAX_VIDEO_BYTES = 50 * 1024 * 1024


def _image_to_url_field(img: ImageInput) -> dict[str, Any]:
    if img.url:
        return {"type": "image_url", "image_url": {"url": img.url}}
    if img.base64:
        prefix = f"data:{img.mime_type};base64,"
        return {"type": "image_url", "image_url": {"url": prefix + img.base64}}
    if img.path:
        path = Path(img.path).expanduser().resolve()
        mime = img.mime_type or mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
    raise ValueError("ImageInput 至少需要 url / base64 / path 之一")


async def image_understand(
    images: list[ImageInput],
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend(_image_to_url_field(img) for img in images)

    body = {
        "model": model or settings.default_vision_model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens or settings.default_max_tokens,
    }
    async with MimoClient(settings) as client:
        return await client.chat(body)


# ---------------------------------------------------------------------------
# 视频输入归一化
# ---------------------------------------------------------------------------


def _path_to_data_url(path: Path) -> str:
    """本地文件 → data:video/mp4;base64,... 形式的 DataURL。"""
    if not path.is_file():
        raise FileNotFoundError(f"本地视频不存在:{path}")
    size = path.stat().st_size
    if size > _MAX_VIDEO_BYTES:
        raise ValueError(
            f"视频过大({size / 1024 / 1024:.1f} MB),超出 {_MAX_VIDEO_BYTES // 1024 // 1024} MB 上限。"
            "请截短或降采样后再传。"
        )
    mime = mimetypes.guess_type(path.name)[0] or "video/mp4"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_page_host(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(h in host for h in _PAGE_HOSTS)


async def _yt_dlp_download(url: str) -> Path:
    """用 yt-dlp 把 B 站 / YouTube / 抖音 等视频站的链接下载成本地 mp4。"""
    import yt_dlp  # 延迟导入,避免无视频任务时也加载

    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "uploads" / today
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"yt_{uuid.uuid4().hex[:10]}"
    out_template = str(out_dir / f"{stem}.%(ext)s")

    # 优先选体积适中的 mp4,避免 4K 几百 MB 一下吃满 DataURL 上限
    ydl_opts = {
        "format": "best[ext=mp4][filesize<40M]/best[filesize<40M]/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "merge_output_format": "mp4",
    }

    def _do_download() -> str:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    log.info("yt-dlp 下载:%s", url)
    loop = asyncio.get_event_loop()
    try:
        path_str = await loop.run_in_executor(None, _do_download)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(
            f"yt-dlp 下载失败:{e}。可能是登录视频/反爬/失效链接,请改用本地 mp4 或直链。"
        ) from e

    final = Path(path_str)
    # yt-dlp 可能 merge 后扩展名变化,fallback 找匹配文件
    if not final.is_file():
        candidates = list(out_dir.glob(f"{stem}.*"))
        if candidates:
            final = candidates[0]
        else:
            raise RuntimeError(f"yt-dlp 下载完成但找不到产物文件:{path_str}")
    log.info("yt-dlp 下载完成:%s (%d bytes)", final, final.stat().st_size)
    return final


async def _download_direct(url: str) -> Path:
    """把直链 mp4(http(s) 静态文件)下载到本地。"""
    import httpx

    settings = get_settings()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    out_dir = settings.artifacts_dir / "uploads" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".mp4"
    out = out_dir / f"dl_{uuid.uuid4().hex[:10]}{suffix}"

    log.info("直链下载:%s → %s", url, out)
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
        async with c.stream("GET", url) as resp:
            resp.raise_for_status()
            written = 0
            with out.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    written += len(chunk)
                    if written > _MAX_VIDEO_BYTES:
                        out.unlink(missing_ok=True)
                        raise ValueError(
                            f"远端文件超 {_MAX_VIDEO_BYTES // 1024 // 1024} MB,已中止"
                        )
    return out


async def resolve_video_input(video: str) -> str:
    """把任意视频输入归一化为 MiMo 接受的 video_url 字段值。

    所有非 DataURL 输入最终都转成 base64 DataURL 下发——MiMo 服务器对外网 URL 的
    主动下载不稳定(实测过会随机 400 'failed to download url data'),自己下载更可靠。
    """
    if not video or not isinstance(video, str):
        raise ValueError("video 输入不能为空")

    # 1) 已经是 DataURL,原样
    if video.startswith("data:"):
        return video

    # 2/3) http(s)
    if video.startswith(("http://", "https://")):
        if _is_page_host(video):
            local = await _yt_dlp_download(video)
        else:
            local = await _download_direct(video)
        return _path_to_data_url(local)

    # 4) 本地路径
    path = Path(video).expanduser().resolve()
    return _path_to_data_url(path)


async def video_understand(
    video: str,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """视频理解。

    `video` 可以是直链 URL、B 站等视频站 URL、本地路径、DataURL —— 一律自动转换。

    视频会被拆出 video_tokens + audio_tokens 单独计费;v2.5 系列是 thinking 模型,
    默认 max_tokens 4096(可视化任务建议设到 6000+)。
    """
    settings = get_settings()
    url_field = await resolve_video_input(video)

    body = {
        "model": model or settings.default_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "video_url": {"url": url_field}},
                ],
            }
        ],
        "max_tokens": max_tokens or settings.default_max_tokens,
    }
    async with MimoClient(settings) as client:
        return await client.chat(body)
