"""pytest 全局夹具。强制使用临时数据目录,避免污染本地 data/。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("MIMO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MIMO_API_KEY", os.environ.get("MIMO_API_KEY", "sk-test-not-real"))
    # 清掉 lru_cache,让 get_settings() 重新读
    from mimo_mcp.config import get_settings  # noqa: WPS433

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
