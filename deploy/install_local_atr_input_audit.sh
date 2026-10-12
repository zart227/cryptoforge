#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-atr-input-audit.service" <<UNIT
[Unit]
Description=CryptoForge resource-gated development ATR input audit
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/audit_atr_inputs.py
TimeoutStartSec=45s
MemoryMax=256M
Nice=10
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-atr-input-audit.timer" <<'UNIT'
[Unit]
Description=Retry deferred CryptoForge input audit every 30 minutes
[Timer]
OnBootSec=10min
OnUnitActiveSec=30min
AccuracySec=2min
Unit=cryptoforge-atr-input-audit.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-atr-input-audit.timer
systemctl --user start cryptoforge-atr-input-audit.service
systemctl --user show cryptoforge-atr-input-audit.service -p Result -p ExecMainStatus
