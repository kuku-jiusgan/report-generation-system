#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""

cleanup() {
    if [[ -n "$BACKEND_PID" ]]; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" || ! -d "$PROJECT_ROOT/frontend/node_modules" ]]; then
    "$PROJECT_ROOT/scripts/setup.sh"
fi

export PYTHONPATH="$PROJECT_ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
"$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app --reload \
    --host 0.0.0.0 --port 8010 --app-dir "$PROJECT_ROOT/backend" &
BACKEND_PID=$!

echo "Frontend: http://0.0.0.0:5173"
echo "API docs: http://127.0.0.1:8010/docs"
cd "$PROJECT_ROOT/frontend"
npm run dev
