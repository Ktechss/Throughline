#!/usr/bin/env bash
# One-time Linux setup for Throughline (WSL or a real Linux server).
# Creates the Python venv, installs backend deps, and installs the frontend.
# Idempotent — safe to re-run.
#
#   ./setup.sh
#
# Requires: python3.11 (onnxruntime has no 3.14 wheels) and node/npm on PATH.
set -euo pipefail
cd "$(dirname "$0")"

# --- Python backend ---------------------------------------------------------
PY=${PYTHON:-python3.11}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "ERROR: $PY not found. Install Python 3.11 (NOT 3.14 — no onnxruntime wheels)." >&2
  echo "  Ubuntu/WSL:  sudo apt install python3.11 python3.11-venv" >&2
  exit 1
fi

echo "==> Creating venv (.venv) with $($PY --version)"
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip wheel setuptools

echo "==> Installing backend requirements"
./.venv/bin/pip install -r requirements.txt

# insightface drags in the full opencv-python (linked against libGL, which a
# headless server does not have). Force the headless build's cv2 to win LAST so
# `import cv2` works with no GUI libraries installed.
echo "==> Pinning headless OpenCV (server-safe cv2)"
./.venv/bin/pip install --quiet --force-reinstall --no-deps opencv-python-headless

# --- Frontend ---------------------------------------------------------------
if ! command -v npm >/dev/null 2>&1; then
  echo "WARNING: npm not found — skipping frontend install." >&2
  echo "  Install Node 20+ (see README) then run: (cd frontend && npm install)" >&2
else
  echo "==> Installing frontend (npm install)"
  ( cd frontend && npm install --no-audit --no-fund )
fi

# --- .env -------------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Wrote .env from .env.example — fill in FAL_KEY / ANTHROPIC_API_KEY"
fi

echo
echo "Setup complete. Start everything with:  ./run.sh"
