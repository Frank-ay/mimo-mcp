#!/usr/bin/env bash
# 一键构建前端到 webui/frontend/dist。FastAPI 启动后会自动挂载。
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR/webui/frontend"

if [[ ! -d "node_modules" ]]; then
  echo "[mimo-web] 首次构建,执行 pnpm install …" >&2
  pnpm install
fi

pnpm build
