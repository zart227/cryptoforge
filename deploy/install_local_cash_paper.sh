#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
PAPER_POLL_SECONDS="$(PYTHONPATH=src "$PROJECT_DIR/.venv/bin/python" - <<'PY'
from pathlib import Path
from datetime import UTC,datetime
import json
from cryptoforge.paper_activation import load_activation
from cryptoforge.live_learning_protocol import load_protocol,time
p=Path('config/live-cash-recovery-protocol-v1.json');now=datetime.now(UTC)
result=load_activation(p,Path('config/paper-execution-policy-v1.json'),Path('.local/state/cash-shadow-candidate.json'),Path('.local/state/cash-shadow-predictions.sqlite'),now=now)
if result['status'] not in {'eligible_virtual_worker','outside_paper_window'}:
    raise SystemExit('Paper service cannot be installed before verified candidate/policy: '+result['status'])
protocol=load_protocol(p)
if now>=time(protocol['windows']['paper']['end_exclusive']):raise SystemExit('The frozen paper window is over')
policy=json.loads(Path('config/paper-execution-policy-v1.json').read_bytes())
print(int(policy['runtime']['poll_seconds']))
PY
)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR" "$PROJECT_DIR/.local/state"
cat > "$UNIT_DIR/cryptoforge-cash-paper.service" <<UNIT
[Unit]
Description=CryptoForge isolated virtual paper execution
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/flock -n ${PROJECT_DIR}/.local/state/cash-paper.lock ${PROJECT_DIR}/.venv/bin/python ${PROJECT_DIR}/scripts/run_cash_paper.py
TimeoutStartSec=45s
Nice=10
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-cash-paper.timer" <<UNIT
[Unit]
Description=Run the preregistered virtual paper worker
[Timer]
OnBootSec=5s
OnUnitActiveSec=${PAPER_POLL_SECONDS}s
AccuracySec=1s
Unit=cryptoforge-cash-paper.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-cash-paper.timer
