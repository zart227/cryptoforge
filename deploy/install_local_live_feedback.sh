#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/cryptoforge-live-feedback.service" <<UNIT
[Unit]
Description=CryptoForge read-only live execution feedback
After=network-online.target
[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONPATH=${PROJECT_DIR}/src
ExecStart=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/analyze_live_feedback.py"'
ExecStartPost=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/collect_live_experiences.py"'
ExecStartPost=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/collect_cash_recovery.py"'
ExecStartPost=/usr/bin/bash -lc 'set -a; source "${PROJECT_DIR}/.env"; set +a; nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/report_entry_gates.py"'
ExecStartPost=/usr/bin/bash -lc 'nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/check_live_learning_readiness.py"'
ExecStartPost=/usr/bin/bash -lc 'if [ -f "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json" ]; then nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/check_live_learning_readiness.py" --protocol "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json"; fi'
ExecStartPost=/usr/bin/bash -lc 'nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/report_cash_shadow.py"'
ExecStartPost=/usr/bin/bash -lc 'if [ -f "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json" ]; then nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/report_cash_shadow.py" --protocol "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json"; fi'
ExecStartPost=/usr/bin/bash -lc 'nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/export_cash_paper.py"'
ExecStartPost=/usr/bin/bash -lc 'nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/evaluate_cash_paper.py"'
ExecStartPost=/usr/bin/bash -lc 'if [ -f "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json" ]; then nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/export_cash_paper.py" --protocol "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json"; fi'
ExecStartPost=/usr/bin/bash -lc 'if [ -f "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json" ]; then nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/evaluate_cash_paper.py" --protocol "${PROJECT_DIR}/config/live-cash-recovery-closed-protocol-v1.json"; fi'
TimeoutStartSec=3min
ExecStartPost=/usr/bin/bash -lc 'if [ -f "${PROJECT_DIR}/.local/state/archive-net-window-portfolio-report.json" ] && [ -f "${PROJECT_DIR}/.local/state/archive-net-ablation-portfolio-report.json" ] && [ -f "${PROJECT_DIR}/.local/state/archive-net-classifier-balance-report.json" ]; then nice -n 10 "${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/scripts/screen_completed_research.py" --protocol "${PROJECT_DIR}/config/net-classifier-balance-research-v1.json" --ledger "${PROJECT_DIR}/.local/state/research-attempts.sqlite" --report "${PROJECT_DIR}/.local/state/archive-net-window-portfolio-report.json" --report "${PROJECT_DIR}/.local/state/archive-net-ablation-portfolio-report.json" --report "${PROJECT_DIR}/.local/state/archive-net-classifier-balance-report.json" --output "${PROJECT_DIR}/.local/state/completed-research-economic-screen.json"; fi'
UMask=0077
NoNewPrivileges=true
UNIT
cat > "$UNIT_DIR/cryptoforge-live-feedback.timer" <<'UNIT'
[Unit]
Description=Update CryptoForge execution feedback every 30 minutes
[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
AccuracySec=2min
Unit=cryptoforge-live-feedback.service
[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now cryptoforge-live-feedback.timer
systemctl --user start cryptoforge-live-feedback.service
systemctl --user show cryptoforge-live-feedback.service -p Result -p ExecMainStatus
