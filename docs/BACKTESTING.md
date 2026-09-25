# Backtesting Framework

Backtests are research jobs. They must stay lower priority than the
trading runtime, use bounded datasets and save summaries instead of
unlimited raw output.

## Baseline Procedure

Print the reproducible VPS commands:

```bash
.venv/bin/python scripts/baseline_backtest_commands.py
```

The commands use:

- Freqtrade installed at `/opt/cryptoforge/app/venv/bin/freqtrade`;
- config `/opt/cryptoforge/config/freqtrade.baseline-dry-run.json`;
- Bybit Spot;
- pair `BTC/USDT`;
- timeframe `5m`;
- timerange `20260923-20260925`;
- fee `0.001`;
- `--export none`;
- `--cache none`;
- `nice -n 10 ionice -c2 -n7`;
- `--no-parallel-download` for data download.

Candles are reproducible and disposable. They live under
`/opt/cryptoforge/data` and can be re-downloaded from Bybit public data.
Do not commit downloaded candle files.

## Execution Assumptions

- Spot only.
- No leverage, futures or margin.
- Fees are included with `--fee`.
- Static pairlist for baseline verification.
- Resource-bounded timeranges on the current 1 vCPU / 1 GB VPS.

## Leakage Check

`find_obvious_future_leakage()` flags common lookahead patterns:

- negative `shift()`;
- centered rolling windows;
- direct `.iloc[-1]` full-dataframe usage.

This static check is not a proof of correctness, but it catches common
mistakes before a backtest is trusted.

## Verification Snapshot

The Phase 9 baseline backtest already verified this procedure on the VPS:

- downloaded 701 candles;
- ran `BTC/USDT` 5m for `20260923-20260925`;
- included fee `0.001`;
- exported no unlimited raw results;
- swap remained `0`;
- disk remained about `30%`;
- no lingering Freqtrade process remained.
