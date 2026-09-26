# Derivatives Research Policy

Updated: 2026-09-26.

The operator asked CryptoForge to check Futures/Margin/Leverage if they
appear profitable. CryptoForge may research derivatives only in paper,
shadow, or backtest mode.

`CryptoForgeLongShortResearchStrategy` exists for this research lane. It
can study short entries and exits, but it is not part of the first
real-money Spot live pilot.

## Allowed

- study derivatives market data;
- run bounded backtests;
- run paper/shadow experiments;
- compare results against Spot champion strategies;
- document expected liquidation risk, fees, funding and slippage;
- produce recommendations for human review.

## Forbidden Without A Separate Explicit Plan

- enable live Futures trading;
- enable live Margin trading;
- enable leverage;
- borrow funds;
- open short positions with real funds;
- deploy derivatives strategies automatically because a backtest looked
  profitable;
- allow ML/Strategy Lab to increase risk limits or market scope.

## Promotion Boundary

Even if a derivatives strategy performs well in research, it cannot be
applied to live trading automatically. A separate plan revision is
required with:

- exchange permissions audit;
- liquidation model;
- funding-rate model;
- max leverage cap;
- isolated/cross margin decision;
- kill switch tested against live derivatives config;
- explicit operator approval.

Current Phase 31 remains Spot-only.
