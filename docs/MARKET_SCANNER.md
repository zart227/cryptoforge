# Market Scanner

The scanner builds a bounded Bybit Spot USDT candidate set without
fetching candles for every listed market.

## Stages

1. Fetch active Bybit Spot USDT instruments and 24h tickers.
2. Reject stablecoin-like bases, leveraged/special tokens, missing
   minimum order size, low 24h turnover and excessive bid/ask spread.
3. Sort the remaining universe by quote turnover and cap the cheap
   shortlist.
4. Fetch OHLCV only for the expensive shortlist.
5. Score candidates with a balanced mix of liquidity, ATR, realized
   volatility and momentum, while penalizing wide spreads and volume
   anomalies.

The scanner deliberately avoids selecting a market solely because it had
an extreme 24h gain. Pump-like conditions are limited through intraday
range and volume-anomaly guards.

## Resource Bounds

Initial defaults:

- `cheap_shortlist_size`: 30 markets.
- `expensive_shortlist_size`: 12 markets.
- `output_limit`: 8 markets.
- `candle_limit`: 120 candles on the 5m timeframe.

The live smoke script uses a smaller expensive shortlist for the current
1 vCPU / 1 GB VPS baseline:

```bash
.venv/bin/python scripts/market_scanner_smoke.py
```

The script prints selected count, rejected count, elapsed time and peak
RSS. It uses public Bybit endpoints only and does not require trading
credentials.

## Verification Snapshot

Local live smoke on 2026-09-25 with
`cheap_shortlist_size=12`, `expensive_shortlist_size=4`,
`output_limit=4` and `candle_limit=80`:

- Selected candidates: 4.
- Cheap candidates: 12.
- Rejected markets: 259.
- Elapsed time: 2.49 seconds.
- Peak RSS: 89.2 MB.

This fits the current 1 vCPU / 1 GB VPS resource envelope for a bounded
scanner run.
