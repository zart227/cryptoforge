#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="cryptoforge-market-feeder"
UNIVERSE_FILE="${PROJECT_DIR}/.local/state/live-universe.json"

mkdir -p "$SERVICE_DIR"

cat >"${SERVICE_DIR}/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=CryptoForge local Supabase market data feeder

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; python3 "${PROJECT_DIR}/scripts/select_live_universe.py" --output "${UNIVERSE_FILE}" --limit "${CRYPTOFORGE_UNIVERSE_LIMIT:-20}" --cheap-shortlist-size "${CRYPTOFORGE_CHEAP_SHORTLIST_SIZE:-80}" --expensive-shortlist-size "${CRYPTOFORGE_EXPENSIVE_SHORTLIST_SIZE:-32}" --candle-limit "${CRYPTOFORGE_UNIVERSE_CANDLE_LIMIT:-120}" && python3 "${PROJECT_DIR}/scripts/sync_supabase_market_data.py" --live-config "${UNIVERSE_FILE}" --candle-limit "${CRYPTOFORGE_MARKET_CANDLE_LIMIT:-120}" --bybit-timeout 20 --supabase-timeout 20'
UNIT

cat >"${SERVICE_DIR}/${SERVICE_NAME}.timer" <<UNIT
[Unit]
Description=Run CryptoForge local market feeder every 2 minutes

[Timer]
OnBootSec=30s
OnUnitActiveSec=2min
AccuracySec=15s
Persistent=true
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.timer"
systemctl --user start "${SERVICE_NAME}.service"
systemctl --user --no-pager status "${SERVICE_NAME}.timer"
