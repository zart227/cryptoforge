# Controlled Autonomous Live Trading Pilot

Phase 31 is a design/build phase for live gates. It does not enable real
trading by itself.

## Scope

The first live pilot, when explicitly approved later, is limited to:

- Bybit only;
- Spot only;
- dedicated limited sub-account only;
- no withdrawal permission;
- no futures;
- no margin;
- no leverage;
- no martingale or martingale-like recovery logic;
- IP-whitelisted API key where feasible;
- small capital allocation chosen explicitly by the operator.

## Required Operator Attestation

`OperatorAttestation` must confirm:

- dedicated sub-account exists;
- withdrawal permission is absent;
- IP whitelist is configured where feasible;
- capital allocation is explicitly chosen;
- operator approval is explicit.

Without this attestation, `evaluate_live_pilot_readiness()` returns
blockers.

## Kill Switch And No-New-Entry Switch

The live pilot requires both:

- kill switch;
- no-new-entry switch.

Switch files are explicit text files. Missing files are treated as
disabled. Valid enabled values are `1`, `true`, `enabled`, or `on`.

## Live Config Policy

Live execution must use a separate live config. Dry-run configs must not
be mutated.

The validator requires:

- `dry_run=false` only in the explicit live config;
- Bybit exchange;
- Spot trading mode;
- empty margin mode;
- no leverage settings;
- explicit bounded stake amount;
- max open trades at or below pilot policy;
- operator-supplied API key/secret at runtime.

Committed repository configs remain dry-run only.

## Day Mode

Autonomous day mode may only run approved live strategies. It must:

- monitor strategy health;
- pause after abnormal loss, drift or errors;
- avoid editing live strategy code in place while positions are open;
- persist decisions and trade context;
- keep a user-visible daily summary.

## Night Mode

Autonomous night mode remains research-only:

- stop or avoid heavy jobs if trading runtime is active and constrained;
- run bounded backtests/research;
- compare candidates against champion;
- produce recommendations;
- promote only through configured gates;
- deploy first to shadow/paper mode.

## Objective

The objective is risk-adjusted capital growth, not fastest possible
unbounded risk-taking.

The system must penalize:

- drawdown;
- instability;
- illiquidity;
- excessive turnover.

It must reject strategies that seek fast money by violating risk limits.

## Current Status

Live pilot readiness tooling exists. Real trading remains disabled until
the operator completes attestation, verifies backup/monitoring, confirms
resources, and explicitly approves a separate live config and command.

Telegram notification delivery was smoke-tested on 2026-09-25 using
local environment credentials. The test message was sent successfully and
no token or chat ID was printed.
