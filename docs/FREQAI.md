# Future FreqAI Architecture

FreqAI is **NOT ACTIVE** in the current runtime. CryptoForge does not spend
CPU/RAM pretending to train heavy ML on the current 1 vCPU / 1 GB VPS.
This document defines the upgrade path for a later resource-approved
phase.

## Candidate Model Families

Initial candidates:

- LightGBM
- XGBoost
- CatBoost

These are future options only. Continuous heavy training is **NOT
ACTIVE** until hardware, monitoring and validation gates explicitly allow
it.

## Feature Set

Candidate feature families:

- returns
- ATR
- RSI
- ADX
- EMA distances
- MACD
- Bollinger width
- VWAP distance
- volume and volume anomaly
- momentum
- realized volatility
- market regime
- time features

Every feature set receives a `feature_version`. Feature definitions must
be deterministic and calculated using only data available at prediction
time.

## Chronological Splits

ML experiments must use chronological splits:

```text
train -> validation -> test
```

No shuffled time-series splits. No feature normalization fitted on
future validation/test data. No target leakage from future candles,
future volume, future order outcomes or final trade labels.

## Walk-Forward Process

Walk-forward validation should use repeated windows:

```text
train[a:b] -> validate[b:c] -> test[c:d]
train[b:c] -> validate[c:d] -> test[d:e]
...
```

Each window stores:

- dataset ID;
- train/validation/test ranges;
- feature version;
- model version;
- parameters;
- metrics;
- artifact URI and checksum.

## Versioning

Model version format:

```text
{model_family}-{feature_version}-{yyyymmdd}-{short_hash}
```

Artifact metadata:

- model family;
- model version;
- feature version;
- train/validation/test ranges;
- parameter hash;
- artifact URI;
- SHA-256 checksum;
- metrics payload;
- creation time;
- producing Git commit.

Artifacts belong in object storage, not PostgreSQL BYTEA. PostgreSQL
stores metadata and checksums.

## Retraining Triggers

Retraining may be queued when:

- paper/live performance drifts below expected range;
- regime mix changes materially;
- data freshness or liquidity profile changes;
- model age exceeds configured window;
- champion/challenger review requests a new candidate.

Initial retraining window: night-only, and only when Strategy Lab
resource gates pass.

## Anti-Leakage Checks

Required checks:

- chronological train/validation/test split;
- no negative shifts;
- no centered rolling windows;
- no `.iloc[-1]` full-dataframe leakage in strategy code;
- feature scalers fitted only on training data;
- labels aligned strictly after feature timestamps;
- walk-forward windows do not overlap improperly;
- final test data not used for parameter selection.

## Champion / Challenger ML Evaluation

ML candidates must beat the champion on:

- out-of-sample metrics;
- walk-forward metrics;
- regime-specific metrics;
- drawdown;
- profit factor;
- expectancy;
- Sharpe/Sortino;
- adequate trade count and stability.

Absolute historical profit is insufficient.

## Shadow Mode Before Deployment

Every ML strategy first runs in shadow or paper mode. It records
predictions, features, confidence and suggested actions without live
execution. Promotion can only proceed through lifecycle gates and human
live approval boundaries.

The Supabase-backed executor supports three explicit modes:

- `off`: do not load the active model;
- `shadow` (default): load the latest `model.active` event, verify the embedded
  artifact checksum and freshness, and record probability without changing the
  conventional strategy decision;
- `gate`: after the conventional entry signal passes, reject entry when the
  fresh compatible model probability is below the configured threshold.

Missing, stale, corrupt, unreachable or feature-incompatible models fall back
to the conventional strategy and risk checks. They never disable exit handling.
The deployed systemd executor remains in `shadow` with threshold `0.55` until
model quality and paper observations justify a separately reviewed promotion.

## Drift And Deactivation

Automatic deactivation criteria:

- daily loss or drawdown guard breach;
- prediction distribution drift;
- feature distribution drift;
- actual performance diverges from paper expectation;
- stale data or missing features;
- outbox/monitoring failure beyond fail-safe threshold.

Deactivation means no new entries. Existing positions remain managed by
runtime/risk rules.

## Exposure Boundary

ML cannot autonomously increase live exposure, edit hard risk limits,
enable leverage, enable futures/margin, enable withdrawals, or deploy
itself to live trading. Any such change requires a separate audited plan
revision and explicit human approval.

## Lightweight model promotion

Training saves every run, but emits `model.active` only after a quality screen;
rejected runs emit `model.candidate` and leave the registry unchanged. Split
boundaries group equal timestamps and purge labels extending into the next split.
The common comparison set must be later than both models' training labels
(legacy artifacts conservatively use their training timestamp). At least 200
unseen examples and 30 candidate signals are required. The candidate must beat
majority-class accuracy, have positive mean signal return after round-trip costs,
and achieve strictly better net return per example without worse accuracy than
the incumbent. Registry errors abort publication rather than bypassing the screen.

`--round-trip-cost` defaults to 0.003 (0.2% round-trip fees plus 0.1% slippage).
`--min-label-return` defaults to the same value, so long and short heads are
trained only on moves large enough to clear the assumed round-trip cost. Smaller
future moves remain negative examples for both directions instead of teaching the
model to chase noise.
This is an assumed signal-level screen, not a portfolio backtest: signals can
overlap and actual fees, fills, exits, and capital constraints differ. Promotion
is not evidence of statistically significant or realized profitability. No
existing model is automatically rolled back or trading configuration changed.

## Bounded strategy discovery and regularization

The hourly night-research runner now stores `strategy_experiments` in its existing
report event. It searches 18 Spot-only variants: reversion (RSI 35/45 with a
bounce), breakout (volume multiplier 1/1.5), and trend (3-bar return 0.1%/0.3%),
each with 3/6/12-bar holding periods. These experiments do not change live pair
selection, executor strategies, stakes, or risk limits.

Each pair uses the first 70% of candles for selection; only that winner is checked
on the last 30%. Entry and exit use subsequent candle opens, with one position
per pair and no overlapping positions. Costs default to 0.3% round-trip; the
holdout must also remain positive at double costs and in both halves, have at
least 10 trades, and drawdown <=5%. Passing means candidate for paper research,
never permission for live trading. Reports retain all selection trials and the
winner's holdout metrics. Gap-containing histories are rejected. OHLC simulation
cannot account for order book depth, exact fills, and intrabar drawdown; current
short histories and repeatedly reused holdouts need longer forward paper
validation before any deployment decision.

The long logistic head now searches L2 values 0/0.01/0.1 using validation log loss.
The chosen weights, L2, and search metrics are saved in the artifact. Test data
never selects the regularization. Changing the target-return threshold does not
relax exclusion of data seen by the incumbent.
