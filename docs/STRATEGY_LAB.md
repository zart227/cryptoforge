# Strategy Lab Skeleton

Strategy Lab is a lightweight research planner. It distinguishes:

- parameter optimization;
- machine learning;
- strategy discovery.

On the current 1 vCPU / 1 GB VPS, heavy search is **NOT ACTIVE**.
Strategy Lab prepares candidate recommendations for paper deployment; it
does not change live risk limits or deploy uncontrolled live strategies.

## Resource Gate

Before research runs, `StrategyLab.can_run()` checks:

- available RAM;
- 1-minute load average;
- free disk;
- whether trading runtime is active during trading hours;
- whether heavy search is marked active.

Research commands should use:

```text
nice -n 10 ionice -c2 -n7
```

## Day/Night Policy

Default trading hours are `08:00` to `22:00`. If trading runtime is
active during that window, research is deferred. Night research can run
only when resource checks pass.

## Experiment Metadata

Every experiment has:

- experiment ID;
- kind;
- objective;
- strategy version;
- dataset ID;
- parameters;
- reproducibility metadata;
- candidate-for-paper flag;
- live-risk-changes flag, always false in this phase.

Metadata is persisted through the durable outbox as
`experiment.planned`.

## Current Boundary

No massive parallel search. No thousands of concurrent backtests. No
large failed artifacts. No live risk changes. Candidate strategies move
through paper/shadow validation and lifecycle gates before any future
live consideration.
