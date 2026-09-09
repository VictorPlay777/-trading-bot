#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="${BOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON="$BOT_DIR/venv/bin/python"
SERVICE_NAME="trading-dashboard.service"

if [[ ! -x "$PYTHON" ]]; then
    echo "Missing virtualenv interpreter: $PYTHON" >&2
    exit 1
fi

"$PYTHON" -m pip install \
    -r "$BOT_DIR/requirements.txt" \
    -r "$BOT_DIR/requirements-dashboard.txt"

sudo install -m 0644 "$SCRIPT_DIR/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"

echo "Installed and enabled $SERVICE_NAME."
echo "Start it with: sudo systemctl start $SERVICE_NAME"
