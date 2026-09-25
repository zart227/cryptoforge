# Bybit Public Market Data

Date: 2026-09-25

## Scope

CryptoForge uses Bybit V5 public market-data endpoints with
`category=spot`. No API key or secret is required for the Phase 4 public
data checks.

Implemented endpoints:

- `/v5/market/instruments-info`
- `/v5/market/tickers`
- `/v5/market/kline`

Timeframes:

- primary: `5m`
- informative candidates: `15m`, `1h`
- `1m` is intentionally not enabled

## Runtime Guard

The market-data module computes candle freshness. New entries are allowed
only when the latest closed candle is within the accepted lag window.
Missing or stale candles set `allow_new_entries=false` in the snapshot.

## Errors

Network timeouts, HTTP errors, Bybit logical errors, and rate-limit
responses are converted into explicit recoverable exceptions. They are
not allowed to crash higher-level trading logic without classification.

## Verification

Unit tests cover:

- spot USDT instrument parsing
- ticker decimal parsing
- malformed candle rejection
- Bybit reverse-order kline sorting
- missing/stale candle detection

Live integration test:

```text
pytest -m integration tests/test_market_data.py
```

The integration test calls Bybit public endpoints and verifies that
`BTCUSDT` is available as a Spot USDT instrument and that a 5m snapshot
can be fetched without credentials.

Smoke check:

```text
PYTHONPATH=src python scripts/bybit_market_data_smoke.py
```

Verified results on 2026-09-25:

- local unit tests: `6 passed`
- local live integration test: `1 passed`
- local smoke check:
  - active Spot USDT pairs: `392`
  - `BTCUSDT` ticker returned
  - 5m candles returned
  - 15m and 1h informative candles returned
  - freshness: `fresh`
  - `allow_new_entries=true`
- VPS smoke check:
  - active Spot USDT pairs: `392`
  - `BTCUSDT` ticker returned
  - 5m candles returned
  - 15m and 1h informative candles returned
  - freshness: `fresh`
  - `allow_new_entries=true`
- VPS post-check resources:
  - available RAM around 450 MiB
  - swap used: 0 B
  - root filesystem around 30% used

The market-data smoke process exits after fetching data and does not run
as a daemon.
