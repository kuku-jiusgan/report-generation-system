#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_SOURCE="$PROJECT_ROOT/deploy/report-generation.service"
SERVICE_TARGET="/etc/systemd/system/report-generation.service"
HEALTHCHECK_SERVICE_SOURCE="$PROJECT_ROOT/deploy/report-generation-healthcheck.service"
HEALTHCHECK_SERVICE_TARGET="/etc/systemd/system/report-generation-healthcheck.service"
HEALTHCHECK_TIMER_SOURCE="$PROJECT_ROOT/deploy/report-generation-healthcheck.timer"
HEALTHCHECK_TIMER_TARGET="/etc/systemd/system/report-generation-healthcheck.timer"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Please run this installer with sudo: sudo ./scripts/install-service.sh" >&2
    exit 1
fi

if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" || ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]]; then
    echo "Project dependencies or the frontend build are missing. Run ./scripts/setup.sh first." >&2
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/.env" ]]; then
    echo "Missing $PROJECT_ROOT/.env" >&2
    exit 1
fi

install -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"
install -m 0644 "$HEALTHCHECK_SERVICE_SOURCE" "$HEALTHCHECK_SERVICE_TARGET"
install -m 0644 "$HEALTHCHECK_TIMER_SOURCE" "$HEALTHCHECK_TIMER_TARGET"
chmod 0755 "$PROJECT_ROOT/scripts/service-healthcheck.sh"
systemctl daemon-reload
systemctl enable --now report-generation.service
systemctl enable --now report-generation-healthcheck.timer

echo "report-generation.service has been installed and started."
echo "Health monitoring runs once per minute."
echo "Status: sudo systemctl status report-generation.service"
echo "Timer:  sudo systemctl status report-generation-healthcheck.timer"
echo "Logs:   sudo journalctl -u report-generation.service -f"
