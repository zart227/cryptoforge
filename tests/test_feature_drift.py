from copy import deepcopy
import pytest
from cryptoforge.feature_drift import training_feature_reference,feature_drift


def reference():return training_feature_reference([(-1.,0.),(1.,0.)],names=['return','body'],means=[0.,0.],stds=[1.,1.])


def test_unseen_values_are_diagnostics_and_do_not_change_train_support_or_policy():
    support=reference();original=deepcopy(support)
    result=feature_drift((5.,.2),support)
    assert result['outside_train_range_features']==['return','body']
    assert result['maximum_absolute_train_standardized_value']==5
    assert support==original and not result['changes_entry_policy']
    assert feature_drift((1.,0.),support)['outside_train_range_count']==0


def test_wrong_dimensions_and_nonfinite_support_are_not_silently_used():
    with pytest.raises(ValueError,match='dimensions'):feature_drift((0.,),reference())
    support=reference();support['stds'][0]=0
    with pytest.raises(ValueError,match='finite'):feature_drift((0.,0.),support)
    with pytest.raises(ValueError):training_feature_reference([],names=['a'],means=[0.],stds=[1.])
