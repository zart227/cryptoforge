from math import log
from types import SimpleNamespace
import pytest
from cryptoforge.classifier_diagnostics import probability_diagnostics,split_diagnostics


def test_all_rejected_can_have_useful_probability_ranking_without_profit_claim():
    result=probability_diagnostics([0,1],[.01,.49],train_positive_rate=.2,threshold=.5)
    assert result['all_rejected'] and result['signals']==0
    assert result['log_loss'] < result['baseline_log_loss']
    assert result['baseline_log_loss']==pytest.approx((-log(.8)-log(.2))/2)
    assert not result['selection_uses_these_diagnostics'] and not result['live_profitability_established']
    assert result['average_precision']==1 and result['balanced_accuracy']==.5
    assert result['fixed_threshold_precision'] is None


def test_endpoint_probabilities_and_empty_sets_do_not_fabricate_measurements():
    result=probability_diagnostics([0,1],[0,1],train_positive_rate=0,threshold=.5)
    assert result['brier']==0 and result['signals']==1
    assert sum(b['count'] for b in result['calibration_bins'])==2
    result=probability_diagnostics([],[],train_positive_rate=.2,threshold=.5)
    assert result['log_loss'] is None and result['probability_max'] is None
    assert not result['all_rejected']


@pytest.mark.parametrize('labels,probabilities,baseline,threshold',[
    ([0],[.1,.2],.2,.5),([2],[.1],.2,.5),([0],[float('nan')],.2,.5),
    ([0],[1.1],.2,.5),([0],[.1],float('inf'),.5),([0],[.1],.2,-.1)])
def test_invalid_diagnostics_inputs_are_rejected(labels,probabilities,baseline,threshold):
    with pytest.raises(ValueError):
        probability_diagnostics(labels,probabilities,train_positive_rate=baseline,threshold=threshold)


def test_pairs_use_same_train_baseline_without_refitting_on_their_outcomes():
    examples=[SimpleNamespace(pair='BTC/USDT',label=0),SimpleNamespace(pair='ETH/USDT',label=1)]
    result=split_diagnostics(examples,[.1,.4],train_positive_rate=.25,threshold=.5)
    assert sum(v['count'] for v in result['by_pair'].values())==result['count']
    assert all(v['train_positive_rate']==.25 for v in result['by_pair'].values())


def test_precision_recall_ranking_groups_ties_and_is_order_invariant():
    original=probability_diagnostics([1,0,1,0],[.8,.8,.2,.2],train_positive_rate=.5,threshold=.5)
    reordered=probability_diagnostics([0,1,0,1],[.8,.8,.2,.2],train_positive_rate=.5,threshold=.5)
    assert original['average_precision']==reordered['average_precision']==.5
    assert original['balanced_accuracy']==.5
    assert original['fixed_threshold_precision']==original['fixed_threshold_recall']==.5


def test_no_positive_labels_have_no_defined_precision_recall_area():
    result=probability_diagnostics([0,0],[.1,.2],train_positive_rate=0,threshold=.5)
    assert result['average_precision'] is None and result['balanced_accuracy'] is None
    assert result['fixed_threshold_recall'] is None
