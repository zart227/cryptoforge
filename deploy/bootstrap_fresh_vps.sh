#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${CRYPTOFORGE_REPO_URL:-https://github.com/zart227/cryptoforge.git}"
BRANCH="${CRYPTOFORGE_BRANCH:-main}"
APP_ROOT="${CRYPTOFORGE_APP_ROOT:-/opt/cryptoforge}"
APP_DIR="$APP_ROOT/app"
REPO_DIR="$APP_DIR/cryptoforge_repo"
VENV_DIR="$APP_DIR/venv"
CONFIG_DIR="$APP_ROOT/config"
DATA_DIR="$APP_ROOT/data"
LOG_DIR="$APP_ROOT/logs"
BACKUP_DIR="$APP_ROOT/backups"
USER_NAME="${CRYPTOFORGE_USER:-cryptoforge}"
PYTHON_BIN="${CRYPTOFORGE_PYTHON:-python3}"

if [ "$(id -u)" != "0" ]; then
  echo "Run as root." >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  ca-certificates \
  curl \
  git \
  jq \
  logrotate \
  python3 \
  python3-pip \
  python3-venv \
  rsync \
  systemd \
  tzdata

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --home "$APP_ROOT" --shell /usr/sbin/nologin "$USER_NAME"
fi

mkdir -p "$APP_DIR" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$BACKUP_DIR" "$APP_ROOT/outbox"
chown -R "$USER_NAME:$USER_NAME" "$APP_ROOT"
chmod 0750 "$APP_ROOT" "$APP_DIR" "$CONFIG_DIR" "$DATA_DIR" "$LOG_DIR" "$BACKUP_DIR" "$APP_ROOT/outbox"

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" fetch --prune origin "$BRANCH"
  git -C "$REPO_DIR" checkout -B "$BRANCH" "origin/$BRANCH"
  git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
else
  rm -rf "$REPO_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi
chown -R "$USER_NAME:$USER_NAME" "$REPO_DIR"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install -e "$REPO_DIR"
"$VENV_DIR/bin/pip" install freqtrade
chown -R "$USER_NAME:$USER_NAME" "$VENV_DIR"

mkdir -p "$APP_DIR/user_data/strategies"
cp "$REPO_DIR"/user_data/strategies/*.py "$APP_DIR/user_data/strategies/"
chown -R "$USER_NAME:$USER_NAME" "$APP_DIR/user_data"

if [ ! -f "$APP_DIR/.env" ]; then
  install -m 0600 -o "$USER_NAME" -g "$USER_NAME" "$REPO_DIR/.env.example" "$APP_DIR/.env"
  {
    echo ""
    echo "# Fill real secrets before live use."
    echo "BYBIT_AI_SUB_MEMBER_ID="
    echo "TELEGRAM_PROXY_URL="
    echo "NTFY_TOPIC="
    echo "NTFY_BASE_URL=https://ntfy.sh"
  } >> "$APP_DIR/.env"
fi
chmod 0600 "$APP_DIR/.env"
chown "$USER_NAME:$USER_NAME" "$APP_DIR/.env"

if [ ! -f "$CONFIG_DIR/freqtrade.live-pilot.json" ]; then
  "$VENV_DIR/bin/python" - <<'PY'
from decimal import Decimal
from cryptoforge.live_config import LiveConfigRequest, write_live_config
write_live_config(
    "/opt/cryptoforge/config/freqtrade.live-pilot.json",
    LiveConfigRequest(stake_amount=Decimal("10"), max_open_trades=1, pair_whitelist=("BTC/USDT",)),
)
PY
fi

cp "$REPO_DIR/deploy/systemd/cryptoforge-git-sync.service" /etc/systemd/system/cryptoforge-git-sync.service
cp "$REPO_DIR/deploy/systemd/cryptoforge-git-sync.timer" /etc/systemd/system/cryptoforge-git-sync.timer
cp "$REPO_DIR/deploy/systemd/cryptoforge-freqtrade.service" /etc/systemd/system/cryptoforge-freqtrade.service
cp "$REPO_DIR/deploy/systemd/cryptoforge-live-pilot.service" /etc/systemd/system/cryptoforge-live-pilot.service
cp "$REPO_DIR/deploy/logrotate/cryptoforge" /etc/logrotate.d/cryptoforge

systemctl daemon-reload
systemctl enable --now cryptoforge-git-sync.timer

runuser -u "$USER_NAME" -- bash "$REPO_DIR/deploy/update_vps.sh"

echo "bootstrap_ok=true"
echo "repo_dir=$REPO_DIR"
echo "env_file=$APP_DIR/.env"
echo "live_config=$CONFIG_DIR/freqtrade.live-pilot.json"
echo "next_steps=restore .env secrets, update Bybit IP whitelist, run live smoke"
