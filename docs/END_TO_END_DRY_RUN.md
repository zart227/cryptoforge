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

VPS runtime restart/resource verification was attempted next, but the
WireGuard SSH endpoint `10.77.0.1` became unreachable during the bounded
test (`ssh: connect to host 10.77.0.1 port 22: Connection timed out`).
Phase 12 remains partially open until VPS access is restored and the
restart/resource checks complete.
