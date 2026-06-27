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
            param = err.get("param")
            if param:
                # MiMo 把"具体哪个字段错"放在 param 里,合并入 message 方便定位
                msg = f"{msg} — {param}"
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
        instructions: str | None = None,
        extra_audio: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        audio: dict[str, Any] = {"voice": voice, "format": audio_format}
        if extra_audio:
            audio.update(extra_audio)
        messages: list[dict[str, Any]] = []
        if instructions:
            # v2.5:user 消息传自然语言风格指令,不会出现在合成语音中
            messages.append({"role": "user", "content": instructions})
        messages.append({"role": "assistant", "content": text})
        body = {
            "model": model,
            "messages": messages,
            "audio": audio,
            "modalities": ["text", "audio"],
        }
        resp = await self.client.post("/chat/completions", json=body)
        self._check(resp)
        return resp.json()

    async def voice_design(
        self,
        voice_prompt: str,
        sample_text: str | None = None,
        *,
        model: str,
        audio_format: str = "wav",
        optimize_text_preview: bool = False,
    ) -> dict[str, Any]:
        """voicedesign 模型:user 消息描述音色,assistant 消息是要朗读的样本文本。

        optimize_text_preview=True 时由模型自动润色目标文本,可不传 sample_text(只发 user)。
        """
        messages: list[dict[str, Any]] = [{"role": "user", "content": voice_prompt}]
        if not optimize_text_preview:
            messages.append({"role": "assistant", "content": sample_text or ""})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "audio": {"format": audio_format},
            "modalities": ["text", "audio"],
        }
        if optimize_text_preview:
            body["optimize_text_preview"] = True
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
        instructions: str | None = None,
    ) -> dict[str, Any]:
        """voiceclone 模型:audio.voice 必须是 DataURL(data:audio/wav;base64,...)。

        v2.5:可选 instructions 作为 user 消息控制风格(文档明确 voiceclone 支持)。
        """
        messages: list[dict[str, Any]] = []
        if instructions:
            messages.append({"role": "user", "content": instructions})
        messages.append({"role": "assistant", "content": text})
        body = {
            "model": model,
            "messages": messages,
            "audio": {"voice": reference_data_url, "format": audio_format},
            "modalities": ["text", "audio"],
        }
        resp = await self.client.post("/chat/completions", json=body)
        self._check(resp)
        return resp.json()

    # M1 实测确认的 ASR schema(2026-06-27,token-plan 端点):
    # - 走 OpenAI 兼容 /audio/transcriptions,multipart/form-data
    # - 必填:file(音频字节)+ model(mimo-v2.5-asr)
    # - response_format=json → {"text": ...};verbose_json → 追加
    #   duration / language / segments[{start,end,text,...}]
    # - language 可传 auto / zh 等;timestamp_granularities[]=segment 拿分段

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        *,
        model: str,
        language: str | None = None,
        response_format: str = "json",
        timestamp_granularity: str | None = None,
        prompt: str | None = None,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """ASR 语音转写。multipart 上传音频到 /audio/transcriptions。"""
        files = {"file": (filename, audio_bytes, content_type)}
        data: dict[str, str] = {"model": model, "response_format": response_format}
        if language and language != "auto":
            data["language"] = language
        if timestamp_granularity:
            data["timestamp_granularities[]"] = timestamp_granularity
        if prompt:
            data["prompt"] = prompt
        resp = await self.client.post("/audio/transcriptions", data=data, files=files)
        self._check(resp)
        return resp.json()

    async def list_models(self) -> list[str]:
        """列出账号可用模型 id(OpenAI 兼容 /models)。鉴权/网络异常向上抛。"""
        resp = await self.client.get("/models", timeout=15.0)
        self._check(resp)
        payload = resp.json()
        data = payload.get("data", payload if isinstance(payload, list) else [])
        return [m.get("id") for m in data if isinstance(m, dict) and m.get("id")]
