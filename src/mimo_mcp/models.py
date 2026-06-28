"""跨层共享的数据模型。MCP tool 入参 / FastAPI 响应 / SQLite 行结构都以此为准。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class VoiceSource(str, Enum):
    DEFAULT = "default"
    CLONE = "clone"
    DESIGN = "design"


class VoiceStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class VoiceRecord(BaseModel):
    voice_id: str
    name: str
    source: VoiceSource
    status: VoiceStatus = VoiceStatus.READY
    description: str | None = None
    voice_prompt: str | None = None
    reference_path: str | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]]
    name: str | None = None
    tool_call_id: str | None = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None


class ImageInput(BaseModel):
    url: str | None = None
    path: str | None = None
    base64: str | None = None
    mime_type: str = "image/jpeg"


class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None
    voice: str | None = Field(default=None, description="原生 voice 名,例如 mimo_default")
    audio_format: Literal["wav", "mp3", "opus"] = "wav"
    style: str | None = None  # 简易风格词;有 instructions 时以 instructions 为准
    instructions: str | None = Field(
        default=None,
        description="v2.5 自然语言风格指令(支持导演模式),作为 user 消息控制语气/情绪/语速/方言等",
    )


class VoiceCloneCreateRequest(BaseModel):
    reference_audio_path: str
    name: str
    description: str | None = None


class VoiceDesignCreateRequest(BaseModel):
    voice_prompt: str
    name: str
    sample_text: str = "你好,这是 MiMo voice design 的试听样本,欢迎使用。"
    optimize_text_preview: bool = Field(
        default=False,
        description="true 时由模型自动润色目标文本,无需手动提供 sample_text",
    )


class ASRRequest(BaseModel):
    audio_path: str | None = None
    audio_url: str | None = None
    language: str = "auto"  # MiMo ASR(/chat/completions)仅支持 auto / zh / en


class AuditLogEntry(BaseModel):
    id: int | None = None
    ts: datetime
    channel: Literal["mcp", "web"]
    tool: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    status: Literal["ok", "error"] = "ok"
    error: str | None = None


class HealthResult(BaseModel):
    """mimo.health 工具返回值。不包含敏感信息。"""

    api_key_configured: bool
    base_url: str
    base_url_reachable: bool | None = None
    auth_valid: bool | None = None
    asr_cloud_available: bool | None = None
    notes: list[str] = Field(default_factory=list)


class ToolError(BaseModel):
    """统一错误返回。MCP tool / Web API 都用这个结构序列化错误。"""

    code: str
    message: str
    suggestion: str | None = None
