#!/usr/bin/env bash
set -euo pipefail

APPLY=0
INCLUDE_LIVE=0
REMOVE_VENV=0
VACUUM_JOURNAL=0
LOG_DAYS="${CRYPTOFORGE_CLEANUP_LOG_DAYS:-14}"
APP_ROOT="${CRYPTOFORGE_APP_ROOT:-/opt/cryptoforge}"
APP_DIR="$APP_ROOT/app"
REPO_DIR="${CRYPTOFORGE_REPO_DIR:-$APP_DIR/cryptoforge_repo}"
VENV_DIR="${CRYPTOFORGE_VENV_DIR:-$APP_DIR/venv}"

usage() {
  cat <<'EOF'
Usage:
  cleanup_vps_resources.sh [--apply] [--include-live] [--remove-venv] [--vacuum-journal]

Default mode is dry-run.

Safe default cleanup:
  - disable/stop cryptoforge-git-sync.timer
  - stop cryptoforge-git-sync.service if it is running
  - remove Python bytecode caches under the CryptoForge repo
  - remove old CryptoForge logs
  - remove pip cache for the cryptoforge user when available

Explicit flags:
  --include-live     also disable/stop cryptoforge-supabase-executor.timer/service
  --remove-venv      remove /opt/cryptoforge/app/venv after services are stopped
  --vacuum-journal   vacuum systemd journal to 100M
EOF
}

run() {
  if [ "$APPLY" = "1" ]; then
    echo "+ $*"
    "$@"
  else
    echo "DRY-RUN: $*"
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --include-live) INCLUDE_LIVE=1 ;;
    --remove-venv) REMOVE_VENV=1 ;;
    --vacuum-journal) VACUUM_JOURNAL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$(id -u)" != "0" ]; then
  echo "Run as root on the VPS." >&2
  exit 2
fi

echo "cleanup_mode=$([ "$APPLY" = "1" ] && echo apply || echo dry-run)"
echo "app_root=$APP_ROOT"
echo "include_live=$INCLUDE_LIVE"
echo "remove_venv=$REMOVE_VENV"

if command -v systemctl >/dev/null 2>&1; then
  run systemctl disable --now cryptoforge-git-sync.timer
  run systemctl stop cryptoforge-git-sync.service

  if [ "$INCLUDE_LIVE" = "1" ]; then
    run systemctl disable --now cryptoforge-supabase-executor.timer
    run systemctl stop cryptoforge-supabase-executor.service
  else
    echo "Skipping live executor. Pass --include-live only after local Docker live/shadow cutover is approved."
  fi
fi

if [ -d "$REPO_DIR" ]; then
  run find "$REPO_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +
  run find "$REPO_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
fi

if id cryptoforge >/dev/null 2>&1; then
  if [ -d /opt/cryptoforge/.cache/pip ]; then
    run rm -rf /opt/cryptoforge/.cache/pip
  fi
fi

if [ -d "$APP_ROOT/logs" ]; then
  run find "$APP_ROOT/logs" -type f -name '*.log.*' -mtime +"$LOG_DAYS" -delete
  run find "$APP_ROOT/logs" -type f -name '*.gz' -mtime +"$LOG_DAYS" -delete
fi

if [ "$REMOVE_VENV" = "1" ]; then
  if [ "$INCLUDE_LIVE" != "1" ]; then
    echo "--remove-venv requires --include-live so no live process keeps using the venv." >&2
    exit 2
  fi
  if [ -d "$VENV_DIR" ]; then
    run rm -rf "$VENV_DIR"
  fi
fi

if [ "$VACUUM_JOURNAL" = "1" ] && command -v journalctl >/dev/null 2>&1; then
  run journalctl --vacuum-size=100M
fi

echo "cleanup_done=$([ "$APPLY" = "1" ] && echo true || echo dry_run)"
echo "next_check_commands:"
echo "  systemctl list-units 'cryptoforge*' --all --no-pager"
echo "  systemctl list-timers 'cryptoforge*' --all --no-pager"
echo "  df -h / /opt 2>/dev/null || df -h /"
echo "  free -h"
