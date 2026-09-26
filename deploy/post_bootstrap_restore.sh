#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${CRYPTOFORGE_APP_ROOT:-/opt/cryptoforge}"
APP_DIR="$APP_ROOT/app"
REPO_DIR="$APP_DIR/cryptoforge_repo"
VENV_DIR="$APP_DIR/venv"
USER_NAME="${CRYPTOFORGE_USER:-cryptoforge}"
ENV_SOURCE="${1:-}"
RUNNER_TOKEN="${2:-}"

if [ "$(id -u)" != "0" ]; then
  echo "Run as root." >&2
  exit 2
fi

if [ -n "$ENV_SOURCE" ]; then
  if [ ! -f "$ENV_SOURCE" ]; then
    echo "env source not found: $ENV_SOURCE" >&2
    exit 2
  fi
  install -m 0600 -o "$USER_NAME" -g "$USER_NAME" "$ENV_SOURCE" "$APP_DIR/.env"
fi

cd "$REPO_DIR"
runuser -u "$USER_NAME" -- bash "$REPO_DIR/deploy/update_vps.sh"

if [ -n "$RUNNER_TOKEN" ]; then
  bash "$REPO_DIR/deploy/install_github_runner.sh" "$RUNNER_TOKEN"
fi

set -a
. "$APP_DIR/.env"
set +a

runuser -u "$USER_NAME" -- env PYTHONPATH=src "$VENV_DIR/bin/python" \
  scripts/select_live_universe.py \
  --output "$APP_ROOT/config/live-universe.json" \
  --live-config "$APP_ROOT/config/freqtrade.live-pilot.json" \
  --limit 4

runuser -u "$USER_NAME" -- env PYTHONPATH=src "$VENV_DIR/bin/python" \
  scripts/live_pilot_smoke.py \
  --env-file "$APP_DIR/.env" \
  --project-root "$REPO_DIR"

systemctl daemon-reload
systemctl status cryptoforge-live-pilot.service --no-pager || true

echo "post_bootstrap_restore_ok=true"
