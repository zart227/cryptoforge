#!/usr/bin/env bash
set -euo pipefail

: "${BYBIT_API_KEY:?BYBIT_API_KEY is required}"
: "${BYBIT_API_SECRET:?BYBIT_API_SECRET is required}"

export FREQTRADE__EXCHANGE__KEY="$BYBIT_API_KEY"
export FREQTRADE__EXCHANGE__SECRET="$BYBIT_API_SECRET"

exec /opt/cryptoforge/app/venv/bin/freqtrade trade \
  --config /opt/cryptoforge/config/freqtrade.live-pilot.json \
  --userdir /opt/cryptoforge/app/user_data \
  --strategy CryptoForgeBaselineStrategy \
  --logfile /opt/cryptoforge/logs/freqtrade-live-pilot.log
