# Long/Short Research

`CryptoForgeLongShortResearchStrategy` is research-only. It may be used
for paper, shadow and backtests, but it must not be wired into the first
real-money live pilot.

## Purpose

The strategy studies both directions:

- long entries from support bounces or resistance breakouts;
- short entries from resistance rejections or support breakdowns;
- long exits near resistance, support loss, trend loss, RSI exhaustion
  or excessive volatility;
- short exits near support, resistance recovery, trend recovery, RSI
  exhaustion or excessive volatility.

This lets CryptoForge learn from both rises and falls without enabling
real futures or margin trading.

## Promotion Rule

Real derivatives, margin or leverage remain blocked until a separate
live derivatives plan is approved. That plan must include:

- paper/shadow evidence over multiple market regimes;
- drawdown and liquidation-risk analysis;
- explicit maximum leverage and position caps;
- exchange permission review;
- a separate operator approval for live derivatives.
