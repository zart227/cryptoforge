from dataclasses import replace
from decimal import Decimal as D
import pytest
from cryptoforge.trade_simulator import SimulationConfig,simulate_portfolio
from cryptoforge.portfolio_diagnostics import portfolio_diagnostics
from test_trade_simulator import history


def test_duplicate_position_rejection_is_counted_without_becoming_negative_trade():
    rows=history(count=10);signals={'ETH/USDT':[rows[0].open_time,rows[1].open_time]}
    outcome=simulate_portfolio({'ETH/USDT':rows},signals,SimulationConfig(hold_bars=3))
    report=portfolio_diagnostics(outcome,signals)
    assert report['generated_signals']==2 and report['executed_trades']==1
    assert report['rejected_signals']==1 and report['negative_trades']==1
    assert report['rejection_reasons']=={'already_open':1}
    assert D(report['net_per_generated_signal'])==outcome.trades[0].net_pnl/2
    assert D(report['total_fees'])==outcome.trades[0].fees


def test_no_trade_sample_has_unknown_expectancy_and_does_not_look_profitable():
    rows=history(count=10);signals={'ETH/USDT':[]}
    report=portfolio_diagnostics(simulate_portfolio({'ETH/USDT':rows},signals),signals)
    assert report['no_trade_sample'] and report['net_per_executed_trade'] is None
    assert report['profit_factor'] is None and not report['independent_evidence']


def test_missing_signal_accounting_is_rejected():
    rows=history(count=10);outcome=simulate_portfolio({'ETH/USDT':rows},{})
    with pytest.raises(ValueError,match='incomplete'):portfolio_diagnostics(outcome,{'ETH/USDT':[rows[0].open_time]})


def test_day_and_pair_attribution_preserves_single_wallet_net_and_cash_baseline():
    rows=history(count=400);btc=[replace(c,pair='BTC/USDT',symbol='BTCUSDT') for c in rows]
    signals={'ETH/USDT':[rows[0].open_time,rows[20].open_time], 'BTC/USDT':[rows[300].open_time]}
    outcome=simulate_portfolio({'ETH/USDT':rows,'BTC/USDT':btc},signals,SimulationConfig(hold_bars=3))
    report=portfolio_diagnostics(outcome,signals)
    assert report['distinct_entry_days']==2 and report['distinct_traded_pairs']==2
    assert sum(D(v['net_pnl']) for v in report['by_pair'].values())==D(report['net_pnl'])
    assert sum(D(v['net_pnl']) for v in report['by_entry_day'].values())==D(report['net_pnl'])
    assert D(report['excess_net_over_cash_only'])<0 and report['cash_only_baseline']['net_pnl']=='0'
    best=sorted((trade.net_pnl for trade in outcome.trades),reverse=True)[:2]
    assert D(report['net_without_two_best_trades'])==D(report['net_pnl'])-sum(best,D(0))
