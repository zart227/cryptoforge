#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="cryptoforge-supabase-executor"
LIVE_ARG=""
if [[ "${1:-}" == "--live" ]]; then
  LIVE_ARG="--live"
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--live]" >&2
  exit 2
fi
test -x "${PROJECT_DIR}/.venv/bin/python"
test -f "${PROJECT_DIR}/.env"
mkdir -p "$SERVICE_DIR" "${PROJECT_DIR}/.local/state" "${PROJECT_DIR}/logs"

cat >"${SERVICE_DIR}/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=CryptoForge local guarded Spot executor
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/flock -n ${PROJECT_DIR}/.local/state/executor.lock ${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/windows_background_runner.py executor --use-night-research --night-research-limit 12 --allow-intraday-reversion --allow-emerging-momentum --append-fallback-pairs --pair ETH/USDT --pair NEAR/USDT --pair ENA/USDT --pair HYPE/USDT --stake-amount 6 --max-open-positions 6 --max-daily-loss 2 --stop-loss-percent 0.04 --ml-mode gate --ml-threshold 0.50 --ml-max-age-hours 36 --timeout 25 ${LIVE_ARG}
TimeoutStartSec=10min
KillMode=control-group
Nice=10
UMask=0077
NoNewPrivileges=true

UNIT

cat >"${SERVICE_DIR}/${SERVICE_NAME}.timer" <<UNIT
[Unit]
Description=Run CryptoForge Spot executor every two minutes

[Timer]
OnBootSec=45s
OnUnitInactiveSec=2min
AccuracySec=10s
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE_NAME}.timer"
systemctl --user start --no-block "${SERVICE_NAME}.service"
systemctl --user --no-pager status "${SERVICE_NAME}.timer"
