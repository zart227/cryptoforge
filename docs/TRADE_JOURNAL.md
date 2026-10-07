# Trade Journal

The trade journal defines a canonical trade record that can reconstruct a
completed dry-run trade without copying every internal Freqtrade row.

## Canonical Record

`CanonicalTradeRecord` stores:

- trade and external/Freqtrade identifiers;
- strategy name and version;
- exchange, market type, mode, pair, timeframe and side;
- open/close timestamps;
- entry/exit price, amount, stake, fees and PnL;
- stop loss, take profit and protection context;
- market regime;
- entry and exit reason;
- feature snapshot;
- MFE/MAE when the candle slice reliably covers the trade window.

The record is intentionally compact. Freqtrade remains the detailed local
execution state, while CryptoForge stores the decision and review
context needed for analysis.

## Outbox Delivery

`TradeJournal.record_trade()` validates the record and writes a durable
event to the SQLite outbox before any remote delivery. Event type is
`trade.{status}` and idempotency key is:

```text
trade-journal:{mode}:{trade_id}:{status}
```

This means Supabase outages do not lose trade context. The event can be
retried later by the existing outbox delivery path.

## Feature Snapshot

`TradeFeatureSnapshot` stores bounded features and a compact market
snapshot. It is suitable for `trade_features` in Supabase and for event
payloads. It should not contain unlimited candles, order books or raw
tick data.

## Validation

`validate_against_local_trade_state()` compares canonical fields against
the local Freqtrade-derived state before journaling. This prevents silent
drift between the execution state and the review record.

## Live Bybit Spot reconciliation

`cryptoforge.live_trade_journal` now reconciles **actual executions**, rather
than order-submission acknowledgements. The live executor runs it before
and after each cycle. If reconciliation fails, new entries pause while
position exits remain available, and `bot_health.live_trade_journal` records
the failure. There is no change to the Postgres schema.

The first run fetches the last 30 days of executions in paginated seven-day
windows. Subsequent runs overlap the previous cursor by one day and retain
all previously downloaded executions in an account-key-specific SQLite
cache under `data/live-journal-*.sqlite`. Preserve this cache when migrating
the executor. For a different initial history boundary, run the standalone
module with `--since <ISO timestamp>` before its first initialization.
The module reads the exchange and writes the journal; it never places orders.

FIFO matching consumes all observed purchases and sales per USDT pair.
Rows are published to `public.trades` when either the acquisition or the
sale has a CryptoForge `cf-` order link; unrelated manual round trips are
excluded. This includes legacy CryptoForge instances. Each closed row is
an **execution-to-lot segment**, so a partial sale or a sale across multiple
purchases can create multiple rows. It is not a count of exchange orders.
Entry/exit reasons retain execution IDs, order IDs and origin. The remaining
part of each CryptoForge acquisition is an open row; when entirely consumed,
its remainder row becomes `cancelled` with zero quantity. This status is an
accounting placeholder, not an exchange order cancellation.

Realized PnL is **net of fees**, in USDT. Buy fees paid in base currency reduce
received inventory; USDT buy fees increase acquisition cost. Sell fees in
base currency increase consumed inventory; USDT sell fees reduce proceeds.
Fees and cost are allocated proportionally across partial closes, using
Decimal arithmetic. `realized_pnl_pct` is a ratio, not percentage points.
`fee_amount` is informational and must not be subtracted from PnL again.

Trades with unavailable fee currency, fees paid in a third token or extra
fees without an exchange rate have null PnL/fees and are flagged in health.
Sales without a matching acquisition are counted as `unmatched_sells` in
health and excluded from PnL; no acquisition cost is invented. FIFO is an
accounting convention: deposits, withdrawals and conversions outside Spot
executions can prevent the inventory from matching the wallet and require
separate reconciliation. The initial history boundary is reported in health.

Stable execution-based idempotency keys make retries and restarts safe.
All reconstructed trade rows are upserted in one REST transaction before
advancing the local cursor; a failed write is retried on the next cycle.
Telegram `/closed`, `/pnl` and `/summary` read these live records directly.
