#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECEIPT="${1:?Pass observed protocol.json}"
test -f "$RECEIPT"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-passive-context.service" <<UNIT
[Unit]
Description=CryptoForge fixed passive buy-and-hold development context
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/run_extension_study_job.py --receipt ${RECEIPT}
ExecStartPost=/bin/bash ${PROJECT_DIR}/deploy/finish_passive_context.sh ${RECEIPT}
TimeoutStartSec=150s
MemoryMax=896M
Nice=15
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-passive-context.timer" <<'UNIT'
[Unit]
Description=Resume the fixed registered study under original worker reserves
[Timer]
OnBootSec=20min
OnUnitActiveSec=20min
AccuracySec=1min
Unit=cryptoforge-passive-context.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-passive-context.timer
systemctl --user start cryptoforge-passive-context.service
systemctl --user show cryptoforge-passive-context.service -p Result -p ExecMainStatus
