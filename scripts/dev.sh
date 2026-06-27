#!/usr/bin/env bash
# 一键启动本地开发环境:后端 :7801 + 前端 :5173(Vite HMR)。
# 按 Ctrl+C 同时停止两者。生产/单进程模式请改用:
#   ./scripts/build_frontend.sh && ./scripts/run_web.sh   (只跑 :7801)
set -euo pipefail

PROJ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_DIR"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "[dev] 正在停止前后端…"
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# 后端(自动 source .env)
"$PROJ_DIR/scripts/run_web.sh" &
BACKEND_PID=$!

# 前端(Vite dev,/api 代理到 :7801)
( cd "$PROJ_DIR/webui/frontend" && pnpm dev ) &
FRONTEND_PID=$!

echo "[dev] 后端 → http://127.0.0.1:7801  (PID $BACKEND_PID)"
echo "[dev] 前端 → http://127.0.0.1:5173  (PID $FRONTEND_PID)"
echo "[dev] 按 Ctrl+C 同时停止两者"

# 任一子进程退出即整体退出(EXIT trap 负责清理另一个)
wait
