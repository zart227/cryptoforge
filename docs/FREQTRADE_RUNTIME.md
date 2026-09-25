# Freqtrade Runtime

Date: 2026-09-25

## Documentation Check

Official Freqtrade documentation reviewed during Phase 3:

- Freqtrade installation documentation for current Linux/Ubuntu guidance
- Freqtrade exchange-specific notes for Bybit
- Freqtrade strategy quickstart/dry-run notes

Findings:

- Python 3.11+ is supported; the VPS has Python 3.12.
- Bybit Spot is a supported exchange mode.
- Bybit Spot does not support stoploss on exchange in Freqtrade, so
  `stoploss_on_exchange` remains `false`.
- Freqtrade dry-run uses live market data while avoiding real exchange
  orders.
- Bybit demo mode is separate from dry-run and must not be enabled for
  this implementation.

## Installation

Freqtrade was installed natively into:

- `/opt/cryptoforge/app/venv`

Installed version:

- `freqtrade 2026.8`

Docker was intentionally not used on the current VPS because of the
small 1 vCPU / 939 MiB RAM profile.

## Active Safety Configuration

Configuration template:

- `config/freqtrade.dry-run.json`

Runtime target path:

- `/opt/cryptoforge/config/freqtrade.dry-run.json`

Safety properties:

- `dry_run` is `true`
- `dry_run_wallet` is `1000`
- `trading_mode` is `spot`
- `margin_mode` is empty
- exchange is `bybit`
- API key and secret are empty
- Telegram is disabled
- API server is disabled
- `stoploss_on_exchange` is `false`

Bootstrap strategy:

- `CryptoForgeNoEntryStrategy`

This strategy intentionally never opens a trade. It exists only to
verify Freqtrade startup and dry-run configuration safely before the
real baseline strategy phase.

## Verification Results

Phase 3 partial runtime verification was performed on 2026-09-25.

Confirmed:

- `freqtrade --version` reports `freqtrade 2026.8`.
- Freqtrade recognizes Bybit as officially supported.
- Bybit Spot market discovery can see `BTC/USDT`.
- Runtime reached `state='RUNNING'` with:
  - dry-run enabled
  - DB `sqlite:////opt/cryptoforge/data/tradesv3.dry_run.sqlite`
  - `max_open_trades: 2`
  - exchange `Bybit`
  - static whitelist `BTC/USDT`
  - strategy `CryptoForgeNoEntryStrategy`
- Freqtrade created persistent SQLite state under `/opt/cryptoforge/data`.
- The dry-run database had `0` trades and `0` orders after the no-entry
  test.
- Post-stop memory returned to about 433-446 MiB available.
- Root filesystem usage after installing Freqtrade was about 5.5 GiB
  used / 14 GiB available / 30% used.

Observed constraints:

- Cold startup is slow on the current 1 vCPU VPS; imports and startup can
  take multiple minutes.
- A `timeout --signal=INT` test reached Freqtrade cleanup but left the
  test process alive. Exact PID `SIGTERM` stopped it.
- A later `timeout --signal=TERM` restart test left no lingering process,
  but did not reach full logged startup within the 210 second test
  window.

Because of this, the runtime is installed and can start in dry-run, but
clean stop/start reliability is not yet fully proven. A systemd service
with explicit `TimeoutStopSec`, `KillSignal=SIGTERM`, memory limits, and
log policy should be created before declaring Phase 3 complete.
