# CryptoForge Final End-To-End Audit

Audit date: 2026-09-25.

## Executive Summary

CryptoForge is ready for continued dry-run/paper development on Bybit
Spot. It is not ready for autonomous real-money trading yet.

Working today:

- Bybit public data and scanner;
- market regime classification;
- baseline dry-run strategy;
- independent hard-risk engine;
- Freqtrade dry-run service;
- durable local outbox;
- Supabase schema and server-side sync path;
- trade journal and performance metrics;
- monitoring/fail-safe checks;
- optional Telegram notification module;
- backup, restore and migration exports;
- security, quant, resource and code-quality audit documentation.

Still not implemented:

- real-money live config;
- live kill switch wired to exchange execution;
- autonomous live pilot;
- heavy FreqAI training;
- production notification runbook with confirmed Telegram delivery;
- stronger VPS migration.

The current VPS can run bounded dry-run verification, but it is too small
for heavy continuous research.

## Working

- Bybit public market data smoke works.
- Market Scanner works and ranked live public candidates.
- Market Regime works in deterministic tests.
- Baseline strategy loads and backtests in Freqtrade.
- Independent Risk Engine enforces hard sizing, loss and drawdown gates.
- Freqtrade dry-run service reaches `RUNNING` and returns to
  inactive/disabled after controlled tests.
- Trade Journal stores canonical trade records and feature snapshots.
- Supabase migrations are applied and service-role access is documented.
- Local outbox survives restart and supports retries/dead-lettering.
- Monitoring/fail-safe produces visible critical/warning states.
- Backup and restore tooling created and verified a local archive.
- Migration export/import tooling created and verified a local package.

## Partially Working

- Telegram notifications are implemented and unit-tested with mocks.
  A real delivery smoke succeeded on 2026-09-25 using local environment
  credentials; token and chat ID were not printed.
- Supabase sync is available through the outbox path, but the trading
  runtime does not yet depend on Supabase for order management.
- Backtesting is reproducible and bounded, but the sample has only 5
  trades and cannot validate profitability.
- Resource audit measured real current usage, but max RSS for the
  backtest was unavailable because the VPS lacks GNU/BSD `time -v`.

## Not Implemented

- Autonomous real-money live trading.
- Dedicated live sub-account workflow.
- Separate live Freqtrade config.
- Exchange-side live kill switch.
- Live no-new-entry operator switch.
- FreqAI model training/execution.
- Automatic strategy promotion into live execution.
- Futures, margin, leverage and withdrawals by design.

## Test Results

Latest full non-integration suite:

- `121 passed, 1 deselected`;
- selected marker: `-m 'not integration'`;
- secret scan found only TypeSafe placeholder examples in docs.

Live/remote smoke measurements:

- Bybit public scanner smoke completed successfully.
- VPS Freqtrade dry-run service reached `RUNNING`.
- VPS bounded baseline backtest exited with status `0`.
- Backup verify/restore rehearsal succeeded.
- Migration verify/import rehearsal succeeded.

## Resource Usage

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

Trader dry-run service:

- strategy: `CryptoForgeNoEntryStrategy`;
- run mode: dry-run;
- exchange: Bybit Spot;
- max RSS: `303704 KiB` (`296.6 MiB`);
- systemd CPU consumed: `6.138s`;
- swap after stop: `0 MiB`;
- service after stop: `inactive` and `disabled`.

Scanner:

- wall time: `1.53s`;
- max RSS: `26396 KiB` (`25.8 MiB`);
- swaps: `0`.

Light backtest:

- wall time: `158.089s`;
- user CPU: `5.071s`;
- system CPU: `0.838s`;
- trades: `5`;
- total profit: `-0.257 USDT`;
- RAM after run: `447 MiB` available;
- swap after run: `0 MiB`;
- disk after run: `30%`.

## Security

- `.env` local permissions: `600`.
- No `.env`, private key, or known plaintext exchange/Supabase/Telegram
  secret is tracked.
- Git history scan did not find configured secret assignment patterns.
- VPS CryptoForge logs/data scan did not find configured secret patterns.
- No CryptoForge container is exposed.
- No CryptoForge public admin endpoint was identified.
- Freqtrade configs contain no exchange credentials.
- Real trading, futures, margin and leverage remain disabled.
- Withdrawal permission is never required.

## Bybit Integration

Working:

- public Spot instruments/tickers/klines;
- scanner smoke with live public data;
- Freqtrade dry-run exchange resolution for Bybit;
- bounded Bybit Spot backtest.

Safety:

- committed configs are Spot only;
- API keys are not embedded in Freqtrade JSON;
- live trading remains disabled.

## Supabase Integration

Working:

- schema migrations exist for strategies, versions, experiments, trades,
  features, model metadata, metrics and system events;
- service-role migration grants server-side REST access;
- outbox can deliver system events through the Supabase sink.

