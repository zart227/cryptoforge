# Champion / Challenger

The baseline strategy is registered as the initial champion/control
candidate:

- strategy: `CryptoForgeBaselineStrategy`
- version: `cryptoforge-baseline-v0.1.0`
- dataset: `bybit_spot_btcusdt_5m_20260923_20260925`
- live enabled: `false`

## Promotion Requirements

A challenger must be compared against the champion on equivalent data:

- same dataset identifier;
- same timerange;
- out-of-sample evidence;
- walk-forward evidence;
- regime-specific evidence;
- risk-adjusted improvement, not just absolute profit.

The decision payload records the champion metrics, challenger metrics,
out-of-sample metrics, walk-forward metrics and regime metrics.

## Rejection Rule

Absolute historical profit alone cannot replace the champion. A
challenger with higher profit but worse expectancy, worse profit factor,
excessive drawdown, missing OOS/walk-forward evidence or missing regime
evidence is rejected.

Every promotion or rejection carries a reason and evidence payload so
strategy history remains auditable.
