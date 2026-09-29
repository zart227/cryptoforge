#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${CRYPTOFORGE_APP_ROOT:-/opt/cryptoforge}"
APP_DIR="$APP_ROOT/app"
REPO_DIR="${CRYPTOFORGE_REPO_DIR:-$APP_DIR/cryptoforge_repo}"
VENV_DIR="${CRYPTOFORGE_VENV_DIR:-$APP_DIR/venv}"

if [ "$(id -u)" != "0" ]; then
  echo "Run as root." >&2
  exit 2
fi

if [ ! -f "$APP_DIR/.env" ]; then
  echo "Missing $APP_DIR/.env" >&2
  exit 2
fi

"$VENV_DIR/bin/pip" install -e "$REPO_DIR"

cp "$REPO_DIR/deploy/systemd/cryptoforge-supabase-executor.service" /etc/systemd/system/cryptoforge-supabase-executor.service
cp "$REPO_DIR/deploy/systemd/cryptoforge-supabase-executor.timer" /etc/systemd/system/cryptoforge-supabase-executor.timer

systemctl daemon-reload
systemctl enable --now cryptoforge-supabase-executor.timer
systemctl start cryptoforge-supabase-executor.service
systemctl --no-pager status cryptoforge-supabase-executor.timer cryptoforge-supabase-executor.service
