# Dynamic SL/TP And Position Management

Phase 11 adds a small independent protection planner. It defines risk
protection before an entry reaches the risk engine, and the resulting
stop distance feeds position sizing.

## Protection Plan

Default config lives in `config/position_protection.dry-run.json`:

- version: `sl-tp-v0.1.0`
- stop method: ATR-based
- stop distance: `2.0 * ATR`, clamped between `0.5%` and `4%`
- take profit: risk/reward target
- risk/reward: `1.5R`
- break-even trigger: `1.0R`
- trailing trigger: `2.0R`
- trailing distance: `1.0R`

The baseline remains intentionally simple. This module is the canonical
place for SL/TP planning rather than hiding hard protection logic inside
strategy code.

## Entry Flow

`PositionProtectionPlanner.evaluate_entry()`:

1. Computes `stop_loss` and `take_profit`.
2. Creates a `TradeRiskRequest` with that stop price.
3. Sends it to the independent `RiskEngine`.
4. Returns the protection plan and risk decision together.

No simulated trade should open without a valid `ProtectionPlan`.

## Gap And Fast-Move Behavior

The state machine is conservative within Freqtrade/backtest limits:

- if price is at or below stop, exit reason is `stop_loss`;
- if price is at or above take profit, exit reason is `take_profit`;
- break-even and trailing only raise the stop for Spot longs;
- stops are never lowered to avoid realizing a loss.

## Journal Context

`ProtectionPlan.journal_context()` returns the fields needed for the
trade journal and Supabase payload:

- protection version;
- stop method;
- take-profit method;
- entry price;
- stop loss;
- take profit;
- stop distance percentage;
- risk/reward.
