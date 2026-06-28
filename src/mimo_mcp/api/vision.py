"""F2 图像理解 / F3 视频理解。

视频输入(2026-04-30 升级):
统一以 `video` 参数接受 4 种形式,内部自动归一为 MiMo 的 `video_url` 字段:

1. ``data:video/mp4;base64,...``  → 原样下发
2. ``https://example.com/clip.mp4``(直链)→ 原样下发
3. ``https://www.bilibili.com/...`` 等视频站 → ``yt-dlp`` 下载到本地后转 DataURL
4. ``/path/to/local.mp4``(绝对/相对路径,~ 也可)→ 读文件后转 DataURL

DataURL 路线已 Phase 0 实测可行(实测见 docs/USAGE.md 附录:API 实测备注)。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..client import MimoClient
from ..config import get_settings
from ..models import ImageInput
from ._media import probe_duration, probe_video_codec

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

# MiMo 实测限制:base64 后视频内容 ≤ 50 MB(2026-04-30 实测错误信息确认)
# base64 编码膨胀 ~1.34x,所以原始字节 ≤ 37 MB 才安全。留点 buffer 设 35 MB。
_MAX_VIDEO_BYTES = 35 * 1024 * 1024

# 自动压缩参数:超过原始字节 ≤ 35MB 时尝试 ffmpeg 降采样
_AUTO_COMPRESS_TRIGGER = _MAX_VIDEO_BYTES  # 同上限,方便理解
_COMPRESS_MAX_DURATION = 90  # 秒,超过会被截短
_COMPRESS_MAX_DIM = 720  # 长边 ≤ 720,降低分辨率
_COMPRESS_CRF = 28  # 质量,数字越大文件越小(28 是中等质量)


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


# MiMo vision 兼容的视频编码白名单(实测 AV1 会报 "Multimodal data is corrupted")
_COMPATIBLE_CODECS = {"h264", "avc1", "hevc", "h265"}


async def _ffmpeg_reencode(
    src: Path,
    *,
    max_duration: int | None = None,
    suffix: str = "_reencoded",
) -> Path:
    """ffmpeg 重编码到 H.264 + 720p + CRF 28 mp4。

    ``max_duration`` 给数字时会截短(单段模式压缩用),给 ``None`` 时保留完整时长(只换编码,
    给 yt-dlp 兜底 codec 转换用,**不能丢内容**)。
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg 未安装,无法处理视频。请先 `brew install ffmpeg` 后重试。"
        )

    out = src.with_name(f"{src.stem}{suffix}.mp4")
    log.info(
        "ffmpeg 重编码:%s (%.1f MB) → %s (max_duration=%s)",
        src.name, src.stat().st_size / 1024 / 1024, out.name, max_duration,
    )

    scale = (
        f"scale='min({_COMPRESS_MAX_DIM},iw)':'min({_COMPRESS_MAX_DIM},ih)':"
        "force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    cmd: list[str] = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
    ]
    if max_duration is not None:
        cmd += ["-t", str(max_duration)]
    cmd += [
        "-vf", scale,
        "-c:v", "libx264", "-crf", str(_COMPRESS_CRF), "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",
        str(out),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        err_txt = stderr.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"ffmpeg 重编码失败:{err_txt}")
    new_size = out.stat().st_size
    log.info(
        "重编码完成:%.1f MB → %.1f MB",
        src.stat().st_size / 1024 / 1024, new_size / 1024 / 1024,
    )
    return out


async def _ffmpeg_compress(src: Path) -> Path:
    """单段模式压缩:截短到 90 秒 + 长边 720p + CRF 28。

    **会丢掉 90 秒之后的内容**,仅当确定走单段流程才用。长视频走分段不要调这个。
    """
    return await _ffmpeg_reencode(
        src, max_duration=_COMPRESS_MAX_DURATION, suffix="_compressed",
    )


async def _ffmpeg_transcode_only(src: Path) -> Path:
    """只转编码格式(AV1 → H.264)+ 缩 720p,保留**完整时长**,不丢内容。"""
    return await _ffmpeg_reencode(src, max_duration=None, suffix="_h264")


