"""F8 健康检查与用量统计。

mimo.health:不消耗 token 的探测;
mimo.usage:从本地 audit_log 聚合 + 平台余额(M1 阶段实测 endpoint)。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..client import MimoClient
from ..config import get_settings
from ..models import HealthResult
from .asr import cloud_available


async def health_check() -> HealthResult:
    settings = get_settings()
    result = HealthResult(
        api_key_configured=settings.has_api_key,
        base_url=settings.base_url,
    )
    if not settings.has_api_key:
        result.notes.append("未配置 MIMO_API_KEY,请编辑 .env 后重启。")
        return result

    async with MimoClient(settings) as client:
        result.base_url_reachable = await client.ping()
        if result.base_url_reachable:
            result.auth_valid = await client.auth_check()
            if result.auth_valid:
                # 鉴权通过才探测 ASR 可用性,复用同一连接
                result.asr_cloud_available = await cloud_available(client)
        else:
            result.notes.append("base_url 不可达,检查网络或 MIMO_BASE_URL。")

    if result.auth_valid is False:
        result.notes.append("API Key 无效或已过期,请重新生成。")

    if result.asr_cloud_available:
        result.notes.append(f"F7 ASR 可用(模型 {settings.default_asr_model})。")
    elif result.auth_valid:
        result.notes.append(
            "F7 ASR 不可用:账号 /models 未包含 "
            f"{settings.default_asr_model}(Token Plan 套餐应含,请检查 MIMO_BASE_URL / 套餐)。"
        )
    return result


async def usage_summary(since_hours: int = 24, storage: Any = None) -> dict[str, Any]:
    """本地 audit_log 聚合。M1 阶段叠加平台余额。"""
    if storage is None:
        return {"calls": 0, "since_hours": since_hours, "note": "storage 未初始化"}

    rows = await storage.recent_audit(limit=500)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    recent = [r for r in rows if datetime.fromisoformat(r["ts"]) >= cutoff]

    total_in = sum((r.get("input_tokens") or 0) for r in recent)
    total_out = sum((r.get("output_tokens") or 0) for r in recent)
    errors = sum(1 for r in recent if r.get("status") == "error")

    return {
        "since_hours": since_hours,
        "calls": len(recent),
        "errors": errors,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "by_tool": _group_by_tool(recent),
    }


def _group_by_tool(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r["tool"]] = out.get(r["tool"], 0) + 1
    return out
