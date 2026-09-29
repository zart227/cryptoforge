#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: run_daily.sh <HH:MM> <command> [args...]" >&2
  exit 2
fi

TARGET_TIME="$1"
shift

case "$TARGET_TIME" in
  [0-2][0-9]:[0-5][0-9]) ;;
  *)
    echo "invalid HH:MM time: $TARGET_TIME" >&2
    exit 2
    ;;
esac

while true; do
  NOW_EPOCH="$(date +%s)"
  TODAY="$(date +%Y-%m-%d)"
  TARGET_EPOCH="$(date -d "${TODAY} ${TARGET_TIME}" +%s)"
  if [ "$TARGET_EPOCH" -le "$NOW_EPOCH" ]; then
    TARGET_EPOCH="$(date -d "${TODAY} ${TARGET_TIME} + 1 day" +%s)"
  fi
  SLEEP_SECONDS="$((TARGET_EPOCH - NOW_EPOCH))"
  echo "cryptoforge_daily_wait target=${TARGET_TIME} sleep_seconds=${SLEEP_SECONDS}"
  sleep "$SLEEP_SECONDS"
  echo "cryptoforge_daily_start command=$*"
  if "$@"; then
    echo "cryptoforge_daily_ok command=$*"
  else
    STATUS="$?"
    echo "cryptoforge_daily_error status=${STATUS} command=$*" >&2
  fi
done
