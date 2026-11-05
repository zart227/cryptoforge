from datetime import datetime,UTC,timedelta
from types import SimpleNamespace
from scripts.evaluate_walk_forward_head import portfolio_summary,validation_prices


def test_price_closing_at_purge_boundary_is_not_used():
    end=datetime(2026,10,15,tzinfo=UTC);start=end-timedelta(hours=1)
    rows=[SimpleNamespace(open_time=end-timedelta(minutes=minutes)) for minutes in (10,5,0)]
    result=validation_prices({'BTC/USDT':rows},start,end)
    assert result['BTC/USDT']==rows[:1]
    assert all(row.open_time+timedelta(minutes=5)<end for row in result['BTC/USDT'])


def test_validation_summary_preserves_stress_and_execution_counts():
    ordinary={'net_pnl':'1','drawdown_bound':'.01','executed_trades':20,
              'open_positions_at_end':0,'known_exit_minimum_violations':0}
    stress={**ordinary,'net_pnl':'-.1','open_positions_at_end':1,'known_exit_minimum_violations':2}
    summary=portfolio_summary({'initial_capital':'100','roles':{'filtered':ordinary,'stress_filtered':stress}})
    assert summary['net_pnl']=='1' and summary['stress_net_pnl']=='-.1'
    assert summary['stress_open_positions_at_end']==1 and summary['stress_exit_minimum_violations']==2
