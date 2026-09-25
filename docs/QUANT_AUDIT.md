# Quant Audit

Audit date: 2026-09-25.

## Scope

Reviewed:

- `CryptoForgeBaselineStrategy`;
- baseline dry-run Freqtrade config;
- baseline backtest procedure;
- Phase 9 bounded VPS backtest result;
- future FreqAI validation design.

## Lookahead Bias, Leakage And Future Candles

Static checks found no obvious:

- negative `shift()`;
- centered rolling windows;
- direct `.iloc[-1]` full-dataframe usage.

Baseline indicators use current and past candles:

- EMA;
- RSI with historical diff/EMA;
- 20-candle rolling volume mean;
- ATR using `shift(1)` for previous close.

This is not a mathematical proof, but no blocking lookahead pattern is
currently known in the baseline strategy.

## Fills, Fees And Spread

Fees are included in the reproducible baseline backtest command with
`--fee 0.001`.

Backtest fill and spread realism remains a warning:

- order-book pricing is configured for dry-run runtime;
- historical fills still need paper/live dry-run evidence;
- slippage assumptions are not yet deeply modeled.

This warning blocks overconfident claims, not dry-run experimentation.

## Minimum Orders And Precision

Committed dry-run configs use:

- `stake_amount=10`;
- Bybit Spot;
- no leverage;
- no futures;
- no margin.

The independent risk engine separately enforces minimum notional,
minimum quantity and quantity step.

## Selection Bias

The baseline backtest used `BTC/USDT` only. This is acceptable for a
control strategy but does not prove broad market robustness.

Scanner and champion/challenger phases exist so later candidates are
compared across regimes and markets instead of selected only because one
pair looked good historically.

## Hyperparameter Overfitting

The baseline was not optimized to maximize historical profit. It is a
transparent control with fixed parameters.

Future optimization must remain bounded, chronological and
champion/challenger gated. Profit-only promotion remains forbidden.

## Trade Count

Blocking finding:

- Phase 9 baseline backtest produced 5 trades.
- This is insufficient to claim strategy validity.
- Minimum audit threshold is currently 30 trades before even considering
  a validity claim.

The current result can be used as a runtime/control check only.

## Chronological, Out-Of-Sample And Walk-Forward

Chronological validation requirements are documented in:

- `docs/FREQAI.md`;
- `docs/BACKTESTING.md`;
- `docs/STRATEGY_LIFECYCLE.md`;
- `docs/CHAMPION_CHALLENGER.md`.

Future claims require:

- chronological train/validation/test;
- out-of-sample separation;
- walk-forward testing;
- adequate trade count;
- regime-specific review;
- champion/challenger comparison.

## Conclusion

No current blocking quant flaw was found that prevents dry-run control
testing. A blocking quant flaw remains for any claim that the baseline is
a valid profitable strategy: insufficient trade count.

Do not present the baseline as production-valid. It is a transparent
control strategy for future comparison.
