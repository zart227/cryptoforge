from datetime import UTC,datetime,timedelta
from dataclasses import replace
import pytest
from cryptoforge.model_training import TrainingExample
from cryptoforge.net_tree import fit_net_tree

NOW=datetime(2026,10,9,tzinfo=UTC)


def data():
    return [TrainingExample('ETH/USDT',NOW-timedelta(days=2)+timedelta(minutes=i),(float(i),0.,0.,0.,0.,0.,0.),int(i>=20),0,
        -.01 if i<20 else .02,NOW-timedelta(days=1)) for i in range(40)]


def fit(rows=None):return fit_net_tree(rows or data(),target_version='spot-long-trade-net-v2',maximum_depth=2,minimum_leaf=8,as_of=NOW)


def test_small_tree_learns_conditional_magnitude_without_live_eligibility():
    model=fit();assert model.predict((5.,0,0,0,0,0,0))<0 and model.predict((35.,0,0,0,0,0,0))>0
    assert not model.live_eligible and model==fit()
    assert min(model.root['left']['count'],model.root['right']['count'])>=8


def test_future_labels_and_duplicate_samples_cannot_enter_tree():
    rows=data();rows[-1]=replace(rows[-1],label_end_time=NOW+timedelta(minutes=1))
    with pytest.raises(ValueError,match='unavailable'):fit(rows)
    with pytest.raises(ValueError,match='duplicate'):fit(data()+[data()[0]])


def test_constant_targets_are_not_split_and_predictions_stay_within_training_leaves():
    rows=[replace(row,label=0,future_return=-.01) for row in data()];model=fit(rows)
    assert 'feature' not in model.root and model.predict((1e10,0,0,0,0,0,0))==pytest.approx(-.01)


def test_spot_tree_rejects_short_price_target_migration():
    rows=data();rows[0]=replace(rows[0],short_label=1)
    with pytest.raises(ValueError,match='short-target'):fit(rows)
