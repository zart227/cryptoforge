from dataclasses import replace
import pytest
from cryptoforge.net_ablation import fit_ablated_net_regressor,ablation_description
from cryptoforge.net_regression import evaluate_net_regressor
from test_net_regression import examples,NOW


def fit(removed):
    return fit_ablated_net_regressor(examples(),removed_indices=removed,target_version='spot-long-trade-net-v2',ridge=.01,as_of=NOW)


def test_removed_predictive_feature_is_masked_in_both_train_and_validation():
    model=fit([0]);report=evaluate_net_regressor(model,examples(),as_of=NOW,target_version=model.target_version)
    assert model.predict((100.,0,0,0,0,0,0))==model.predict((-100.,0,0,0,0,0,0))==0
    assert report['rmse']>.02 and not model.live_eligible
    assert not ablation_description(model)['feature_selection_performed']


def test_unremoved_feature_can_learn_and_validation_cannot_refit_normalizer():
    model=fit([1]);means=model.fitted.means
    assert model.predict((2.,0,0,0,0,0,0))>0
    evaluate_net_regressor(model,[replace(row,features=(100.,0,0,0,0,0,0)) for row in examples()],as_of=NOW,target_version=model.target_version)
    assert model.fitted.means==means


@pytest.mark.parametrize('removed',[[],[0,0],[7],[True],list(range(7))])
def test_invalid_ablation_specification_is_rejected(removed):
    with pytest.raises(ValueError,match='subset'):fit(removed)


def test_nonfinite_removed_feature_is_not_hidden_by_mask():
    model=fit([0])
    with pytest.raises(ValueError,match='finite original'):model.predict((float('nan'),0,0,0,0,0,0))


def test_ablation_preserves_explicit_recency_weights():
    model=fit_ablated_net_regressor(examples(),removed_indices=[0],
        target_version='spot-long-trade-net-v2',ridge=.01,as_of=NOW,
        sample_weights=(1.,1.,2.,4.))
    # Removing the only varying feature leaves the weighted train target mean.
    assert model.predict((999.,0,0,0,0,0,0)) == pytest.approx(.0175)
