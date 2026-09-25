# Market Regime Detector

The initial regime detector is deterministic and indicator-based. It
does not train, optimize or inspect future candles. The caller passes the
exact candle window available at decision time, and the classification is
stamped with the close time of the last supplied candle.

## Regimes

- `TREND_UP`: fast EMA is above slow EMA and the slow EMA slope is
  positive enough.
- `TREND_DOWN`: fast EMA is below slow EMA and the slow EMA slope is
  negative enough.
- `RANGE`: EMA separation and slope are small, or no stronger condition
  matched.
- `HIGH_VOLATILITY`: ATR percentage is above the configured threshold.
- `LOW_VOLATILITY`: ATR percentage is below the configured threshold.
- `UNKNOWN`: there is not enough candle history.

Volatility regimes are evaluated before trend regimes. This is
intentional: extreme volatility can invalidate simple trend assumptions.

## Inputs

The detector uses only OHLCV candles supplied by the caller:

- fast EMA
- slow EMA
- slow EMA slope over a configurable lookback
- ATR as a percentage of close
- realized volatility for observability

Default thresholds live in `RegimeConfig` in
`src/cryptoforge/regime.py`.

## Trade Context

Supabase already includes `public.trades.regime`. Strategies should copy
`RegimeClassification.trade_context_value` into that column when a trade
is opened. This gives later review, metrics and Strategy Lab experiments
the regime that was actually known at entry time.
