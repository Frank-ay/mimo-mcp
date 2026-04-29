"""统一日志配置。stdio MCP 必须把日志发往 stderr(否则会污染协议),Web 进程随意。"""

from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO", *, stderr_only: bool = True) -> None:
    handler = logging.StreamHandler(sys.stderr if stderr_only else sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s :: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
