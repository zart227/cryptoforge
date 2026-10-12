from decimal import Decimal as D
import pytest
from cryptoforge.paired_portfolio import compare_filtered_portfolios
from cryptoforge.trade_simulator import SimulationConfig
from test_trade_simulator import history
from cryptoforge.entry_risk import EntryRiskPlan

POLICY=dict(minimum_days=14,block_days=2,repetitions=100,seed=20261011)


def compare(data,baseline,filtered):
    return compare_filtered_portfolios(data,baseline,filtered,
        SimulationConfig(capital=D(100),stake=D(10),hold_bars=2),
        stress_multiplier=2,bootstrap_policy=POLICY)


def test_identical_filter_has_zero_incremental_value_under_both_cost_scenarios():
    rows=history();signals={'ETH/USDT':[rows[0].open_time]}
    result=compare({'ETH/USDT':rows},signals,signals)
    for difference in result['paired_differences'].values():
        assert D(difference['net_pnl_difference'])==0
        assert difference['block_interval']['status']=='insufficient_calendar_days'
    assert not result['live_promotion_allowed']


def test_no_trade_filter_avoids_fee_loss_but_does_not_establish_profitability():
    rows=history();result=compare({'ETH/USDT':rows},{'ETH/USDT':[rows[0].open_time]}, {})
    assert result['roles']['filtered']['no_trade_sample']
    assert D(result['paired_differences']['filtered_minus_baseline']['net_pnl_difference'])>0
    assert D(result['roles']['filtered']['net_pnl'])==0
    assert not result['independent_evidence']
    assert D(result['roles']['stress_baseline']['total_fees'])>D(result['roles']['baseline']['total_fees'])


def test_shared_wallet_capacity_is_applied_equally_to_both_arms():
    eth=history();btc=history('BTC/USDT');cfg=SimulationConfig(capital=D(10),stake=D(10),max_positions=1)
    signals={pair:[rows[0].open_time] for pair,rows in (('ETH/USDT',eth),('BTC/USDT',btc))}
    result=compare_filtered_portfolios({'ETH/USDT':eth,'BTC/USDT':btc},signals,signals,cfg,
        stress_multiplier=2,bootstrap_policy=POLICY)
    for role in result['roles'].values():
        assert role['executed_trades']==1
        assert role['rejected_signals']==1


def test_new_or_duplicate_signals_cannot_be_claimed_as_filter_improvement():
    rows=history();base={'ETH/USDT':[rows[0].open_time]}
    with pytest.raises(ValueError,match='subset'):
        compare({'ETH/USDT':rows},base,{'ETH/USDT':[rows[1].open_time]})
    with pytest.raises(ValueError,match='duplicate'):
        compare({'ETH/USDT':rows},base,{'ETH/USDT':[rows[0].open_time]*2})


def test_paired_full_day_bootstrap_is_deterministic_and_cash_still_earns_zero():
    rows=history(count=14*288)
    baseline={'ETH/USDT':[rows[index].open_time for index in range(0,len(rows),288)]}
    first=compare({'ETH/USDT':rows},baseline,{})
    second=compare({'ETH/USDT':rows},baseline,{})
    assert first==second
    delta=first['paired_differences']['filtered_minus_baseline']
    assert len(delta['daily_equity_difference_fraction_initial_capital'])==14
    assert delta['block_interval']['interval_lower']>0
    assert first['roles']['filtered']['net_pnl']=='0'
    assert not first['independent_evidence']


def test_ex_ante_risk_plans_are_identical_for_retained_baseline_signals():
    rows=history();stamp=rows[0].open_time
    plan=EntryRiskPlan('ETH/USDT',stamp,rows[1].open_time,D('.02'),D('.04'),2)
    signals={'ETH/USDT':[stamp]}
    kwargs=dict(stress_multiplier=2,bootstrap_policy=POLICY,entry_risks={('ETH/USDT',stamp):plan})
    report=compare_filtered_portfolios({'ETH/USDT':rows},signals,signals,SimulationConfig(),**kwargs)
    for role in report['roles'].values():
        assert role['entry_risk_policy']=='per_signal_ex_ante_plan'
        assert role['recorded_entry_risk_plans']==1
    assert D(report['paired_differences']['filtered_minus_baseline']['net_pnl_difference'])==0
    with pytest.raises(ValueError,match='coverage'):
        compare_filtered_portfolios({'ETH/USDT':rows},signals,signals,SimulationConfig(),
            stress_multiplier=2,bootstrap_policy=POLICY,entry_risks={})


def test_fixed_reference_model_uses_same_capital_costs_and_original_opportunities():
    rows=history();signals={'ETH/USDT':[rows[0].open_time]}
    report=compare_filtered_portfolios({'ETH/USDT':rows},signals,signals,SimulationConfig(),
        stress_multiplier=2,bootstrap_policy=POLICY,reference_signals=signals)
    for name in ('filtered_minus_reference','stress_filtered_minus_reference'):
        assert D(report['paired_differences'][name]['net_pnl_difference'])==0
    assert report['roles']['reference']==report['roles']['filtered']
    with pytest.raises(ValueError,match='reference filter'):
        compare_filtered_portfolios({'ETH/USDT':rows},signals,signals,SimulationConfig(),
            stress_multiplier=2,bootstrap_policy=POLICY,
            reference_signals={'ETH/USDT':[rows[1].open_time]})
