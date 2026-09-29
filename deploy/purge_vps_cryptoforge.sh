#!/usr/bin/env bash
set -euo pipefail

APPLY=0
APP_ROOT="${CRYPTOFORGE_APP_ROOT:-/opt/cryptoforge}"
USER_NAME="${CRYPTOFORGE_USER:-cryptoforge}"

usage() {
  cat <<'EOF'
Usage:
  purge_vps_cryptoforge.sh --apply

Stops, disables, masks and removes CryptoForge from the VPS.

This intentionally removes:
  - cryptoforge systemd services and timers
  - /etc/systemd/system/cryptoforge-*.service
  - /etc/systemd/system/cryptoforge-*.timer
  - /etc/logrotate.d/cryptoforge
  - /opt/cryptoforge by default
  - cryptoforge system user when possible

It does not touch Docker, Postgres, Guacamole, VPN, x-ui, xray, firewall
or non-CryptoForge files.
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
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ "$APPLY" != "1" ]; then
  usage >&2
  echo "" >&2
  echo "Refusing to purge without --apply." >&2
  exit 2
fi

if [ "$(id -u)" != "0" ]; then
  echo "Run as root on the VPS." >&2
  exit 2
fi

echo "purge_target_app_root=$APP_ROOT"
echo "purge_target_user=$USER_NAME"

if command -v systemctl >/dev/null 2>&1; then
  mapfile -t UNITS < <(
    systemctl list-unit-files 'cryptoforge*' --no-legend --no-pager 2>/dev/null | awk '{print $1}' || true
    systemctl list-units 'cryptoforge*' --all --no-legend --no-pager 2>/dev/null | awk '{print $1}' || true
  )

  if [ "${#UNITS[@]}" -gt 0 ]; then
    mapfile -t UNIQUE_UNITS < <(printf '%s\n' "${UNITS[@]}" | sed '/^$/d' | sort -u)
    for unit in "${UNIQUE_UNITS[@]}"; do
      run systemctl stop "$unit" || true
    done
    for unit in "${UNIQUE_UNITS[@]}"; do
      run systemctl disable "$unit" || true
    done
    for unit in "${UNIQUE_UNITS[@]}"; do
      run systemctl mask "$unit" || true
    done
  fi
fi

run rm -f /etc/systemd/system/cryptoforge-*.service
run rm -f /etc/systemd/system/cryptoforge-*.timer
run rm -f /etc/logrotate.d/cryptoforge

if command -v systemctl >/dev/null 2>&1; then
  run systemctl daemon-reload
  run systemctl reset-failed 'cryptoforge*' || true
fi

if [ -d "$APP_ROOT" ]; then
  run rm -rf "$APP_ROOT"
fi

if id "$USER_NAME" >/dev/null 2>&1; then
  if command -v userdel >/dev/null 2>&1; then
    run userdel "$USER_NAME" || true
  fi
fi

echo "purge_done=true"
echo "verification_commands:"
echo "  systemctl list-units 'cryptoforge*' --all --no-pager"
echo "  systemctl list-unit-files 'cryptoforge*' --no-pager"
echo "  test ! -e /opt/cryptoforge && echo cryptoforge_dir_removed"
echo "  id cryptoforge || true"
