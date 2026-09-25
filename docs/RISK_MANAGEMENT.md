# Risk Management

The risk engine is independent from strategies, scanners, optimizers and
future ML components. Those components may request a trade; they do not
own hard limits.

## Dry-Run Defaults

The initial dry-run hard limits are stored in `config/risk.dry-run.json`:

- Virtual capital: `1000 USDT`.
- Risk per trade: at most `0.5%`.
- Max simultaneous positions: `2`.
- Daily loss limit: `2%`.
- Max portfolio drawdown: `10%`.
- Max position notional: `5%` of equity.
- Taker fee estimate: `0.1%` per side.
- Persistence fail-safe: stop new entries if the oldest pending outbox
  event is at least 1 hour old.

`HardRiskConfig` enforces these ceilings in code. A strategy cannot
increase them by passing a larger requested size.

## Position Sizing

For a Spot long request, the caller must provide:

- pair;
- entry price;
- stop price below entry;
- optional requested notional.

The engine calculates effective risk as:

```text
stop_distance_pct + estimated_round_trip_fee_pct
```

It sizes from the smaller of:

- risk budget divided by effective risk;
- max position notional;
- requested notional, if provided.

The result is rounded down to the configured quantity step and checked
against minimum order quantity and notional.

## No-New-Trade Guards

The engine returns `NO_NEW_TRADES` when any hard guard is active:

- maximum simultaneous positions reached;
- daily realized loss limit reached;
- portfolio drawdown limit reached;
- persistence outbox fail-safe exceeded.

These guards block new entries. They do not force-close existing
positions.

## Forbidden Behavior

The engine does not support martingale, doubling after loss, all-in
positioning, unlimited averaging down, stop removal, futures, margin or
leverage. Those require explicit future plan revisions and audits.