Boundary:

- `service_role` key must remain server-side;
- current runtime can continue managing positions during Supabase outage
  because outbox persists locally.

## Outbox And Data Integrity

Working:

- SQLite outbox persists events locally;
- retry backoff and dead-lettering are tested;
- restart recovery is tested;
- idempotency keys prevent duplicate remote system events;
- monitoring blocks new entries when outbox age/depth exceeds
  fail-safe thresholds.

## Risk Management

Working:

- risk per trade capped at `0.5%`;
- max daily loss capped at `2%`;
- max portfolio drawdown capped at `10%`;
- max position notional capped at `5%`;
- max simultaneous positions default `2`;
- no-new-trade states do not force-close existing positions.

Forbidden:

- martingale;
- doubling after loss;
- unlimited averaging down;
- leverage/futures/margin;
- automatic risk-limit increases.

## Market Scanner

Working:

- bounded public-data scan;
- cheap/expensive shortlist separation;
- rejects stablecoin-like and leveraged/special tokens;
- scanner smoke selected 4 candidates and rejected 259 symbols.

## Market Regime

Working:

- deterministic regime classifier;
- trend/range/volatile behavior covered by tests;
- regime is included in trade context and metrics grouping.

## Baseline Strategy

Working:

- transparent EMA/RSI/volume/ATR control strategy;
- no obvious lookahead patterns found;
- Freqtrade backtest ran successfully;
- not tuned for profit.

Result:

- 5 trades;
- `0 / 0 / 5` win/draw/loss;
- `-0.257 USDT`;
- this is a control strategy, not a valid profitable strategy claim.

## Backtest Quality

Good:

- bounded timerange;
- fee included;
- Spot only;
- no unlimited exports;
- low-priority command.

Blocking for validity claims:

- only 5 trades;
- single-pair BTC/USDT sample;
- spread/slippage realism requires more paper evidence;
- no full out-of-sample/walk-forward campaign has been run.

## Strategy Lab

Working:

- day/night/resource gates;
- no heavy research during constrained trading runtime;
- experiment metadata persisted through outbox;
- candidate recommendations do not change live risk limits.

## FreqAI Status

Heavy FreqAI is **NOT ACTIVE**.

Defined but inactive:

- candidate model families;
- chronological train/validation/test;
- walk-forward process;
- feature/model versioning;
- artifact checksums;
- shadow-mode validation;
- drift/deactivation criteria.

ML cannot autonomously increase live exposure or promote itself to live.

## Known Limitations

- Current VPS has only `939 MiB` RAM and slow cold starts.
- Backtest sample is too small for strategy validity.
- Telegram delivery is smoke-tested manually; it is not committed as an
  automated integration test.
- Live trading has no live config, kill switch, or dedicated sub-account
  workflow yet.
- Supabase is not yet used as a real-time operational dashboard.

## Technical Debt

- Optional notifications have a real delivery smoke, but still need an
  operational runbook for alert severity and quiet hours.
- Resource measurement should be repeated after migration to a stronger
  VPS.
- A broader multi-pair/multi-regime backtest campaign is needed before
  any strategy promotion claim.
- Live pilot needs separate config and explicit operator command, not a
  mutation of dry-run configs.

## VPS Bottlenecks

- 1 vCPU class host;
- trader RSS near `297 MiB`;
- backtest took `158s`;
- heavy ML disabled;
- cold starts can take minutes.

## Migration Readiness

Ready:

- compact backup/export;
- checksum verification;
- restore/import rehearsal;
- Bybit IP-whitelist migration procedure documented.

Not yet done:

- actual migration to 2 CPU / 8 GB VPS.

## What Changes After 2 CPU / 8 GB Upgrade

After migration:

- run broader backtests without starving dry-run trading;
- enable larger scanner candidate windows;
- add regular paper-trading health jobs;
- consider light FreqAI experiments at night;
- keep live trading disabled until Phase 31 gates are complete.

## Next Phase

Phase 31 may start only as a controlled live pilot design/build phase. It
must not enable real trading until every live pre-check is implemented,
tested and explicitly approved by the operator.

## Final Checklist

- [x] Bybit public data works.
- [x] Market Scanner works.
- [x] Market Regime works.
- [x] Baseline strategy works.
- [x] Independent Risk Engine works.
- [x] Freqtrade dry-run works.
- [x] Trade Journal works.
- [x] Supabase sync works.
- [x] Local outbox works through outage/recovery.
- [x] Monitoring/fail-safe works.
- [x] Backup and tested restore work.
- [x] Migration export is ready.
- [x] Real trading is still disabled.
- [x] Futures are still disabled.
- [x] Leverage is still disabled.
- [x] Heavy FreqAI is honestly marked inactive if not running.
- [x] `FINAL_AUDIT.md` accurately distinguishes working/partial/not
  implemented.
