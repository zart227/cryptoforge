# CryptoForge

Adaptive crypto trading and strategy research platform for Bybit.

CryptoForge is currently being bootstrapped from `IMPLEMENTATION_PLAN.md`.
The active implementation constraints are:

- Bybit only
- Spot only
- Dry-run / paper trading only
- No futures, margin, leverage, or real-money execution
- Independent hard risk controls
- Resource-conscious operation for a small VPS

## Current Status

The repository is in Phase 0/1 bootstrap. The VPS has been inspected
read-only and baseline documentation has been created. No trading runtime
has been installed or started yet.

## Repository Layout

- `IMPLEMENTATION_PLAN.md` - authoritative progress plan
- `docs/` - architecture, operations, VPS audit, and later phase docs
- `config/` - non-secret configuration templates
- `src/cryptoforge/` - application code
- `tests/` - automated tests
- `supabase/migrations/` - future Supabase schema migrations
- `user_data/strategies/` - future Freqtrade strategies

## Safety

Do not commit `.env`, exchange credentials, Supabase service keys,
Telegram tokens, SSH keys, or generated runtime state. Real trading is
out of scope until a separate explicit approval and audit.
