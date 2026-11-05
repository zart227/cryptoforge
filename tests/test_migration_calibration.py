from datetime import UTC,datetime,timedelta
import pytest
from cryptoforge.migration_calibration import evaluate_migration_rows

NOW=datetime(2026,10,13,tzinfo=UTC)


def row(identity,p,label):
    return identity,{'migration_protocol_sha256':'a'*64,'artifact_sha256':'b'*64,'pair':'ETH/USDT',
        'target_version':'fixed-future-return-v1','predicted_at':(NOW-timedelta(hours=1)).isoformat(),'long_probability':p},\
        {'label':label,'label_available_at':NOW.isoformat(),'forecast_id':identity,
         'target_information_end':(NOW-timedelta(minutes=1)).isoformat(),
         'source_kind':'primary_future_candle_return_diagnostic_v1','counts_as_real_executed_buys':False,
         'original_label_policy_available':label is not None}


def evaluate(rows):
    return evaluate_migration_rows(rows,protocol_sha='a'*64,artifact_sha='b'*64,train_positive_rate=.25,
        frozen_at=NOW-timedelta(days=1),as_of=NOW,pairs=['ETH/USDT'])


def test_frozen_prevalence_comparison_is_paired_not_current_label_rate():
    result=evaluate([row('1',.5,1),row('2',.5,0)])
    diagnostic=result['diagnostics']['all']
    assert diagnostic['brier']==.25 and diagnostic['baseline_brier']==.3125
    assert diagnostic['brier_difference_vs_frozen_prevalence']==-.0625
    assert not result['independent_admission_granted']


def test_wrong_identity_future_outcome_and_duplicate_endpoint_are_refused():
    first=row('1',.5,1)
    with pytest.raises(ValueError,match='unique'):evaluate([first,first])
    first[1]['artifact_sha256']='c'*64
    with pytest.raises(ValueError,match='identity'):evaluate([first])
    future=row('2',.5,0);future[2]['label_available_at']=(NOW+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='availability'):evaluate([future])


def test_unknown_labels_are_not_negative_training_examples():
    result=evaluate([row('1',.5,None)])
    assert result['unknown_policy_endpoints']==1 and not result['diagnostics']


@pytest.mark.parametrize('field,value',[('forecast_id','wrong'),('counts_as_real_executed_buys',True),
    ('source_kind','cash_trade'),('original_label_policy_available',False)])
def test_nonprice_or_unpaired_label_cannot_be_probability_evidence(field,value):
    first=row('1',.5,1);first[2][field]=value
    with pytest.raises(ValueError):evaluate([first])
