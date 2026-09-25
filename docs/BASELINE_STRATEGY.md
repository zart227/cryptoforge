# Baseline Strategy

`CryptoForgeBaselineStrategy` is a transparent control strategy for
dry-run testing and future champion/challenger comparisons. It is not an
optimized historical winner.

## Indicators

- `ema_fast`: 12-period EMA, trend direction.
- `ema_slow`: 36-period EMA, slower trend filter.
- `rsi`: 14-period RSI, momentum confirmation.
- `volume_ratio`: current volume divided by 20-candle average volume.
- `atr_pct`: 14-candle ATR divided by close, volatility filter.

All indicators are calculated from current and past candles only. The
strategy does not use negative shifts, centered rolling windows or future
candles.

## Entry Logic

A long entry can be signaled when:

- fast EMA is above slow EMA;
- close is above fast EMA;
- RSI is at least 55;
- volume is above its 20-candle average by the configured ratio;
- ATR percentage is inside the configured volatility band;
- volume is positive.

The entry tag is `ema_rsi_volume_atr_baseline`.

## Exit Logic

An exit can be signaled when:

- fast EMA falls below slow EMA;
- RSI drops to 45 or lower;
- ATR percentage exceeds the configured maximum volatility band.

The exit tag is `baseline_exit_signal`. Freqtrade ROI and stoploss rules
remain active in addition to the exit signal.

## Backtest Scope

The first verification backtest should remain resource-bounded:

- Bybit Spot only.
- `BTC/USDT` only.
- 5m timeframe.
- Short timerange such as one to three days.
- Dry-run style config with `stake_amount=10` and `dry_run_wallet=1000`.

Version metadata is stored in `config/baseline_strategy_metadata.json`.

## Verification Snapshot

Resource-bounded VPS backtest on 2026-09-25:

- Runtime: Freqtrade 2026.8 on the existing 1 vCPU / 939 MiB VPS.
- Pair: `BTC/USDT`.
- Exchange/mode: Bybit Spot.
- Timeframe: 5m.
- Timerange: `20260923-20260925`.
- Loaded backtest window after startup candles:
  `2026-09-23 06:40:00` to `2026-09-25 00:00:00`.
- Downloaded candles: 701.
- Fee: `0.001` per side as passed to Freqtrade.
- Starting balance: `1000 USDT`.
- Stake amount: `10 USDT`.
- Trades: 5.
- Average profit: `-0.52%`.
- Total profit: `-0.257 USDT` (`-0.03%`).
- Max drawdown: `0.257 USDT` (`0.03%`).
- Win/draw/loss: `0 / 0 / 5`.

This result is intentionally not tuned. The baseline exists so later
strategy work has a reproducible control to beat on risk-adjusted terms.

Post-backtest VPS state:

- Swap used: `0`.
- Root filesystem: `5.5G / 20G`, about `30%`.
- Available RAM after process exit: about `449 MiB`.
- No lingering Freqtrade process remained.
