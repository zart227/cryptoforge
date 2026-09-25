# Performance Metrics

Metrics are computed from stored `CanonicalTradeRecord` values. The
calculations are reproducible and do not depend on the current exchange
state.

## Formulas

- `net_pnl`: sum of closed-trade realized PnL.
- `gross_profit`: sum of positive realized PnL.
- `gross_loss`: sum of negative realized PnL.
- `fees`: sum of recorded fees.
- `trade_count`: count of closed trades with realized PnL.
- `win_rate`: winning trades divided by trade count.
- `profit_factor`: gross profit divided by absolute gross loss; `null`
  when there are no losses.
- `expectancy`: net PnL divided by trade count.
- `average_win`: gross profit divided by winning-trade count.
- `average_loss`: gross loss divided by losing-trade count.
- `max_drawdown`: largest peak-to-trough drop in the cumulative PnL
  curve.
- `Sharpe`: mean trade return divided by sample standard deviation.
- `Sortino`: mean trade return divided by downside sample standard
  deviation.

Win rate is reported but is not treated as the primary metric. A high win
rate with poor expectancy or drawdown is not a good strategy.

## Grouping

The module produces:

- daily metrics;
- strategy-version metrics;
- regime-specific metrics.

## Persistence

`MetricsPublisher` sends summary payloads through the durable SQLite
outbox as `metrics.summary` events. Supabase delivery can retry later if
the network or Supabase is unavailable.
