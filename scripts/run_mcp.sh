#!/usr/bin/env bash
# stdio MCP server 启动脚本。Codex 的 TOML 不便传 env,统一用此脚本读取 .env。
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if [[ -z "${MIMO_API_KEY:-}" ]]; then
  echo "[mimo-mcp] 警告:MIMO_API_KEY 未设置,服务可启动但所有 API 调用都会 401。" >&2
fi

exec uv run --quiet mimo-mcp
