from datetime import datetime,UTC,timedelta
from cryptoforge.entry_gate_diagnostics import analyze_entry_decisions,current_gate_diagnostic
NOW=datetime(2026,10,10,tzinfo=UTC)


def test_entry_gate_observations_are_bounded_and_do_not_guarantee_collection():
    def row(minutes):return {'decided_at':(NOW+timedelta(minutes=minutes)).isoformat(),'decision':'reject_entry','reasons':['ml_fallback=no_fresh_model']*2}
    report=analyze_entry_decisions([row(-1),row(-16),row(1)],as_of=NOW)
    assert report['included_rows']==1 and report['no_fresh_model_rejections']==1
    assert report['status']=='observed_no_fresh_model_rejections'
    assert not report['changes_readiness_gates'] and not report['sample_growth_guaranteed']


def test_old_or_future_diagnostics_do_not_describe_current_gate():
    report=analyze_entry_decisions([],as_of=NOW)
    assert current_gate_diagnostic(report,now=NOW)['status']==report['status']
    assert current_gate_diagnostic(report,now=NOW+timedelta(minutes=6))['status']=='recent_decision_diagnostic_stale_or_future'
    assert current_gate_diagnostic(report,now=NOW-timedelta(seconds=1))['status']=='recent_decision_diagnostic_stale_or_future'
    assert current_gate_diagnostic({},now=NOW)['status']=='recent_decision_diagnostic_unavailable'


def test_truncated_window_is_not_reported_as_complete():
    assert analyze_entry_decisions([],as_of=NOW,truncated=True)['status']=='partial_decision_window'


def test_pair_counts_and_constraint_categories_ignore_numeric_context():
    rows=[{'pair':'ETH/USDT','decided_at':NOW.isoformat(),'decision':'reject_entry',
        'reasons':['ml_fallback=no_fresh_model']*2+['rsi=50.34','trend=True']},
        {'pair':'BTC/USDT','decided_at':NOW.isoformat(),'decision':'hold',
         'reasons':['trend=False','rsi=49.31']},
        {'pair':'ETH/USDT','decided_at':NOW.isoformat(),'decision':'reject_entry',
         'reasons':['dust risk too high: step_value=0.034 > allowed=0.01']},
        {'pair':'ETH/USDT','decided_at':NOW.isoformat(),'decision':'reject_entry','reasons':['unknown restriction']}]
    result=analyze_entry_decisions(rows,as_of=NOW)
    assert result['entry_constraints']=={'model_fallback':1,'dust_budget':1}
    assert result['by_pair']['ETH/USDT']['decisions']=={'reject_entry':3}
    assert result['observed_signal_flags']=={'trend=True':1,'trend=False':1}
    assert result['unclassified_rejections']==1
    assert result['signal_flags_are_observations_not_individual_causal_blockers']
