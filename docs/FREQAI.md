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
