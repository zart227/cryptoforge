# CryptoForge Architecture

CryptoForge is designed as a safety-first, Bybit Spot-only research and
paper-trading system.

## Active Constraints

- Exchange: Bybit only
- Market type: Spot only
- Execution: dry-run / paper trading only
- Futures, margin, leverage, and real-money execution are disabled
- Hard risk limits live outside strategies and future ML systems

## Target Flow

```text
Bybit Spot public data
  -> Market data layer
  -> Market scanner
  -> Market regime detector
  -> Baseline strategy
  -> Independent risk engine
  -> Freqtrade dry-run execution
  -> Local state and SQLite outbox
  -> Supabase durable history and research metadata
```

## Persistence Policy

Supabase stores valuable durable state such as trades, metrics,
strategy versions, experiments, and system events. It must not be a
single point of failure for managing already-open simulated positions.

The local runtime keeps critical local state and a durable outbox.
Supabase outages should queue events locally, retry with idempotency,
and trigger fail-safe behavior when data integrity policy requires it.

Bulk reproducible market data, temporary backtest output, debug logs,
and failed experiment artifacts are not long-term durable assets.

## Resource Policy

The current VPS is small, so trading stability takes priority over
research. Heavy backtests, optimization, and future FreqAI work must run
only when they cannot starve the trading runtime.
