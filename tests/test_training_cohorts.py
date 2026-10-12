from dataclasses import replace
from datetime import timedelta, timezone
import pytest
from cryptoforge.training_cohorts import net_training_cohorts as diagnose
from test_net_regression import examples, NOW


def net_training_cohorts(rows, *, as_of):
    return diagnose(rows,as_of=as_of,target_version='spot-long-trade-net-v2')


def test_class_and_pair_support_reconcile_without_income_claim():
    rows=examples()
    rows[0]=replace(rows[0],pair='BTC/USDT')
    result=net_training_cohorts(rows,as_of=NOW)
    assert result['available_examples']==4
    assert result['positive']==result['negative']==2
    assert result['positive_fraction']==.5
    assert result['largest_pair_fraction']==.75
    assert sum(g['examples'] for g in result['by_utc_entry_day'].values())==4
    assert not result['live_promotion_allowed']


def test_unavailable_targets_are_not_inspected_or_counted():
    rows=examples()
    rows[0]=replace(rows[0],label_end_time=NOW+timedelta(seconds=1),future_return=float('nan'))
    rows[1]=replace(rows[1],label_end_time=None,features=(float('nan'),)*7)
    result=net_training_cohorts(rows,as_of=NOW)
    assert result['available_examples']==2
    assert result['excluded']=={'unknown_label_availability':1,'label_not_yet_available':1}


def test_duplicate_and_invalid_available_examples_fail():
    rows=examples()
    with pytest.raises(ValueError,match='duplicate'):
        net_training_cohorts(rows+[rows[0]],as_of=NOW)
    rows[0]=replace(rows[0],short_label=1)
    with pytest.raises(ValueError,match='Spot net'):
        net_training_cohorts(rows,as_of=NOW)


def test_utc_day_and_empty_support():
    row=replace(examples()[0],open_time=NOW.astimezone(timezone(timedelta(hours=3))),
                label_end_time=NOW,future_return=0,label=0)
    result=net_training_cohorts([row],as_of=NOW)
    assert result['by_utc_entry_day']=={NOW.date().isoformat():dict(examples=1,positive=0,negative=0,zero=1)}
    assert net_training_cohorts([],as_of=NOW)['positive_fraction'] is None


def test_gross_price_target_is_not_treated_as_net_trade_support():
    with pytest.raises(ValueError,match='explicit net target'):
        diagnose(examples(),as_of=NOW,target_version='fixed-future-return-v1')
