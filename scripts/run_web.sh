#!/usr/bin/env bash
# Web 控制台启动脚本。开发期建议两个终端:
#   终端 1:scripts/run_web.sh                           (后端 :7801)
#   终端 2:cd webui/frontend && pnpm dev                (前端 :5173,代理到后端)
# 生产期:先 pnpm build,再仅跑本脚本即可,FastAPI 会托管 dist。
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

exec uv run --quiet mimo-web
