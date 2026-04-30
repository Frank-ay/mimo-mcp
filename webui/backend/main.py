"""FastAPI 入口。

进程独立于 stdio MCP server,但共享 src/mimo_mcp 的 SDK 适配层。
开发期:uv run mimo-web   生产期:uvicorn webui.backend.main:app
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mimo_mcp.api import tts as api_tts
from mimo_mcp.config import get_settings
from mimo_mcp.logging_setup import configure_logging
from mimo_mcp.storage import Storage

from .routers import asr, chat, tts, usage, vision, voices

log = logging.getLogger("mimo_web")


def _frontend_dist() -> Path:
    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, stderr_only=False)
    storage = Storage(settings.db_path)
    await storage.init()
    seeded = await api_tts.seed_default_voices(storage)
    app.state.storage = storage
    app.state.settings = settings
    log.info("mimo-web 启动:%s:%d  default_voices=%d", settings.web_host, settings.web_port, seeded)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="mimo-mcp Web Console",
        version="0.1.0",
        description="本地管理面板:音色库 / 多模态沙盒 / 审计日志",
        lifespan=lifespan,
    )

    # 仅本地 dev server(Vite 5173)需要 CORS;生产时同源不需要
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(voices.router, prefix="/api/voices", tags=["voices"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(vision.router, prefix="/api/vision", tags=["vision"])
    app.include_router(asr.router, prefix="/api/asr", tags=["asr"])
    app.include_router(usage.router, prefix="/api/usage", tags=["usage"])
    app.include_router(tts.router, prefix="/api/tts", tags=["tts"])

    dist = _frontend_dist()
    if dist.exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")
    else:
        @app.get("/")
        async def _hint() -> dict[str, str]:
            return {
                "status": "ok",
                "hint": (
                    "前端尚未构建。开发期请到 webui/frontend 目录运行 "
                    "`pnpm install && pnpm dev`,生产期运行 `pnpm build`。"
                ),
            }
    return app


app = create_app()


def main() -> None:
    """启动 Web 后端。

    默认开启 hot reload:
    - 改 src/mimo_mcp/**.py 或 webui/backend/**.py → 自动重启
    - 改 .env(API key、base_url 等)→ 自动重启,新配置立即生效
    - 改 webui/frontend(归 Vite HMR 管,不在这里)
    """
    settings = get_settings()

    if not settings.web_reload:
        uvicorn.run(
            "webui.backend.main:app",
            host=settings.web_host,
            port=settings.web_port,
            reload=False,
        )
        return

    # 监听三个范围:src/ 与 webui/backend/ 里的 .py,以及项目根的 .env
    # 前端 TS / 产物 / 缓存都用 reload_excludes 排除掉
    project_root = Path(__file__).resolve().parents[2]
    uvicorn.run(
        "webui.backend.main:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=True,
        reload_dirs=[
            str(project_root / "src"),
            str(project_root / "webui" / "backend"),
            str(project_root),  # 为了监听根目录下的 .env
        ],
        reload_includes=["*.py", ".env"],
        reload_excludes=[
            "**/__pycache__/*",
            "**/.pytest_cache/*",
            "**/node_modules/*",
            ".venv/*",
            "data/*",
            "webui/frontend/*",
            ".git/*",
            "docs/*",
        ],
    )


if __name__ == "__main__":
    main()
