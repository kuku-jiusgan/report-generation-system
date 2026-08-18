#!/usr/bin/env bash

set -euo pipefail

SERVICE_NAME="report-generation.service"
HEALTH_URL="http://127.0.0.1:8010/health"
MAX_ATTEMPTS=6
RETRY_INTERVAL_SECONDS=10

if systemctl is-active --quiet "$SERVICE_NAME"; then
    for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
        if curl --fail --silent --show-error --max-time 10 "$HEALTH_URL" >/dev/null; then
            exit 0
        fi

        if ((attempt < MAX_ATTEMPTS)); then
            sleep "$RETRY_INTERVAL_SECONDS"
        fi
    done
fi

logger -t report-generation-healthcheck \
    "Health check failed for $HEALTH_URL; restarting $SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
