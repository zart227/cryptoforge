# End-To-End Bybit Spot Dry-Run

Phase 12 connects the safe paper-trading path:

```text
Bybit public data
  -> market scanner
  -> market regime detector
  -> position protection planner
  -> independent risk engine
  -> Freqtrade dry-run configuration/runtime
```

The active dry-run config remains safe:

- `dry_run=true`
- Bybit only
- Spot only
- no futures
- no margin
- no leverage
- no exchange credentials embedded in Freqtrade config

`scripts/dry_run_pipeline_smoke.py` builds live public-data candidate
plans without placing orders. It validates the Freqtrade dry-run config
before doing any market work.

## Controlled Lifecycle

The first controlled lifecycle for Phase 12 is paper/backtest only:

- Phase 9 backtest exercised entries and exits on `BTC/USDT`.
- Phase 12 pipeline produces protected dry-run candidate plans with
  regime, SL/TP and risk sizing context.
- The runtime verification uses Freqtrade dry-run startup/stop, not live
  orders.

Real-money execution remains impossible under the committed configs.

## Verification Snapshot

Local public-data pipeline smoke on 2026-09-25:

- Config validation: passed for `config/freqtrade.baseline-dry-run.json`.
- Candidate plans built: 3.
- Runtime: 3.72 seconds.
- Peak RSS: 97.6 MB.
- Each plan included regime, SL/TP context and independent risk decision.
- All produced risk decisions were `APPROVED` for paper-trade sizing.

Safety checks:

- `dry_run=true`.
- `trading_mode=spot`.
- `margin_mode` empty.
- exchange is `bybit`.
- no exchange credentials embedded in Freqtrade config.
- no leverage setting in the dry-run config.

VPS runtime restart/resource verification after access was restored:

- First Freqtrade dry-run start reached `Changing state to: RUNNING`.
- Second Freqtrade dry-run start reached `Changing state to: RUNNING`.
- Both runs logged `Dry run is enabled`.
- Both runs used exchange `Bybit`.
- Both runs resolved `CryptoForgeBaselineStrategy`.
- Service remained `inactive` and `disabled`; the test did not enable
  boot startup.
- No lingering Freqtrade process remained after shutdown.
- Baseline dry-run SQLite DB existed with `trades_count=0` and
  `orders_count=0`, so the restart check did not create duplicate
  trade/order state.
- Post-test resources: swap `0`, root filesystem `5.5G / 20G` (`30%`),
  available RAM about `458 MiB`.

The current VPS can run the bounded dry-run verification, but cold starts
remain slow and should stay part of operational expectations.
