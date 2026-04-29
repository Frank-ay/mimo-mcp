"""聊天沙盒。"""

from __future__ import annotations

from fastapi import APIRouter

from mimo_mcp.api import chat as api_chat
from mimo_mcp.models import ChatRequest

router = APIRouter()


@router.post("")
async def chat(req: ChatRequest) -> dict:
    return await api_chat.chat_completion(req)
