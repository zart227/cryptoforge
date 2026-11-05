#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOB="${1:?Pass the registered frozen job.json}"
test -f "$JOB"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-long-label-audit.service" <<UNIT
[Unit]
Description=CryptoForge fixed development archive label audit
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/run_long_label_audit_job.py --job ${JOB}
ExecStartPost=/bin/bash ${PROJECT_DIR}/deploy/finish_long_label_audit.sh ${JOB}
TimeoutStartSec=150s
MemoryMax=896M
Nice=15
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-long-label-audit.timer" <<'UNIT'
[Unit]
Description=Retry fixed label audit when original resource reserves permit
[Timer]
OnBootSec=15min
OnUnitActiveSec=15min
AccuracySec=1min
Unit=cryptoforge-long-label-audit.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-long-label-audit.timer
systemctl --user start cryptoforge-long-label-audit.service
systemctl --user show cryptoforge-long-label-audit.service -p Result -p ExecMainStatus
