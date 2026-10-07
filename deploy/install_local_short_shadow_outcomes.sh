#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="${HOME}/.config/systemd/user"
mkdir -p "${SYSTEMD_DIR}"

cat > "${SYSTEMD_DIR}/cryptoforge-short-shadow-outcomes.service" <<UNIT
[Unit]
Description=CryptoForge short shadow outcome evaluator
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; nice -n 10 ionice -c2 -n7 python3 "${PROJECT_DIR}/scripts/evaluate_short_shadow.py" --lookback-hours "\${CRYPTOFORGE_SHORT_SHADOW_LOOKBACK_HOURS:-72}" --limit "\${CRYPTOFORGE_SHORT_SHADOW_LIMIT:-2000}" --supabase-timeout 30'
UNIT

cat > "${SYSTEMD_DIR}/cryptoforge-short-shadow-outcomes.timer" <<UNIT
[Unit]
Description=Run CryptoForge short shadow outcome evaluator every 30 minutes

[Timer]
OnBootSec=10min
OnUnitActiveSec=30min
AccuracySec=2min
Persistent=true
Unit=cryptoforge-short-shadow-outcomes.service

[Install]
WantedBy=timers.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-short-shadow-outcomes.timer
systemctl --user list-timers cryptoforge-short-shadow-outcomes.timer --no-pager
