# Supabase Market Data Cache

CryptoForge can persist a bounded market-data cache and decision journal in
Supabase. Supabase is not the execution source of truth: Bybit remains the
place to verify balances, open orders and submitted trades before live actions.

## Migration

The schema is in:

```text
supabase/migrations/20260927000100_market_data_cache.sql
```

When the Supabase GitHub integration is connected, Supabase should pick up this
migration from the repository. The migration creates server-side tables for:

- `market_candles`
- `market_tickers`
- `selected_universe`
- `strategy_signals`
- `trade_decisions`
- `bot_health`

All tables have RLS enabled. `anon` and `authenticated` are revoked. Only the
server-side `service_role` gets REST access.

## Sync

After the migration is applied, run:

```bash
PYTHONPATH=src .venv/bin/python scripts/sync_supabase_market_data.py \
  --live-config /opt/cryptoforge/config/freqtrade.live-pilot.json
```

Required environment variables:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SECRET_KEY`

The sync writes latest tickers, bounded candles and a `bot_health` row. It can
run on the VPS or on another host with a better route to Bybit.

## Trading Use

The first safe use is analysis and observability: strategy research, dashboards,
and checking what data was available around a decision. A live bot may later read
cached candles or precomputed signals from Supabase, but it must still check
Bybit directly before placing or cancelling real orders.
