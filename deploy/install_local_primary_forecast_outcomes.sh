#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-primary-forecast-outcomes.service" <<UNIT
[Unit]
Description=CryptoForge read-only primary forecast price diagnostics
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; /usr/bin/flock -n "${PROJECT_DIR}/.local/state/primary-forecast-outcomes.lock" nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/collect_primary_forecast_outcomes.py" --maximum-forecasts 400 --maximum-pairs 20 --wall-seconds 20'
ExecStartPost=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/report_primary_forecasts.py"'
TimeoutStartSec=45
MemoryMax=256M
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-primary-forecast-outcomes.timer" <<'UNIT'
[Unit]
Description=Update CryptoForge primary forecast diagnostics every 30 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
AccuracySec=1min
Unit=cryptoforge-primary-forecast-outcomes.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-primary-forecast-outcomes.timer
systemctl --user start cryptoforge-primary-forecast-outcomes.service
systemctl --user show cryptoforge-primary-forecast-outcomes.service -p Result -p ExecMainStatus
