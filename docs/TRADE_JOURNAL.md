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
