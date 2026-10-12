#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
PROTOCOL_FILE="${1:?Pass the frozen study protocol path}"
PAPER_INSTALL_DATA="$(CRYPTOFORGE_PAPER_INSTALL_PROTOCOL="$PROTOCOL_FILE" PYTHONPATH=src "$PROJECT_DIR/.venv/bin/python" - <<'PY'
from datetime import UTC,datetime
from pathlib import Path
import os
from cryptoforge.cash_study_paths import load_cash_study
from cryptoforge.cash_study_registry import require_collection_freeze
from cryptoforge.paper_activation import load_activation
from cryptoforge.live_learning_protocol import time
p=Path(os.environ['CRYPTOFORGE_PAPER_INSTALL_PROTOCOL']);protocol,study=load_cash_study(p);require_collection_freeze(study)
now=datetime.now(UTC)
result=load_activation(p,study.execution_policy,study.candidate,study.predictions,now=now)
if result['status'] not in {'eligible_virtual_worker','outside_paper_window'}:
    raise SystemExit('Study paper service cannot be installed: '+result['status'])
if now>=time(protocol['windows']['paper']['end_exclusive']):raise SystemExit('Study paper window is over')
import json
print(study.protocol_sha256,int(json.loads(study.execution_policy.read_bytes())['runtime']['poll_seconds']))
PY
)"
read -r PAPER_PROTOCOL_SHA PAPER_POLL_SECONDS <<< "$PAPER_INSTALL_DATA"
UNIT_NAME="cryptoforge-cash-study-paper-${PAPER_PROTOCOL_SHA}"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/${UNIT_NAME}.service" <<UNIT
[Unit]
Description=CryptoForge isolated study virtual paper execution
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/flock -n ${PROJECT_DIR}/.local/state/cash-study-paper-${PAPER_PROTOCOL_SHA}.lock ${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/run_cash_paper.py --protocol "${PROTOCOL_FILE}"
TimeoutStartSec=45s
Nice=10
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/${UNIT_NAME}.timer" <<UNIT
[Unit]
Description=Run a preregistered isolated study paper worker
[Timer]
OnBootSec=5s
OnUnitActiveSec=${PAPER_POLL_SECONDS}s
AccuracySec=1s
Unit=${UNIT_NAME}.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now "${UNIT_NAME}.timer"
