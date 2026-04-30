"""统一配置加载。所有可配置项从 .env / 环境变量读取,前缀 MIMO_。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MimoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MIMO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    api_key: str = Field(default="", description="MiMo API Key,从 platform.xiaomimimo.com 获取")
    base_url: str = Field(default="https://api.xiaomimimo.com/v1")

    default_text_model: str = "mimo-v2.5-pro"
    default_vision_model: str = "mimo-v2.5"
    default_tts_model: str = "mimo-v2.5-tts"
    default_voice_clone_model: str = "mimo-v2.5-tts-voiceclone"
    default_voice_design_model: str = "mimo-v2.5-tts-voicedesign"
    default_asr_model: str = "mimo-v2.5-asr"

    # v2.5 系列是 thinking 模型,默认 reasoning 会占大量 token,给足以跑完思考 + 回复
    default_max_tokens: int = 4096

    web_host: str = "127.0.0.1"
    web_port: int = 7801
    # 开发期默认开启 reload:改 .py 或 .env 自动重启,避免改完看不到效果
    # 生产部署建议设 false(更稳定 + 启动更快)
    web_reload: bool = True

    data_dir: Path = Field(default=Path("./data"))
    http_timeout: float = 120.0
    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mimo.db"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("sk-请")

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "voice_refs").mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "tts").mkdir(parents=True, exist_ok=True)
        (self.artifacts_dir / "uploads").mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> MimoSettings:
    """全局单例,首次读取后缓存。测试时可用 get_settings.cache_clear()。"""
    settings = MimoSettings()
    settings.ensure_dirs()
    return settings
