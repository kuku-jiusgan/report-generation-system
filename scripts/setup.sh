#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Python 3 was not found. Install Python 3.11 or newer." >&2
    exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    echo "Node.js and npm were not found. Install Node.js 20 or newer." >&2
    exit 1
fi

"$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' || {
    echo "Python 3.11 or newer is required." >&2
    exit 1
}

echo "[1/4] Creating Python virtual environment..."
if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$PROJECT_ROOT/.venv"
fi

echo "[2/4] Installing backend dependencies..."
"$PROJECT_ROOT/.venv/bin/python" -m pip install --disable-pip-version-check --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install --disable-pip-version-check \
    -r "$PROJECT_ROOT/backend/requirements.txt"

echo "[3/4] Installing frontend dependencies..."
cd "$PROJECT_ROOT/frontend"
npm ci

echo "[4/4] Building frontend..."
npm run build

echo "Setup complete. Run ./start.sh to start the application."
