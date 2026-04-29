"""Dashboard:健康 + 用量。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from mimo_mcp.api import usage as api_usage

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    result = await api_usage.health_check()
    return result.model_dump(mode="json")


@router.get("/summary")
async def summary(request: Request, since_hours: int = 24) -> dict:
    return await api_usage.usage_summary(since_hours, request.app.state.storage)


@router.get("/audit")
async def audit(request: Request, limit: int = 100) -> list[dict]:
    return await request.app.state.storage.recent_audit(limit=limit)
