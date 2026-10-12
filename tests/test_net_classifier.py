from dataclasses import replace
from datetime import timedelta
import pytest
from cryptoforge.net_classifier import fit_net_classifier,evaluate_net_classifier
from test_net_regression import examples,NOW


def imbalanced():
    row=examples()[0]
    return [replace(row,open_time=row.open_time+timedelta(minutes=i),features=(0.,)*7,
        label=int(i<2),future_return=.01 if i<2 else -.01) for i in range(10)]


def fit(balance):return fit_net_classifier(imbalanced(),target_version='spot-long-trade-net-v2',as_of=NOW,class_balance=balance,epochs=2)


def test_weights_use_only_train_counts_and_weighted_scores_are_not_called_calibrated():
    balanced=fit(True);natural=fit(False)
    assert balanced.class_weights==(0.625,2.5)
    assert balanced.predict_probability((0.,)*7)==.5
    assert natural.predict_probability((0.,)*7)==pytest.approx(.2)
    report=evaluate_net_classifier(balanced,imbalanced(),as_of=NOW,target_version=balanced.target_version)
    assert report['observed_positive_rate']==.2 and report['count']==10
    assert report['evaluation_reuses_training_identities']==10
    assert not report['evaluation_is_after_fit_information_end']
    assert not report['independent_out_of_sample_established']
    assert report['brier']>report['baseline_brier']
    assert not report['probability_calibration_established'] and not report['live_promotion_allowed']


def test_validation_distribution_and_normalizer_are_not_rebalanced():
    model=fit(True);before=model.means
    rows=[replace(row,features=(100.,)*7) for row in imbalanced()]
    evaluate_net_classifier(model,rows,as_of=NOW,target_version=model.target_version)
    assert model.means==before


def test_invalid_labels_future_outcomes_and_gross_target_are_rejected():
    rows=imbalanced();rows[0]=replace(rows[0],label_end_time=NOW+timedelta(seconds=1))
    with pytest.raises(ValueError,match='unavailable'):fit_net_classifier(rows,target_version='spot-long-trade-net-v2',as_of=NOW)
    with pytest.raises(ValueError,match='gross'):fit_net_classifier(imbalanced(),target_version='fixed-future-return-v1',as_of=NOW)
    rows=imbalanced();rows[0]=replace(rows[0],label=0)
    with pytest.raises(ValueError,match='labels'):fit_net_classifier(rows,target_version='spot-long-trade-net-v2',as_of=NOW)


def test_duplicate_rows_cannot_inflate_class_support():
    rows=imbalanced()
    with pytest.raises(ValueError,match='duplicate'):fit_net_classifier(rows+rows[:1],target_version='spot-long-trade-net-v2',as_of=NOW)


def test_later_evaluation_is_explicitly_separate_from_train_identities():
    model=fit(True)
    later=[replace(row,open_time=NOW-timedelta(hours=3)+timedelta(minutes=i),label_end_time=NOW-timedelta(hours=1)) for i,row in enumerate(imbalanced())]
    report=evaluate_net_classifier(model,later,as_of=NOW,target_version=model.target_version)
    assert report['evaluation_is_after_fit_information_end']
    assert report['evaluation_reuses_training_identities']==0
    assert not report['independent_out_of_sample_established']


def test_price_short_label_is_rejected_by_net_profit_classifier():
    rows=imbalanced();rows[0]=replace(rows[0],short_label=1)
    with pytest.raises(ValueError,match='short-target'):
        fit_net_classifier(rows,target_version='spot-long-trade-net-v2',as_of=NOW)
