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

Recorded first pilot capital allocation: `16 USDT`.

## Required Operator Attestation

`OperatorAttestation` must confirm:

- dedicated sub-account exists;
- withdrawal permission is absent;
- IP whitelist is configured where feasible;
- capital allocation is explicitly chosen;
- operator approval is explicit.

Without this attestation, `evaluate_live_pilot_readiness()` returns
blockers.

`cryptoforge.bybit_private` provides a read-only audit helper for Bybit
V5 private endpoints. It can check API key scope, UTA status, IP
whitelist count and Unified USDT balance without placing orders or
printing secrets.

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

`cryptoforge.live_config` can generate a separate live pilot config into
an operator-chosen, gitignored path. The generated config starts in
`initial_state=stopped`, uses environment references for Bybit keys, and
does not embed plaintext secrets.

Before live start, `scripts/select_live_universe.py` can scan Bybit Spot
USDT markets and update the live config whitelist with a bounded intraday
universe. It favors liquid pairs with back-and-forth movement using the
scanner `oscillation_score`, while still rejecting stablecoin-like,
leveraged/special, thin, wide-spread and pump-like markets.

The VPS live service unit is `cryptoforge-live-pilot.service`. It uses:

- config: `/opt/cryptoforge/config/freqtrade.live-pilot.json`;
- environment: `/opt/cryptoforge/app/.env`;
- userdir: `/opt/cryptoforge/app/user_data`;
- strategy: `CryptoForgeBaselineStrategy`;
- log file: `/opt/cryptoforge/logs/freqtrade-live-pilot.log`.

Deployment syncs repository strategies into the runtime userdir before
the service is started.

## Day Mode

Autonomous day mode may only run approved live strategies. It must:

- monitor strategy health;
- pause after abnormal loss, drift or errors;
- avoid editing live strategy code in place while positions are open;
- persist decisions and trade context;
- keep a user-visible daily summary.

`cryptoforge.daily_summary` renders a concise daily summary from metrics,
monitoring status, open position count and operator notes.

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

The final no-trade live smoke check on 2026-09-26 passed Bybit, config,
kill-switch, no-new-entry and backup gates from the VPS. Telegram
delivery from the VPS failed because `api.telegram.org:443` timed out
while other outbound HTTPS, including GitHub, still worked.

An `ntfy` fallback channel was then configured through the deployment
environment and the no-trade live smoke check passed the alert gate from
the VPS. Telegram remains a secondary channel until its route is fixed.
