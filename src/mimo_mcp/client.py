"""MimoClient:小米 MiMo HTTP 客户端,异步 httpx 实现。

设计原则:
- 只暴露 OpenAI 兼容的"原始"端点(chat / audio.speech / audio.transcriptions / files 等)
- 不在这一层做业务编排(Voice 库管理、文件落盘等放 api/* 层)
- M0 阶段:基础 HTTP 客户端 + chat 已就绪;TTS / 克隆 / ASR 等待 M1 用真 key 实测后填充
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .config import MimoSettings, get_settings

log = logging.getLogger(__name__)


class MimoAPIError(RuntimeError):
    def __init__(self, status: int, message: str, code: str | None = None) -> None:
        super().__init__(f"[{status}] {message}")
        self.status = status
        self.message = message
        self.code = code


class MimoClient:
    def __init__(self, settings: MimoSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> MimoClient:
        self._client = httpx.AsyncClient(
            base_url=self.settings.base_url,
            timeout=self.settings.http_timeout,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "User-Agent": "mimo-mcp/0.1.0",
            },
        )
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("MimoClient 未通过 async with 启动")
        return self._client

    @staticmethod
    def _check(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            payload = resp.json()
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            msg = err.get("message") or resp.text
            code = err.get("code")
        except Exception:
            msg = resp.text
            code = None
        raise MimoAPIError(resp.status_code, msg, code)

    async def chat(self, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self.client.post("/chat/completions", json=body)
        self._check(resp)
        return resp.json()

    async def chat_stream(self, body: dict[str, Any]) -> AsyncIterator[str]:
        body = {**body, "stream": True}
        async with self.client.stream("POST", "/chat/completions", json=body) as resp:
            self._check(resp)
            async for line in resp.aiter_lines():
                if line:
                    yield line

    async def ping(self) -> bool:
        """轻量探测:只检查 base_url 可达性,不消耗 token。"""
        try:
            resp = await self.client.get("/models", timeout=10.0)
            return resp.status_code in (200, 401, 403)
        except httpx.HTTPError:
            return False

    async def auth_check(self) -> bool:
        """用最小请求验证 key 是否合法(消耗极少 token,M1 阶段会改为更轻的 endpoint)。"""
        try:
            resp = await self.client.get("/models", timeout=15.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    # M1 实测确认的 schema:
    # - TTS / VoiceClone / VoiceDesign 都走 /chat/completions
    # - messages 里要朗读的文本放在 role=assistant 消息里
    # - audio.voice 取 voice_id 或预置名;audio.format 目前确认 wav
    # - 响应里 choices[0].message.audio.data 是 base64,需解码

    async def tts(
        self,
        text: str,
        voice: str,
        *,
        model: str,
        audio_format: str = "wav",
        extra_audio: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audio: dict[str, Any] = {"voice": voice, "format": audio_format}
        if extra_audio:
            audio.update(extra_audio)
        body = {
            "model": model,
            "messages": [{"role": "assistant", "content": text}],
            "audio": audio,
            "modalities": ["text", "audio"],
        }
        resp = await self.client.post("/chat/completions", json=body)
        self._check(resp)
        return resp.json()

    async def voice_design(
        self,
        voice_prompt: str,
        sample_text: str,
        *,
        model: str,
        audio_format: str = "wav",
    ) -> dict[str, Any]:
        """voicedesign 模型:user 消息描述音色,assistant 消息是要朗读的样本文本。"""
        body = {
            "model": model,
            "messages": [
                {"role": "user", "content": voice_prompt},
                {"role": "assistant", "content": sample_text},
            ],
            "audio": {"format": audio_format},
            "modalities": ["text", "audio"],
        }
        resp = await self.client.post("/chat/completions", json=body)
        self._check(resp)
        return resp.json()

    async def voice_clone(
        self,
        text: str,
        reference_data_url: str,
        *,
        model: str,
        audio_format: str = "wav",
    ) -> dict[str, Any]:
        """voiceclone 模型:audio.voice 必须是 DataURL(data:audio/wav;base64,...)。"""
        body = {
            "model": model,
            "messages": [{"role": "assistant", "content": text}],
            "audio": {"voice": reference_data_url, "format": audio_format},
            "modalities": ["text", "audio"],
        }
        resp = await self.client.post("/chat/completions", json=body)
        self._check(resp)
        return resp.json()
