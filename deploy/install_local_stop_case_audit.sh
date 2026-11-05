#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECEIPT="${1:?Pass observed job.json}"
test -f "$RECEIPT"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-stop-case-audit.service" <<UNIT
[Unit]
Description=CryptoForge fixed source-bound stop-case minute audit
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/run_stop_case_audit_job.py --job ${RECEIPT}
ExecStartPost=/bin/bash ${PROJECT_DIR}/deploy/finish_stop_case_audit.sh ${RECEIPT}
TimeoutStartSec=150s
MemoryMax=896M
Nice=15
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-stop-case-audit.timer" <<'UNIT'
[Unit]
Description=Resume the fixed registered study under original worker reserves
[Timer]
OnBootSec=20min
OnUnitActiveSec=20min
AccuracySec=1min
Unit=cryptoforge-stop-case-audit.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-stop-case-audit.timer
systemctl --user start cryptoforge-stop-case-audit.service
systemctl --user show cryptoforge-stop-case-audit.service -p Result -p ExecMainStatus
