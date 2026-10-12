#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
PYTHONPATH="${PROJECT_DIR}:${PROJECT_DIR}/src" "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/retry_feature_ablation.py" --register-only
cat > "$UNIT_DIR/cryptoforge-feature-ablation.service" <<UNIT
[Unit]
Description=CryptoForge one frozen feature ablation study
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}:${PROJECT_DIR}/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/retry_feature_ablation.py
TimeoutStartSec=140s
MemoryMax=768M
Nice=10
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-feature-ablation.timer" <<'UNIT'
[Unit]
Description=Retry one frozen feature ablation when resources permit
[Timer]
OnBootSec=15min
OnUnitActiveSec=30min
AccuracySec=2min
Unit=cryptoforge-feature-ablation.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-feature-ablation.timer
systemctl --user start cryptoforge-feature-ablation.service
systemctl --user show cryptoforge-feature-ablation.service -p Result -p ExecMainStatus
