# Strategy Lifecycle

Strategy promotion is evidence-backed and sequential:

```text
DRAFT
  -> BACKTESTED
  -> OUT_OF_SAMPLE_TESTED
  -> WALK_FORWARD_TESTED
  -> PAPER_TRADING
  -> CANDIDATE
  -> APPROVED
```

`APPROVED` does not enable real-money trading. Live trading still
requires the separate controlled-live phase and human approval.

## Evaluation Criteria

`EvaluationCriteria` checks:

- adequate trade count;
- profit factor;
- expectancy;
- Sharpe;
- Sortino;
- max drawdown;
- loss streak.

Absolute historical profit is not enough. A strategy with high profit but
unacceptable drawdown or instability is rejected.

## Evidence

Every evaluation produces an evidence payload containing metrics,
criteria and loss streak. This is suitable for storage in Supabase
experiment or strategy-version metadata.

## Hard Boundary

Strategy lifecycle code cannot modify hard risk limits, enable live
trading, enable withdrawals, or enable futures/margin/leverage. Promotion
recommendations remain separate from operator-controlled live configs.
