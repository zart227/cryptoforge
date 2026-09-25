# CryptoForge Final Resource Audit

Audit date: 2026-09-25.

## Current VPS

Host: `ruvds-xl3sl`.

System snapshot:

- uptime: 23 days, 19 hours;
- load average: `0.08, 0.02, 0.01`;
- RAM: `939 MiB` total, `468 MiB` available before measurement;
- swap: `1023 MiB` total, `0 MiB` used;
- disk `/`: `20G` total, `5.5G` used, `14G` available, `30%` used.

CryptoForge footprint:

- `/opt/cryptoforge`: `868M`;
- `/opt/cryptoforge/app`: `702M`;
- `/opt/cryptoforge/data`: `224K`;
- `/opt/cryptoforge/logs`: `40K`;
- `/opt/cryptoforge/backups`: `4.0K`;
- dry-run SQLite DB: `94208` bytes;
- baseline dry-run SQLite DB: `94208` bytes;
- downloaded `BTC_USDT-5m.feather`: `24594` bytes.

Service state after tests:

- `cryptoforge-freqtrade.service`: `inactive`;
- boot state: `disabled`;
- no lingering `freqtrade trade` process found.

## Trader RAM

Measured by starting `cryptoforge-freqtrade.service`, waiting until
Freqtrade logged `Changing state to: RUNNING`, sampling RSS, then stopping
the service.

- strategy: `CryptoForgeNoEntryStrategy`;
- run mode: dry-run;
- exchange: Bybit Spot;
- max RSS: `303704 KiB` (`296.6 MiB`);
- samples with RSS: `31`;
- systemd reported CPU consumed: `6.138s`;
- swap after stop: `0 MiB`;
- disk after stop: `30%`;
- service after stop: `inactive` and `disabled`.

## Scanner CPU/RAM

Measured locally with:

```text
/usr/bin/time -v .venv/bin/python scripts/market_scanner_smoke.py
```

Result:

- selected candidates: `4`;
- cheap candidates: `12`;
- rejected candidates: `259`;
- wall time: `1.53s`;
- user CPU: `0.16s`;
- system CPU: `0.02s`;
- CPU percent: `12%`;
- max RSS: `26396 KiB` (`25.8 MiB`);
- swaps: `0`.

## Light Backtest CPU/RAM

Measured on the VPS with the bounded baseline backtest:

```text
nice -n 10 ionice -c2 -n7 freqtrade backtesting ... --pairs BTC/USDT --timeframe 5m --timerange 20260923-20260925 --fee 0.001 --export none --cache none
```

Result:

- exit status: `0`;
- wall time: `158.089s`;
- user CPU: `5.071s`;
- system CPU: `0.838s`;
- trades: `5`;
- total profit: `-0.257 USDT`;
- final balance: `999.743 USDT`;
- max drawdown: `0.257 USDT`;
- RAM after run: `447 MiB` available;
- swap after run: `0 MiB`;
- disk after run: `30%`.

The VPS does not have `/usr/bin/time` or `/bin/time`, so max RSS for this
backtest run was not available without installing extra packages.

## Disk And Logs

Log files on VPS:

- `phase12-run1.log`: `7889` bytes;
- `phase12-run2.log`: `7780` bytes;
- `freqtrade-bootstrap.log`: `9212` bytes;
- `freqtrade-service.log`: `8148` bytes.

Phase 22 added a logrotate template that rotates daily or at `25M`, keeps
14 compressed rotations, and uses `copytruncate`.

## Outbox Footprint

No VPS outbox database was present in `/opt/cryptoforge` during this
measurement. Local restore/import rehearsal directories contained only
test artifacts under gitignored `data/`.

The durable outbox implementation remains tested by unit tests and the
earlier Supabase smoke write. Outbox growth thresholds are covered by the
monitoring fail-safe.

## Supabase Sync Behavior

Current committed runtime does not require Supabase for order management.
When Supabase is offline, local outbox events are retained and monitoring
surfaces a warning. New entries are blocked only when outbox age/depth
exceeds fail-safe thresholds.

## Current VPS Limitations

The current VPS is usable for bounded dry-run verification, but it is too
small for heavy continuous research:

- 1 vCPU class host;
- `939 MiB` RAM;
- trader startup RSS near `297 MiB`;
- Freqtrade cold starts are slow;
- bounded backtest took `158s`;
- heavy ML/FreqAI is explicitly not active.

## Upgrade Triggers

Upgrade the VPS before enabling heavier workloads if any of these happen:

- trader RSS plus system baseline leaves less than `256 MiB` available;
- swap usage becomes sustained rather than `0`;
- disk usage reaches `70%` warning or higher;
- backtests/research overlap with daytime trading;
- scanner/backtest runtime blocks monitoring or outbox flushes;
- FreqAI training is needed;
- real-money trading is approved and requires more operational headroom.
