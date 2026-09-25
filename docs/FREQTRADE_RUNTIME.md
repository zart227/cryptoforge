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

Initial observed constraints:

- Cold startup is slow on the current 1 vCPU VPS; imports and startup can
  take multiple minutes.
- A `timeout --signal=INT` test reached Freqtrade cleanup but left the
  test process alive. Exact PID `SIGTERM` stopped it.
- A later `timeout --signal=TERM` restart test left no lingering process,
  but did not reach full logged startup within the 210 second test
  window.

## Systemd Service

Service template:

- `deploy/systemd/cryptoforge-freqtrade.service`

Deployment target:

- `/etc/systemd/system/cryptoforge-freqtrade.service`

The service is intended for controlled dry-run runtime management. It
uses the `cryptoforge` system user, explicit `SIGTERM` stop behavior,
bounded start/stop timeouts, CPU and memory limits, and write access only
to `/opt/cryptoforge`.

The service should not be enabled for boot until monitoring, recovery,
and log rotation phases are in place.

## Systemd Verification

The systemd service was installed on the VPS and verified manually. It
is intentionally disabled for boot:

- `systemctl is-enabled cryptoforge-freqtrade.service` -> `disabled`

To avoid cleanup hangs seen during the first signal tests, websocket
market streams are disabled in the dry-run config with
`exchange.enable_ws=false`. The service also marks signal shutdown status
codes as successful.

Verified service cycle:

- `systemctl start cryptoforge-freqtrade.service`
- Freqtrade reached `Changing state to: RUNNING`
- dry-run mode was logged
- exchange was `Bybit`
- pair whitelist was `BTC/USDT`
- `systemctl stop cryptoforge-freqtrade.service`
- final systemd state was `inactive/dead`
- `Result=success`
- no lingering Freqtrade process remained

Measured during service verification:

- service memory around 400-490 MiB while starting/running
- post-stop available RAM around 449 MiB
- swap remained unused
- root filesystem remained about 30% used

Cold startup remains slow on the current 1 vCPU VPS and should be
treated as an operational constraint.
