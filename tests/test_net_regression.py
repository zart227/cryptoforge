from datetime import UTC,datetime,timedelta
from dataclasses import replace
import pytest
from cryptoforge.model_training import TrainingExample
from cryptoforge.net_regression import fit_net_regressor,evaluate_net_regressor

NOW=datetime(2026,10,9,tzinfo=UTC)


def examples():
    return [TrainingExample('ETH/USDT',NOW-timedelta(days=2)+timedelta(hours=index),tuple([x]+[0]*6),int(x>0),0,x*.02,NOW-timedelta(days=1)) for index,x in enumerate((-2.,-1.,1.,2.))]


def fit(rows=None,**kwargs):
    return fit_net_regressor(rows or examples(),target_version=kwargs.get('target_version','spot-long-trade-net-v2'),ridge=.01,as_of=NOW)


def test_regularized_net_head_learns_magnitude_and_keeps_no_live_eligibility():
    model=fit();assert model.predict((2.,0,0,0,0,0,0))>model.predict((1.,0,0,0,0,0,0))>0
    assert model.predict((-1.,0,0,0,0,0,0))<0 and not model.live_eligible
    metrics=evaluate_net_regressor(model,examples(),as_of=NOW,target_version='spot-long-trade-net-v2')
    assert metrics['mae']<.001 and not metrics['live_promotion_allowed']


def test_gross_future_labels_and_late_observations_cannot_be_used():
    with pytest.raises(ValueError,match='gross'):fit(target_version='fixed-future-return-v1')
    rows=examples();rows[0]=replace(rows[0],label_end_time=NOW+timedelta(seconds=1))
    with pytest.raises(ValueError,match='unavailable'):fit(rows)
    with pytest.raises(ValueError,match='unavailable'):evaluate_net_regressor(fit(),rows,as_of=NOW,target_version='spot-long-trade-net-v2')


def test_validation_does_not_refit_standardizer_and_mismatched_targets_fail():
    model=fit();means=model.means
    rows=[replace(row,features=(100.,0,0,0,0,0,0)) for row in examples()]
    evaluate_net_regressor(model,rows,as_of=NOW,target_version='spot-long-trade-net-v2');assert model.means==means
    rows=examples();rows[0]=replace(rows[0],label=1)
    with pytest.raises(ValueError,match='mismatch'):fit(rows)



def test_duplicate_buys_and_different_target_evaluation_are_rejected():
    rows=examples()
    with pytest.raises(ValueError,match='duplicate'):fit(rows+[rows[0]])
    with pytest.raises(ValueError,match='differs'):evaluate_net_regressor(fit(),rows,as_of=NOW,target_version='spot-long-real-cash-recovery-dust-zero-v1')


def test_evaluation_cannot_inflate_count_with_duplicates_or_reversed_label_time():
    model=fit();rows=examples()
    with pytest.raises(ValueError,match='duplicate'):
        evaluate_net_regressor(model,rows+[rows[0]],as_of=NOW,target_version='spot-long-trade-net-v2')
    rows[0]=replace(rows[0],open_time=NOW)
    with pytest.raises(ValueError,match='unordered'):
        evaluate_net_regressor(model,rows,as_of=NOW,target_version='spot-long-trade-net-v2')


def test_short_price_labels_cannot_be_reinterpreted_as_spot_net_samples():
    rows=examples();rows[0]=replace(rows[0],short_label=1)
    with pytest.raises(ValueError,match='short-target'):fit(rows)
    with pytest.raises(ValueError,match='short-target'):
        evaluate_net_regressor(fit(),rows,as_of=NOW,target_version='spot-long-trade-net-v2')


def test_weighted_fit_normalization_and_regularization_ignore_weight_scale():
    rows=examples()
    kwargs=dict(target_version='spot-long-trade-net-v2',ridge=.01,as_of=NOW)
    model=fit_net_regressor(rows,sample_weights=(1.,1.,2.,4.),**kwargs)
    scaled=fit_net_regressor(rows,sample_weights=(10.,10.,20.,40.),**kwargs)
    assert model == scaled
    assert model.means[0] == pytest.approx(.875)
    assert model.bias == pytest.approx(.0175)
    assert model.means != fit(rows).means
    before=model.means
    evaluate_net_regressor(model,rows,as_of=NOW,target_version=kwargs['target_version'])
    assert model.means == before


@pytest.mark.parametrize('weights', [(1.,), (1.,1.,0.,1.), (1.,1.,float('nan'),1.),
                                     (1.,1.,True,1.), (1e-320,1e300,1e300,1e300)])
def test_invalid_training_weights_fail(weights):
    with pytest.raises(ValueError,match='sample weights'):
        fit_net_regressor(examples(),target_version='spot-long-trade-net-v2',
                          ridge=.01,as_of=NOW,sample_weights=weights)
