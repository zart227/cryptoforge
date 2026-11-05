#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
PROTOCOL="${PROJECT_DIR}/.local/state/feature-migrations/700119966617653d6be5d011b009821ff35383ea91304c56bd02206d56c38c24/protocol.json"
test -f "$PROTOCOL"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-feature-migration.service" <<UNIT
[Unit]
Description=CryptoForge fixed prospective feature price comparison
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/collect_feature_migration.py --protocol ${PROTOCOL}
TimeoutStartSec=45s
MemoryMax=256M
Nice=10
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-feature-migration.timer" <<'UNIT'
[Unit]
Description=Collect future fixed-model/control price diagnostics every5minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=5min
AccuracySec=30s
Unit=cryptoforge-feature-migration.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-feature-migration.timer
systemctl --user start cryptoforge-feature-migration.service
systemctl --user show cryptoforge-feature-migration.service -p Result -p ExecMainStatus
