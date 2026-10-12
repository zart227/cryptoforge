#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-instrument-observations.service" <<UNIT
[Unit]
Description=CryptoForge public Spot instrument observation archive
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/flock -n ${PROJECT_DIR}/.local/state/instrument-observations.lock /usr/bin/nice -n 10 ${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/capture_spot_instrument_observations.py
TimeoutStartSec=30
MemoryMax=128M
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-instrument-observations.timer" <<'UNIT'
[Unit]
Description=Observe current Spot filters every 30 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
AccuracySec=1min
Unit=cryptoforge-instrument-observations.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-instrument-observations.timer
