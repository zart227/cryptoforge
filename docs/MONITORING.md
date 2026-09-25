# Monitoring And Fail-Safe

Phase 20 adds deterministic health checks for the trading runtime. The
monitoring layer does not place trades and does not close positions. It
decides whether the system is healthy enough to allow new entries and
surfaces the reason when it is not.

## Checks

CryptoForge monitors:

- trader process status;
- Bybit connectivity;
- latest candle freshness;
- CPU load;
- available RAM;
- swap usage;
- free disk;
- Supabase sync status;
- local outbox depth and oldest pending age;
- recent database errors;
- recent strategy errors;
- risk-limit state.

Each check returns one of:

- `ok`;
- `warning`;
- `critical`.

Critical checks that affect execution set `blocks_new_entries=true`.
Warnings are visible but do not automatically stop entries unless a
separate hard-risk rule already says so.

## No-New-Entry States

New entries are blocked when any of these states is present:

- trader process is not running;
- Bybit connectivity failed;
- market data is stale;
- CPU/RAM/swap/disk is beyond critical threshold;
- local outbox depth or age is beyond critical threshold;
- recent strategy errors are present;
- daily loss limit is reached;
- portfolio drawdown limit is reached;
- max simultaneous positions is reached.

The fail-safe blocks only new entries. Existing positions must remain
manageable through local runtime and hard-risk rules even when Supabase
is offline.

## Supabase Offline

Supabase outage is a warning while the local outbox remains inside age
and depth thresholds. Events continue to accumulate locally and can be
flushed after the remote backend recovers.

Escalate to no-new-entry when:

- oldest pending outbox event reaches the critical age threshold;
- pending count reaches the critical depth threshold;
- database errors combine with stale market data or strategy errors.

Recovery:

1. Confirm the local trading process is still running.
2. Confirm `.env` still contains `SUPABASE_URL` and the server-only
   Supabase secret key.
3. Test Supabase reachability from the host.
4. Flush the local outbox.
5. Verify pending depth and oldest age return below warning thresholds.

## Stale Market Data

Stale market data is critical. The bot must not open new positions when
the latest candle is older than the configured maximum age.

Recovery:

1. Check Bybit public API connectivity.
2. Confirm the pair and timeframe are supported.
3. Confirm host time is synchronized.
4. Restart only the market-data/trading process after preserving logs.
5. Keep new entries disabled until fresh candles are observed.

## Resource Pressure

The current VPS is intentionally treated as resource constrained. Disk,
RAM, swap and load warnings should be handled before they become
critical.

Recovery:

1. Stop optional jobs first, especially experiments and backtests.
2. Inspect logs and database files under `/opt/cryptoforge`.
3. Remove only reproducible artifacts such as downloaded candles or old
   logs covered by the log policy.
4. Do not delete pending outbox data or trade metadata.
5. Restart dry-run only after resources are back below warning levels.

## Risk-Limit Alerts

Risk-limit alerts are execution boundaries, not advice. When daily loss,
portfolio drawdown or position count limits are reached, strategies and
future ML components cannot override them.

Recovery:

1. Do not raise limits automatically.
2. Review the trade journal and performance metrics.
3. Confirm open positions remain protected by stop logic.
4. Require explicit human approval for any future limit change.

## Simulated Failure Coverage

Unit tests cover:

- healthy runtime allows new entries;
- stale market data blocks entries;
- Bybit outage blocks entries;
- Supabase outage is visible while local outbox preserves events;
- outbox growth warns and then blocks;
- disk/resource pressure warns and then blocks;
- risk limits block entries.
