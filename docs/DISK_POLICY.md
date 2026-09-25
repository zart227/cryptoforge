# Disk Policy, Log Rotation And Guard

CryptoForge treats disk pressure as a trading safety issue. When disk
usage rises, research must stop before filesystem exhaustion can affect
the trading runtime, local state, or pending outbox events.

## Data Classes

Critical data:

- configs;
- strategies;
- trade metadata;
- pending outbox;
- important model or experiment metadata;
- migration metadata.

Critical data must never be automatically deleted.

Reproducible data:

- downloaded candle history;
- market-history caches;
- generated backtest input data that can be downloaded again.

Temporary data:

- cache;
- debug logs;
- failed experiment artifacts;
- temporary backtests.

Only reproducible and temporary data may be removed by automated cleanup.

## Thresholds

Disk guard thresholds:

- `<70%`: normal;
- `70-80%`: warning;
- `80-90%`: stop research and clean only safe temporary/reproducible
  data;
- `>90%`: stop research and emit critical warning.

At `80%` and above, Strategy Lab and heavy research should not start.
At `90%` and above, the condition is critical even if cleanup succeeds.

## Log Rotation

Repository template:

```text
deploy/logrotate/cryptoforge
```

Policy:

- rotate daily or when a log reaches `25M`;
- keep 14 rotations;
- compress old logs;
- tolerate missing or empty logs;
- use `copytruncate` for long-running processes.

The template is not installed automatically by this phase. It should be
copied to `/etc/logrotate.d/cryptoforge` during a controlled deployment
step.

## Cleanup Rules

Automated cleanup must receive explicit `CleanupTarget` entries. Each
entry has a path and a data class.

Allowed:

- delete `DataClass.REPRODUCIBLE`;
- delete `DataClass.TEMPORARY`.

Forbidden:

- delete `DataClass.CRITICAL`;
- infer safe paths from broad globs such as `/opt/cryptoforge/*`;
- delete pending outbox files, trade databases, configs or strategies.

## Runtime Behavior

`classify_disk_usage()` converts usage percentage into a deterministic
decision:

- `normal`: research may run;
- `warning`: research may run but alerting should be visible;
- `cleanup`: research stops and safe cleanup may run;
- `critical`: research stops and a critical warning should be emitted.

`cleanup_safe_targets()` skips critical paths even when they are included
by mistake. Tests verify that synthetic critical files remain intact.
