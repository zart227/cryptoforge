import pytest
from cryptoforge.classifier_portfolio import ClassifierEntryScore


class Constant:
    def __init__(self,value):self.value=value
    def predict_probability(self,features):return self.value


def test_threshold_includes_equal_score_and_does_not_claim_calibration():
    assert ClassifierEntryScore(Constant(.5),.5).predict((0.,)*7)>0
    assert ClassifierEntryScore(Constant(.49),.5).predict((0.,)*7)<0
    assert not ClassifierEntryScore(Constant(.5),.5).live_eligible


@pytest.mark.parametrize('value',[float('nan'),-1,2])
def test_invalid_model_probabilities_are_not_entry_scores(value):
    with pytest.raises(ValueError):ClassifierEntryScore(Constant(value),.5).predict((0.,)*7)
