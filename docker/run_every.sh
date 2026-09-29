#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "usage: run_every.sh <interval-seconds> <command> [args...]" >&2
  exit 2
fi

INTERVAL_SECONDS="$1"
shift

while true; do
  STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "cryptoforge_loop_start started_at=${STARTED_AT} command=$*"
  if "$@"; then
    echo "cryptoforge_loop_ok command=$*"
  else
    STATUS="$?"
    echo "cryptoforge_loop_error status=${STATUS} command=$*" >&2
  fi
  sleep "$INTERVAL_SECONDS"
done
