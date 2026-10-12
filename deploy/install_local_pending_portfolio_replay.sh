#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
PYTHONPATH="${PROJECT_DIR}/src" "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/retry_portfolio_replay.py" --register-only
cat > "$UNIT_DIR/cryptoforge-pending-portfolio-replay.service" <<UNIT
[Unit]
Description=CryptoForge one source-bound deferred development replay
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/retry_portfolio_replay.py
TimeoutStartSec=45s
MemoryMax=256M
Nice=10
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-pending-portfolio-replay.timer" <<'UNIT'
[Unit]
Description=Retry one frozen CryptoForge replay when resources permit
[Timer]
OnBootSec=15min
OnUnitActiveSec=30min
AccuracySec=2min
Unit=cryptoforge-pending-portfolio-replay.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-pending-portfolio-replay.timer
systemctl --user start cryptoforge-pending-portfolio-replay.service
systemctl --user show cryptoforge-pending-portfolio-replay.service -p Result -p ExecMainStatus
