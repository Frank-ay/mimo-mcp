"""公共媒体工具函数:ffprobe 探针 + audio DataURL 编码。

本模块集中了 asr / vision / tts / voice_clone 中重复的底层工具,
避免各模块分别维护几乎逐字相同的实现。

公开 API
--------
probe_duration(path)        → float      ffprobe 探时长(音频或视频均可)
probe_video_codec(path)     → str | None ffprobe 探视频流 codec
audio_data_url(path, mime)  → str        本地音频文件 → base64 DataURL
"""

from __future__ import annotations

import asyncio
import base64
import shutil
from pathlib import Path


async def probe_duration(path: Path) -> float:
    """ffprobe 探媒体时长(秒)。

    音频与视频均适用(`format=duration` 对两者都生效)。
    未安装 ffprobe、命令失败或输出无法解析时返回 ``0.0``。
    """
    if shutil.which("ffprobe") is None:
        return 0.0
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        return float(out.decode().strip())
    except (ValueError, AttributeError):
        return 0.0


async def probe_video_codec(path: Path) -> str | None:
    """ffprobe 探视频第一流的 codec_name。

    未安装 ffprobe、命令失败或无视频流时返回 ``None``(原 vision.py 返回空串;
    此处统一为 ``None`` 以便布尔判断更直观,调用方已同步更新)。
    """
    if shutil.which("ffprobe") is None:
        return None
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "csv=p=0",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    result = out.decode("utf-8", errors="replace").strip().lower()
    return result if result else None


def audio_data_url(path: Path, mime: str = "audio/wav") -> str:
    """本地音频文件 → ``data:{mime};base64,{b64}`` 形式的 DataURL。

    与原 tts._data_url / voice_clone._data_url 行为完全一致。
    """
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"
