#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="cryptoforge-model-training"
UNIVERSE_FILE="${PROJECT_DIR}/.local/state/live-universe.json"
ARTIFACT_DIR="${PROJECT_DIR}/.local/models"

mkdir -p "$SERVICE_DIR"

cat >"${SERVICE_DIR}/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=CryptoForge local lightweight model training

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; python3 "${PROJECT_DIR}/scripts/select_live_universe.py" --output "${UNIVERSE_FILE}" --limit "${CRYPTOFORGE_UNIVERSE_LIMIT:-20}" --cheap-shortlist-size "${CRYPTOFORGE_CHEAP_SHORTLIST_SIZE:-80}" --expensive-shortlist-size "${CRYPTOFORGE_EXPENSIVE_SHORTLIST_SIZE:-32}" --candle-limit "${CRYPTOFORGE_UNIVERSE_CANDLE_LIMIT:-120}" && python3 "${PROJECT_DIR}/scripts/sync_supabase_market_data.py" --live-config "${UNIVERSE_FILE}" --candle-limit "${CRYPTOFORGE_MARKET_CANDLE_LIMIT:-500}" --bybit-timeout 20 --supabase-timeout 30 && nice -n 10 ionice -c2 -n7 python3 "${PROJECT_DIR}/scripts/run_model_training.py" --pairs-file "${UNIVERSE_FILE}" --artifact-dir "${ARTIFACT_DIR}" --lookback-candles "${CRYPTOFORGE_MODEL_LOOKBACK_CANDLES:-500}" --horizon-candles "${CRYPTOFORGE_MODEL_HORIZON_CANDLES:-3}" --min-examples "${CRYPTOFORGE_MODEL_MIN_EXAMPLES:-80}" --epochs "${CRYPTOFORGE_MODEL_EPOCHS:-450}" --learning-rate "${CRYPTOFORGE_MODEL_LEARNING_RATE:-0.08}" --supabase-timeout 30'
UNIT

cat >"${SERVICE_DIR}/${SERVICE_NAME}.timer" <<UNIT
[Unit]
Description=Run CryptoForge local model training during the day and night

[Timer]
OnCalendar=*-*-* 03:05:00
OnCalendar=*-*-* 11/6:35:00
RandomizedDelaySec=20min
Persistent=true
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.timer"
systemctl --user start "${SERVICE_NAME}.service"
systemctl --user --no-pager status "${SERVICE_NAME}.timer"
