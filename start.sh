#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST_ADDRESS="${REPORT_HOST:-0.0.0.0}"
PORT="${REPORT_PORT:-8010}"
ONLYOFFICE_COMPOSE="$PROJECT_ROOT/docker-compose.onlyoffice.yml"

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

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to start ONLYOFFICE, but the docker command was not found." >&2
    exit 1
fi

if docker info >/dev/null 2>&1; then
    DOCKER_COMMAND=(docker)
elif command -v sudo >/dev/null 2>&1; then
    DOCKER_COMMAND=(sudo docker)
else
    echo "Cannot access the Docker daemon and sudo is not available." >&2
    exit 1
fi

echo "Starting ONLYOFFICE Document Server at port 8090..."
"${DOCKER_COMMAND[@]}" compose --env-file "$PROJECT_ROOT/.env" \
    -f "$ONLYOFFICE_COMPOSE" up -d

export PYTHONPATH="$PROJECT_ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
echo "Report Studio is starting at http://$HOST_ADDRESS:$PORT"
echo "ONLYOFFICE is available at ${REPORT_ONLYOFFICE_URL:-the URL configured in .env}"
echo "Press Ctrl+C to stop."
exec "$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app \
    --host "$HOST_ADDRESS" --port "$PORT" --app-dir "$PROJECT_ROOT/backend"
