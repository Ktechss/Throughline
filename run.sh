#!/usr/bin/env bash
# Run Throughline on Linux (WSL or a server): FastAPI backend + Vite frontend.
# Ctrl-C stops both.
#
#   ./run.sh            # backend :8000 + frontend dev :5173 (open :5173)
#   ./run.sh backend    # backend only
#   ./run.sh frontend   # frontend only
#
# Env: PORT (backend, default 8000), FRONTEND_PORT (default 5173),
#      HOST (bind address, default 0.0.0.0 so it's reachable off-box).
set -euo pipefail
cd "$(dirname "$0")"

PORT=${PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
HOST=${HOST:-0.0.0.0}
MODE=${1:-all}

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: .venv missing. Run ./setup.sh first." >&2
  exit 1
fi

pids=()
cleanup() { trap - INT TERM EXIT; kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

start_backend() {
  echo "==> Backend  http://$HOST:$PORT  (docs at /docs)"
  ./.venv/bin/python -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --reload &
  pids+=($!)
}

start_frontend() {
  echo "==> Frontend http://$HOST:$FRONTEND_PORT  (proxies /api -> :$PORT)"
  ( cd frontend && npm run dev -- --host "$HOST" --port "$FRONTEND_PORT" ) &
  pids+=($!)
}

case "$MODE" in
  backend)  start_backend ;;
  frontend) start_frontend ;;
  all)      start_backend; start_frontend ;;
  *) echo "usage: ./run.sh [all|backend|frontend]" >&2; exit 1 ;;
esac

wait
