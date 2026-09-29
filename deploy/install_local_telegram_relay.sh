#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="cryptoforge-telegram-relay"

mkdir -p "$SERVICE_DIR"

cat >"${SERVICE_DIR}/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=CryptoForge local Telegram relay
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; "${PROJECT_DIR}/.venv/bin/python" -m cryptoforge.telegram_relay --watch --interval-seconds 60'
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.service"
systemctl --user --no-pager --lines=40 status "${SERVICE_NAME}.service"
