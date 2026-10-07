from datetime import UTC, datetime, timedelta
from decimal import Decimal
from dataclasses import replace

from cryptoforge.supabase_executor import CandleRow
from cryptoforge.strategy_search import StrategySpec, backtest, search_strategies, signal


def candles(count=500):
    start = datetime(2026, 10, 1, tzinfo=UTC)
    return [CandleRow('ETH/USDT','ETHUSDT',start+timedelta(minutes=5*i),
                      Decimal(100+i),Decimal(102+i),Decimal(99+i),Decimal(101+i),
                      Decimal(1000)) for i in range(count)]


def test_nonoverlapping_next_open_fills_and_costs():
    rows = candles(100)
    spec = StrategySpec('trend',3,0.001)
    result = backtest(rows,spec,35,100,0)
    assert result['trades'] == 16
    assert backtest(rows,spec,35,100,0.003)['net_return'] < result['net_return']
    # Future changes cannot change an earlier signal.
    altered = rows[:40]+[replace(c,close=Decimal('1')) for c in rows[40:]]
    assert signal(rows,39,spec) == signal(altered,39,spec)


def test_search_reports_all_trials_and_never_enables_live():
    result = search_strategies(candles())
    assert len(result['trials']) == 18
    assert result['status'] == 'candidate_for_paper'
    assert result['live_eligible'] is False
    assert result['holdout']['trades'] >= 10
    assert len(result['holdout_segments']) == 2


def test_costs_and_missing_history_prevent_false_winners():
    rows = candles()
    assert search_strategies(rows,cost=0.2)['status'] == 'no_qualified_strategy'
    assert search_strategies(rows[:100])['status'] == 'insufficient_history'
    assert search_strategies(rows[:100]+rows[101:])['status'] == 'gapped_history'
