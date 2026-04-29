"""F1 多模态对话。"""

from __future__ import annotations

from typing import Any

from ..client import MimoClient
from ..config import get_settings
from ..models import ChatRequest


async def chat_completion(req: ChatRequest) -> dict[str, Any]:
    settings = get_settings()
    body: dict[str, Any] = {
        "model": req.model or settings.default_text_model,
        "messages": [m.model_dump(exclude_none=True) for m in req.messages],
    }
    if req.temperature is not None:
        body["temperature"] = req.temperature
    if req.top_p is not None:
        body["top_p"] = req.top_p
    # v2.5 系列是 thinking 模型,reasoning_tokens 会先吃掉 max_tokens。
    # 调用方未显式指定时,自动用 settings 的 default_max_tokens(默认 4096)。
    body["max_tokens"] = req.max_tokens if req.max_tokens is not None else settings.default_max_tokens
    if req.tools:
        body["tools"] = req.tools

    async with MimoClient(settings) as client:
        return await client.chat(body)
