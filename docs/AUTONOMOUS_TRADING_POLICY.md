# Autonomous Trading Policy

Date: 2026-09-25

## User Objective

The intended future operating model is an autonomous trading and research
system:

- During the day, the bot trades approved strategies automatically.
- During the night, the bot researches, backtests, compares, and prepares
  candidate strategies.
- During the day, it monitors what worked, what failed, and whether a
  strategy should be paused, de-prioritized, or queued for retraining.
- The system should learn from results and improve its strategy selection
  over time.

## Safety Boundary

This objective does not mean immediate live trading. Current execution
remains dry-run until the plan reaches a dedicated controlled-live phase
and passes a pre-production audit.

The bot must not optimize for maximum short-term profit without risk
constraints. That objective is likely to select ruinous behavior such as
oversizing, leverage, martingale-like averaging, or chasing pumps.

The allowed objective is:

> Maximize risk-adjusted capital growth under explicit hard risk limits,
> liquidity constraints, operational safety limits, and human-approved
> live-trading boundaries.

## Non-Negotiable Guards

- No withdrawal permission is required or allowed.
- No futures, margin, leverage, or martingale unless a later plan revision
  explicitly adds them after a separate audit. Current scope remains Spot.
- Strategy Lab, ML, and optimizers cannot modify hard risk limits.
- Live strategies must pass paper-trading, out-of-sample, walk-forward,
  and risk checks before promotion.
- A high-return strategy with unacceptable drawdown, unstable behavior, or
  insufficient trade count must be rejected.
- The runtime must have a kill switch and no-new-entry fail-safe.
- Research must pause when it threatens trading runtime stability.
- New or edited strategies start in shadow/paper mode before live use.

## Day/Night Operating Model

Day mode:

- Run the approved live or dry-run strategy set.
- Monitor open positions, risk limits, market data freshness, outbox
  health, and system resources.
- Pause strategies that breach guardrails or drift from expected behavior.
- Record trade outcomes and feature snapshots for later analysis.

Night mode:

- Run bounded research jobs only when resources permit.
- Re-download reproducible market data as needed.
- Backtest candidate changes chronologically.
- Run out-of-sample and walk-forward validation.
- Compare candidates against champion strategy by risk-adjusted metrics.
- Prepare promotion recommendations, not direct uncontrolled live edits.

## Promotion Rule

Autonomous learning may recommend or queue changes. It may only promote a
strategy to live trading when all configured gates pass. Any change that
increases live risk budget, enables a new market type, enables leverage,
or changes real-money permissions requires explicit human approval.
