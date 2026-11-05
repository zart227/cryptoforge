#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATUS="$(dirname "${1:?Pass observed job.json}")/status.json"
if "$PROJECT_DIR/.venv/bin/python" -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["status"]=="completed" or r["status"].startswith("blocked_") else 1)' "$STATUS"; then
  systemctl --user disable --now cryptoforge-stop-case-audit.timer
fi