async def _path_to_data_url(path: Path) -> str:
    """本地文件 → data:video/mp4;base64,... 形式的 DataURL(单段模式入口)。

    单段模式两条硬约束:
    - **时长 ≤ 90 秒**(MiMo 服务端限制,即便 size 不大,长视频也会被解读为空)
    - **体积 base64 后 ≤ 50 MB**(原始 ≤ 35 MB)

    任一不满足都立即抛 ValueError + 引导用户切换到「长视频分段分析」,
    避免默默截短或返回乱码。
    """
    if not path.is_file():
        raise FileNotFoundError(f"本地视频不存在:{path}")
    size = path.stat().st_size

    # 前置硬约束 1:时长。无论 size 多大,>90s 单段都没法分析(MiMo 实测会返回空内容)
    duration = await probe_duration(path)
    if duration > _COMPRESS_MAX_DURATION + 1.0:
        raise ValueError(
            f"视频时长 {duration:.0f} 秒,超过单段分析上限"
            f"({_COMPRESS_MAX_DURATION} 秒)。\n"
            f"\n要分析完整 {duration:.0f} 秒的内容,请改用「长视频分段分析」:\n"
            f"  · Web /vision 页面勾选「长视频分段分析」\n"
            f"  · SDK:video_understand_chunked(...)\n"
            f"  · API:POST /api/vision/video/chunked\n"
            f"\n该模式会自动切段、逐段分析,最后由 v2.5-pro 综合成完整内容。"
        )

    # 前置硬约束 2:体积。超过则压缩(已知时长 ≤ 90s,所以可安全用 _ffmpeg_compress)
    if size > _AUTO_COMPRESS_TRIGGER:
        try:
            path = await _ffmpeg_compress(path)
            size = path.stat().st_size
        except Exception as e:
            max_mb = _MAX_VIDEO_BYTES // 1024 // 1024
            raise ValueError(
                f"视频过大({size / 1024 / 1024:.1f} MB),且自动压缩失败:{e}\n"
                f"请手动截短到 ≤ {max_mb} MB 后重试,例如:\n"
                f"  ffmpeg -i input.mp4 -t 60 -vf scale=720:-2 -c:v libx264 -crf 28 output.mp4"
            ) from e

        if size > _MAX_VIDEO_BYTES:
            max_mb = _MAX_VIDEO_BYTES // 1024 // 1024
            raise ValueError(
                f"压缩后仍超 {max_mb} MB({size / 1024 / 1024:.1f} MB)。"
                "请手动用更激进参数截短视频,或改用「长视频分段分析」模式。"
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

    # B 站等站点常用 dash 分轨道流(video+audio 分开),要让 yt-dlp 自动 merge 成 mp4。
    # format selector 从严到松多重 fallback,保证总能拿到东西:
    #   1) ≤40MB 预合并 mp4
    #   2) ≤40MB 任意预合并
    #   3) bestvideo+bestaudio 分流(filesize 限制单流)
    #   4) 不限大小的 best/bestvideo+bestaudio,后续 ffmpeg 压缩流程兜底
    ydl_opts = {
        "format": (
            "best[ext=mp4][filesize<40M]/"
            "best[filesize<40M]/"
            "bestvideo[ext=mp4][filesize<25M]+bestaudio[ext=m4a]/"
            "bestvideo[filesize<25M]+bestaudio/"
            "best/bestvideo+bestaudio"
        ),
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

    # 兼容性兜底:B 站等站点可能给 AV1 编码,MiMo 解不了。
    # 检测 codec,非 H.264 / H.265 系列就强制转 H.264;**保留完整时长**,
    # 不能用 _ffmpeg_compress(它会截到 90 秒丢内容,这是历史 bug 的根因)。
    codec = await probe_video_codec(final)
    if codec and codec not in _COMPATIBLE_CODECS:
        log.warning(
            "yt-dlp 产物是 %s 编码,MiMo vision 不兼容,转 H.264(保留完整时长)", codec,
        )
        final = await _ffmpeg_transcode_only(final)
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
        return await _path_to_data_url(local)

    # 4) 本地路径
    path = Path(video).expanduser().resolve()
    return await _path_to_data_url(path)


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


# ---------------------------------------------------------------------------
# 长视频分段分析(突破 MiMo 单次 50MB 上限)
# ---------------------------------------------------------------------------


async def _resolve_to_local_path(video: str) -> Path:
    """跟 resolve_video_input 类似但只返回本地路径,**不做压缩**——

    分段流程要拿到原始视频自己切,如果先压缩(截到 90 秒)就把后段丢了。
    """
    if video.startswith("data:"):
        try:
            _header, data = video.split(",", 1)
        except ValueError as e:
            raise ValueError("DataURL 格式错") from e
        settings = get_settings()
        out_dir = settings.artifacts_dir / "uploads" / datetime.now(timezone.utc).strftime("%Y%m%d")
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"data_{uuid.uuid4().hex[:10]}.mp4"
        out.write_bytes(base64.b64decode(data))
        return out

    if video.startswith(("http://", "https://")):
        if _is_page_host(video):
            return await _yt_dlp_download(video)
        return await _download_direct(video)

    path = Path(video).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"本地视频不存在:{path}")
    return path


async def _ffmpeg_segment(src: Path, segment_seconds: int) -> list[tuple[Path, float, float]]:
    """ffmpeg 一次切多段(同时降码到 H.264 + 720p),保证每段 ≤ 35 MB。"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("分段功能需要 ffmpeg,请先 brew install ffmpeg")

    duration = await probe_duration(src)
    if duration <= 0:
        raise RuntimeError(f"无法读取视频时长(可能格式损坏):{src.name}")

    out_dir = src.parent / f"{src.stem}_chunks_{uuid.uuid4().hex[:6]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(out_dir / "part_%03d.mp4")

    scale = (
        f"scale='min({_COMPRESS_MAX_DIM},iw)':'min({_COMPRESS_MAX_DIM},ih)':"
        "force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-vf", scale,
        "-c:v", "libx264", "-crf", str(_COMPRESS_CRF), "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "64k",
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-reset_timestamps", "1",
        "-movflags", "+faststart",
        out_template,
    ]
    log.info("ffmpeg 切段 + 转码:%s → %s/(每段 %ds)",
             src.name, out_dir.name, segment_seconds)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 切段失败:{stderr.decode('utf-8', errors='replace')[:300]}"
        )

    parts = sorted(out_dir.glob("part_*.mp4"))
    if not parts:
        raise RuntimeError("切段成功但找不到产物文件,可能视频太短")

    result: list[tuple[Path, float, float]] = []
    for i, p in enumerate(parts):
        start = float(i * segment_seconds)
        end = min(start + float(segment_seconds), duration)
        result.append((p, start, end))
    return result


async def video_understand_chunked(
    video: str,
    prompt: str,
    *,
    segment_seconds: int = 50,
) -> AsyncIterator[dict[str, Any]]:
    """长视频分段分析,绕开 MiMo 单次 50 MB 上限。

    yield 4 种事件,每个 dict 用 ``kind`` 字段区分:
    - ``plan``:总段数 + 每段时间区间
    - ``segment``:单段处理完(含描述)
    - ``summary``:综合后的完整分析
    """
    from .chat import chat_completion
    from ..models import ChatMessage, ChatRequest

    settings = get_settings()
    src = await _resolve_to_local_path(video)
    duration = await probe_duration(src)
    chunks = await _ffmpeg_segment(src, segment_seconds)
    total = len(chunks)
    log.info("长视频分段:%d 段,总时长 %.1f s", total, duration)

    yield {
        "kind": "plan",
        "total": total,
        "duration": duration,
        "segment_seconds": segment_seconds,
        "segments": [
            {"index": i, "start": s, "end": e, "bytes": p.stat().st_size}
            for i, (p, s, e) in enumerate(chunks)
        ],
    }

    descriptions: list[dict[str, Any]] = []
    for i, (chunk_path, start, end) in enumerate(chunks):
        seg_prompt = (
            f"以下是一段长视频被切出的第 {i + 1}/{total} 段"
            f"(约 {start:.0f}-{end:.0f} 秒)。{prompt}"
        )
        try:
            result = await video_understand(
                str(chunk_path),
                seg_prompt,
                max_tokens=4096,
            )
            desc = (result["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:
            desc = f"(本段分析失败:{e})"
            log.warning("段 %d/%d 分析失败:%s", i + 1, total, e)

        descriptions.append({
            "index": i,
            "start": start,
            "end": end,
            "description": desc,
            "bytes": chunk_path.stat().st_size,
        })
        yield {"kind": "segment", **descriptions[-1]}

    listing = "\n".join(
        f"[{d['start']:.0f}-{d['end']:.0f}秒] {d['description']}" for d in descriptions
    )
    summary_prompt = f"""我把一段时长约 {duration:.0f} 秒的视频按 {segment_seconds} 秒切成了 {total} 段,逐段做了视频理解。请基于下面这 {total} 段描述,综合写出一段**完整、连贯**的视频分析。

要求:
1. 还原视频的整体叙事(开头 → 中间 → 结尾的时间线)
2. 突出关键场景、画面变化、情绪转折
3. 不要逐段重复也不要加段号,要把分段内容融合成一段流畅的中文
4. 用户原始提问:{prompt}

各段描述如下:
{listing}
"""
    try:
        chat_resp = await chat_completion(ChatRequest(
            messages=[ChatMessage(role="user", content=summary_prompt)],
            model=settings.default_text_model,
            max_tokens=8192,
        ))
        summary = (chat_resp["choices"][0]["message"].get("content") or "").strip()
        if not summary:
            finish = chat_resp["choices"][0].get("finish_reason")
            summary = f"(综合输出为空,finish={finish}。请直接看下方各段描述)"
    except Exception as e:
        summary = f"(综合失败:{e}。请直接看下方各段描述)"

    yield {
        "kind": "summary",
        "text": summary,
        "total": total,
        "duration": duration,
        "segments": descriptions,
    }
