#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_ADDRESS="${REPORT_HOST:-0.0.0.0}"
PORT="${REPORT_PORT:-8010}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host) HOST_ADDRESS="${2:?Missing value for --host}"; shift 2 ;;
        --port) PORT="${2:?Missing value for --port}"; shift 2 ;;
        -h|--help)
            echo "Usage: ./start.sh [--host HOST] [--port PORT]"
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" || ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]]; then
    echo "The application has not been set up yet. Running setup..."
    "$PROJECT_ROOT/scripts/setup.sh"
fi

export PYTHONPATH="$PROJECT_ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
echo "Report Studio is starting at http://$HOST_ADDRESS:$PORT"
echo "Press Ctrl+C to stop."
exec "$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app \
    --host "$HOST_ADDRESS" --port "$PORT" --app-dir "$PROJECT_ROOT/backend"
