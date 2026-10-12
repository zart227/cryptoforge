from datetime import UTC,datetime,timedelta
from dataclasses import replace
import pytest
from cryptoforge.context_regression import ContextExample,fit_context_regressor

NOW=datetime(2026,10,10,tzinfo=UTC)


def rows():
    return [ContextExample('ETH/USDT',NOW-timedelta(days=2)+timedelta(minutes=i),NOW-timedelta(days=2)+timedelta(minutes=i+5),NOW,
        tuple([x]+[0.]*23),x*.01,int(x>0)) for i,x in enumerate((-2.,-1.,1.,2.))]


def fit(data=None):return fit_context_regressor(data or rows(),target_version='spot-long-trade-net-v2',ridge=.01,as_of=NOW)


def test_context_model_requires24_features_and_remains_experimental():
    model=fit();assert len(model.weights)==24 and model.predict(tuple([2.]+[0.]*23))>0
    assert not model.live_eligible
    with pytest.raises(ValueError,match='dimensions'):model.predict((0.,)*7)


def test_future_availability_and_wrong_schema_cannot_enter_context_training():
    data=rows();data[0]=replace(data[0],label_available_at=NOW+timedelta(seconds=1))
    with pytest.raises(ValueError,match='unavailable'):fit(data)
    data=rows();data[0]=replace(data[0],feature_version='candle-v1')
    with pytest.raises(ValueError,match='schema'):fit(data)


@pytest.mark.parametrize('weights', [(0.,)*23, (0.,)*25, (float('nan'),)+(0.,)*23])
def test_corrupt_context_weights_cannot_produce_a_forecast(weights):
    with pytest.raises(ValueError):
        replace(fit(),weights=weights).predict((1.,)*24)


def test_context_evaluation_rejects_same_dimensions_from_another_schema():
    from cryptoforge.net_regression import evaluate_net_regressor
    data=rows();data[0]=replace(data[0],feature_version='different-24-feature-schema')
    with pytest.raises(ValueError,match='schema'):
        evaluate_net_regressor(fit(),data,as_of=NOW,target_version='spot-long-trade-net-v2')
    with pytest.raises(ValueError,match='schema'):
        replace(fit(),feature_version='candle-v1').predict((0.,)*24)


def test_context_training_rejects_features_observed_after_entry_before_exit():
    data=rows();data[0]=replace(data[0],feature_available_at=data[0].open_time+timedelta(minutes=6))
    with pytest.raises(ValueError,match='entry decision'):fit(data)
    from cryptoforge.net_regression import evaluate_net_regressor
    with pytest.raises(ValueError,match='entry decision'):
        evaluate_net_regressor(fit(),data,as_of=NOW,target_version='spot-long-trade-net-v2')
