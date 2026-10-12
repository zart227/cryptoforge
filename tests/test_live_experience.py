from copy import deepcopy
from datetime import datetime,UTC
from cryptoforge.live_experience import build_live_experiences


def data():
    common={'mode':'live','pair':'ETH/USDT','opened_at':'2026-10-07T05:00:00+00:00',
            'entry_reason':'FIFO order=buy1 origin=cryptoforge'}
    closed={**common,'idempotency_key':'bybit:spot:fifo:exec1:sell1','status':'closed',
            'closed_at':'2026-10-07T05:03:00+00:00','amount':'1','stake_amount':'5',
            'realized_pnl':'-.02','fee_amount':'.018','exit_reason':'FIFO order=sell1 origin=cryptoforge'}
    remainder={**common,'idempotency_key':'bybit:spot:fifo:exec1:remaining','status':'cancelled','amount':'0'}
    context={'pair':'ETH/USDT','decision':'approve_entry','features':{
        'order':{'result':{'orderId':'buy1'}},'feature_capture_status':'complete','feature_version':'candle-v1',
        'feature_observed_at':'2026-10-07T04:59:59+00:00','model_feature_values':[0,0,.01,1,0,.5,0]}}
    return [closed,remainder],[context]


def test_only_mature_original_feature_outcomes_are_training_labels():
    trades,contexts=data();seen=datetime(2026,10,7,6,tzinfo=UTC)
    result=build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)
    assert len(result['examples'])==1
    assert result['examples'][0]['example'].label==0
    assert result['examples'][0]['example'].label_end_time==seen
    trades[1]['status']='open';trades[1]['amount']='.001'
    assert build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)['examples']==[]


def test_late_features_or_manual_exit_cannot_be_training_targets():
    trades,contexts=data();seen=datetime(2026,10,7,6,tzinfo=UTC)
    contexts[0]['features']['feature_observed_at']='2026-10-07T05:00:01+00:00'
    result=build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)
    assert result['excluded'][0]['reason']=='features_not_observed_before_execution'
    trades,contexts=data();trades[0]['exit_reason']='FIFO order=sell1 origin=external'
    assert build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)['examples']==[]
    assert build_live_experiences(*data(),observed_at=seen,accounting_quality_verified=True,truncated=True)['examples']==[]


def test_accounting_verification_is_required_even_for_complete_examples():
    result=build_live_experiences(*data(),observed_at=datetime(2026,10,7,6,tzinfo=UTC))
    assert not result['examples']
    assert result['excluded'][0]['reason']=='unverified_accounting_snapshot'


def test_later_partial_close_does_not_retroactively_mature_prior_window():
    trades,contexts=data();later=deepcopy(trades[0])
    later.update(idempotency_key='bybit:spot:fifo:exec1:sell2',closed_at='2026-10-07T07:00:00+00:00')
    trades.append(later)
    result=build_live_experiences(trades,contexts,observed_at=datetime(2026,10,7,8,tzinfo=UTC),
        source_as_of=datetime(2026,10,7,6,tzinfo=UTC),accounting_quality_verified=True)
    assert not result['examples'] and result['excluded'][0]['reason']=='execution_not_mature_at_snapshot'


def test_label_is_available_when_observed_not_at_old_audit_cutoff():
    seen=datetime(2026,10,7,6,1,tzinfo=UTC)
    result=build_live_experiences(*data(),observed_at=seen,source_as_of=datetime(2026,10,7,6,tzinfo=UTC),
        accounting_quality_verified=True)
    assert result['examples'][0]['example'].label_end_time==seen


def test_training_rows_must_match_audited_closed_evidence_not_just_health():
    from cryptoforge.live_feedback import analyze_feedback
    from cryptoforge.live_experience import bind_examples_to_audit
    trades,contexts=data();seen=datetime(2026,10,7,6,tzinfo=UTC)
    contexts[0]['decided_at']='2026-10-07T05:00:00+00:00'
    audit=analyze_feedback([trades[0]],contexts,as_of=seen)
    result=build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)
    assert len(bind_examples_to_audit(result,audit)['examples'])==1
    trades[0]['realized_pnl']='.4'
    changed=build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)
    assert not bind_examples_to_audit(changed,audit)['examples']
    assert changed['excluded'][-1]['reason']=='execution_or_features_differ_from_verified_audit'


def test_expired_audit_history_is_not_reported_as_a_current_correction_mismatch():
    from cryptoforge.live_experience import bind_examples_to_audit
    trades,contexts=data();seen=datetime(2026,10,7,6,tzinfo=UTC)
    result=build_live_experiences(trades,contexts,observed_at=seen,accounting_quality_verified=True)
    audit={'as_of':'2026-11-01T06:00:00+00:00','source_lookback_days':14,'outcomes':[]}
    bound=bind_examples_to_audit(result,audit)
    assert not bound['examples'] and bound['source_binding_mismatches']==0
    assert bound['excluded'][-1]['reason']=='closing_history_outside_verified_audit_window'
