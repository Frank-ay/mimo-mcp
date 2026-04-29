"""F2 图像理解 / F3 视频理解。

M0 阶段:基于"messages 内嵌 image_url / video_url"的 OpenAI 风格构造,真实字段名等
M1 阶段实测后再校准(参考 PRD §14 风险表)。
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from ..client import MimoClient
from ..config import get_settings
from ..models import ImageInput


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

    # v2.5 是 thinking 模型,默认 max_tokens 必须给足才能跑完思考
    body = {
        "model": model or settings.default_vision_model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens or settings.default_max_tokens,
    }
    async with MimoClient(settings) as client:
        return await client.chat(body)


async def video_understand(
    video_url: str,
    prompt: str,
    *,
    model: str | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """视频理解。M1 实测确认:走 v2.5 + content 数组里 `{type:video_url, video_url:{url}}`。

    视频会被拆出 video_tokens 与 audio_tokens 单独计费,且 thinking 模型容易吃光预算,
    所以默认 max_tokens 与 chat 共享(4096)。
    """
    settings = get_settings()
    body = {
        "model": model or settings.default_vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "video_url", "video_url": {"url": video_url}},
                ],
            }
        ],
        "max_tokens": max_tokens or settings.default_max_tokens,
    }
    async with MimoClient(settings) as client:
        return await client.chat(body)
