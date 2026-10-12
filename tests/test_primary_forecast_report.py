from datetime import timedelta
from decimal import Decimal as D
from cryptoforge.primary_forecast_report import primary_forecast_report
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.supabase_executor import CandleRow
from test_primary_forecast_memory import NOW,forecast


def test_report_uses_only_outcomes_available_as_of_and_is_not_portfolio_income(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    receipt=memory.record({**forecast(),'long_probability':.6,'input_drift':{'status':'training_reference_diagnostic_error'}})
    candle=CandleRow('ETH/USDT','ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))
    before=NOW+timedelta(minutes=10);after=before+timedelta(seconds=1);memory.clock=lambda:after
    memory.record_outcome(receipt['forecast_id'],candle)
    assert primary_forecast_report(memory,as_of=before)['observed_endpoints']==0
    report=primary_forecast_report(memory,as_of=after);group=report['by_model']['a'*64]
    assert group['brier']==(1-.6)**2 and group['fixed_threshold_signals']==1
    assert 'support:unknown' in group['signal_cohorts']
    assert 'support:within_train_range' not in group['signal_cohorts']
    assert group['mean_signal_price_return_minus_assumed_cost']=='0.01'
    assert not report['realized_income_established'] and report['cash_training_rows_added']==0
    assert group['baseline_signal_true_endpoints']==1 and group['baseline_fixed_threshold_signals']==1
    concentration=group['signal_concentration']
    assert concentration['signal_pairs']==concentration['signal_days']==1
    assert concentration['largest_pair_fraction']==concentration['largest_day_fraction']=='1'


def test_signal_cohorts_preserve_unknown_support_and_do_not_claim_profit(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    receipt=memory.record({**forecast(),'long_probability':.6})
    candle=CandleRow('ETH/USDT','ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))
    memory.clock=lambda:NOW+timedelta(minutes=10)
    memory.record_outcome(receipt['forecast_id'],candle)
    group=primary_forecast_report(memory,as_of=memory.clock())['by_model']['a'*64]
    cohorts=group['signal_cohorts']
    assert cohorts['pair:ETH/USDT']['signals']==1
    assert cohorts['support:unknown']['mean_price_return_minus_assumed_cost']=='0.01'
    assert not cohorts['support:unknown']['independent_profitability_established']


def test_baseline_opportunities_include_low_probability_losses_and_missed_winners(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    first=memory.record({**forecast(),'long_probability':.4})
    second=memory.record({**forecast(),'pair':'BTC/USDT','long_probability':.7})
    third=memory.record({**forecast(),'pair':'SOL/USDT','long_probability':.9,'baseline_entry_signal':False})
    memory.clock=lambda:NOW+timedelta(minutes=11)
    for receipt,pair,close in ((first,'ETH/USDT',D(101)),(second,'BTC/USDT',D(99)),(third,'SOL/USDT',D(101))):
        memory.record_outcome(receipt['forecast_id'],CandleRow(pair,pair.replace('/',''),NOW+timedelta(minutes=5),D(100),D(102),D(98),close,D(100)))
    group=primary_forecast_report(memory,as_of=memory.clock())['by_model']['a'*64]
    cohorts=group['baseline_opportunity_cohorts']
    assert cohorts['all_baseline_signals']['signals']==2
    assert D(cohorts['all_baseline_signals']['mean_price_return_minus_assumed_cost'])==0
    assert cohorts['probability_below_0.5']['mean_price_return_minus_assumed_cost']=='0.01'
    assert cohorts['probability_at_least_0.5']['mean_price_return_minus_assumed_cost']=='-0.01'
    assert group['fixed_threshold_signals']==2
    concentration=group['signal_concentration']
    assert concentration['by_pair']=={'BTC/USDT':1,'SOL/USDT':1}
    assert concentration['largest_pair_fraction']=='0.5'
    assert concentration['largest_day_fraction']=='1'
    assert not cohorts['all_baseline_signals']['independent_profitability_established']
