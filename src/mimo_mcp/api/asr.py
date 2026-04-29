"""F7 ASR 语音转写。

M0 占位 — 决策见 PRD §15-Q6:**仅 MiMo 云端,不预置本地兜底**。
M1 实测:① 优先尝试 /v1/audio/transcriptions;② 若云端 API 不存在,
       则 mimo.health 报告 asr_cloud_available=False,工具直接返回友好错误。
"""

from __future__ import annotations

from ..models import ASRRequest


async def transcribe(req: ASRRequest) -> dict[str, str]:
    raise NotImplementedError(
        "F7 ASR 将在 M1 阶段实测 MiMo 云端转写接口后填充。"
        "若官方未开放云端 ASR API,工具会持续返回 unavailable 状态。"
    )


async def cloud_available() -> bool:
    """探测 MiMo 是否开放云端 ASR(M1 阶段实测后填充)。M0:始终 False。"""
    return False
