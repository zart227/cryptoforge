#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECEIPT="${1:?Pass observed job.json}"
test -f "$RECEIPT"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-walk-forward-inputs.service" <<UNIT
[Unit]
Description=CryptoForge source-bound walk-forward input preparation
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/run_walk_forward_input_job.py --job ${RECEIPT}
ExecStartPost=/bin/bash ${PROJECT_DIR}/deploy/finish_walk_forward_inputs.sh ${RECEIPT}
TimeoutStartSec=150s
MemoryMax=896M
Nice=15
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-walk-forward-inputs.timer" <<'UNIT'
[Unit]
Description=Resume the fixed registered study under original worker reserves
[Timer]
OnBootSec=20min
OnUnitActiveSec=20min
AccuracySec=1min
Unit=cryptoforge-walk-forward-inputs.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-walk-forward-inputs.timer
systemctl --user start cryptoforge-walk-forward-inputs.service
systemctl --user show cryptoforge-walk-forward-inputs.service -p Result -p ExecMainStatus
