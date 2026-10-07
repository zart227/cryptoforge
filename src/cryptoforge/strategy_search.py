"""Bounded Spot strategy discovery. Research results never place orders."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from cryptoforge.supabase_executor import CandleRow
from cryptoforge.night_research import rsi


@dataclass(frozen=True)
class StrategySpec:
    family: str
    hold_candles: int
    sensitivity: float


def signal(candles: list[CandleRow], index: int, spec: StrategySpec) -> bool:
    """Use only closed candles up to index; fill at the following open."""
    window = candles[index-35:index+1]
    close = window[-1].close
    closes = [c.close for c in window]
    volume_mean = sum(c.volume for c in window[-20:]) / Decimal(20)
    if close <= 0 or volume_mean <= 0:
        return False
    liquid = window[-1].volume >= volume_mean * Decimal('0.5')
    if spec.family == 'reversion':
        return liquid and rsi(closes, 14) < Decimal(str(spec.sensitivity)) and closes[-1] > closes[-2]
    if spec.family == 'breakout':
        return (close > max(c.high for c in window[-21:-1]) and
                window[-1].volume >= volume_mean * Decimal(str(spec.sensitivity)))
    if spec.family == 'trend':
        fast = sum(closes[-8:]) / Decimal(8)
        slow = sum(closes[-24:]) / Decimal(24)
        return liquid and fast > slow and float((close-closes[-4])/closes[-4]) > spec.sensitivity
    raise ValueError(f'unknown strategy family: {spec.family}')


def backtest(candles: list[CandleRow], spec: StrategySpec, start: int, end: int,
             cost: float = 0.003) -> dict[str, Any]:
    """One position per pair; fixed holding time, next-open fills, no leverage."""
    if not 0 <= cost < 1:
        raise ValueError('cost must be in [0, 1)')
    equity = peak = 1.0
    drawdown = 0.0
    returns: list[float] = []
    index = max(35, start)
    while index + 1 + spec.hold_candles < min(end, len(candles)):
        if not signal(candles, index, spec):
            index += 1
            continue
        entry = candles[index+1].open
        exit_index = index+1+spec.hold_candles
        exit_price = candles[exit_index].open
        if entry <= 0 or exit_price <= 0:
            index += 1
            continue
        net = float(exit_price / entry) * (1-cost/2) / (1+cost/2) - 1
        returns.append(net)
        # Include interim close marks so holding-period losses are not hidden.
        before = equity
        for bar in candles[index+1:exit_index]:
            mark = before * float(bar.close / entry) * (1-cost/2) / (1+cost/2)
            peak = max(peak, mark)
            drawdown = max(drawdown, 1-mark/peak)
        equity = before * (1+net)
        peak = max(peak, equity)
        drawdown = max(drawdown, 1-equity/peak)
        index = exit_index
    return {'trades': len(returns), 'net_return': equity-1, 'max_drawdown': drawdown,
            'mean_trade_return': sum(returns)/max(len(returns), 1),
            'win_rate': sum(r > 0 for r in returns)/max(len(returns), 1)}


def search_strategies(candles: list[CandleRow], *, cost: float = 0.003,
                      min_trades: int = 10) -> dict[str, Any]:
    """Select one approach on the earlier segment; inspect its holdout once."""
    if len(candles) < 160:
        return {'status': 'insufficient_history', 'candles': len(candles)}
    if any(b.open_time <= a.open_time for a, b in zip(candles, candles[1:])):
        raise ValueError('candles must have unique increasing timestamps')
    spacing = candles[1].open_time - candles[0].open_time
    if any(b.open_time-a.open_time != spacing for a,b in zip(candles,candles[1:])):
        return {'status': 'gapped_history', 'candles': len(candles)}
    boundary = int(len(candles)*0.7)
    specs = [StrategySpec(family, hold, sensitivity)
             for family, sensitivities in [('reversion', (35.,45.)),
                                            ('breakout',(1.,1.5)),
                                            ('trend',(0.001,0.003))]
             for hold in (3,6,12) for sensitivity in sensitivities]
    trials = [{'strategy': asdict(spec), 'selection': backtest(candles,spec,35,boundary,cost)}
              for spec in specs]
    qualified = [t for t in trials if t['selection']['trades'] >= min_trades and
                 t['selection']['net_return'] > 0 and t['selection']['max_drawdown'] <= 0.05]
    result: dict[str, Any] = {'status': 'no_qualified_strategy', 'trials': trials,
                              'round_trip_cost':cost, 'holdout_start': candles[boundary].open_time.isoformat(),
                              'data_end':candles[-1].open_time.isoformat(), 'live_eligible':False}
    if not qualified:
        return result
    winner = max(qualified,key=lambda t:t['selection']['net_return']-t['selection']['max_drawdown'])
    spec = StrategySpec(**winner['strategy'])
    test = backtest(candles,spec,boundary,len(candles),cost)
    stress = backtest(candles,spec,boundary,len(candles),cost*2)
    midpoint = boundary+(len(candles)-boundary)//2
    segments = [backtest(candles,spec,start,end,cost) for start,end in
                [(boundary,midpoint),(midpoint,len(candles))]]
    passed = (test['trades'] >= min_trades and test['net_return'] > 0 and
              test['max_drawdown'] <= 0.05 and stress['net_return'] > 0 and
              all(s['trades'] >= 3 and s['net_return'] > 0 for s in segments))
    result.update(status='candidate_for_paper' if passed else 'failed_holdout',
                  winner=winner, holdout=test, stress_holdout=stress, holdout_segments=segments)
    return result
