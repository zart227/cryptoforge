from datetime import UTC,datetime,timedelta
import pytest
from cryptoforge.walk_forward import folds,TemporalExample,select_fold

START=datetime(2025,10,1,tzinfo=UTC)


def sample(identity,day,known_day=None):
    decision=START+timedelta(days=day,hours=1)
    return TemporalExample(identity,decision,decision-timedelta(minutes=5),
        START+timedelta(days=known_day,hours=2) if known_day is not None else decision+timedelta(hours=1))


def test_year_produces_seven_nonoverlapping_windows_and_rejects_overlap():
    windows=folds(START,START+timedelta(days=365))
    assert len(windows)==7
    assert all(a.test_end<=b.test_start for a,b in zip(windows,windows[1:]))
    with pytest.raises(ValueError,match='overlap'):folds(START,START+timedelta(days=365),step_days=15)
    with pytest.raises(ValueError,match='cover'):folds(START,START+timedelta(days=365),embargo=timedelta(hours=1))


def test_late_labels_boundaries_and_embargo_are_purged():
    fold=folds(START,START+timedelta(days=365))[0]
    rows=[sample('train',2),sample('late-train',118,120),sample('embargo-validation',120),
          sample('validation',122),sample('late-validation',148,150),sample('test',152)]
    selected,excluded=select_fold(rows,fold,as_of=fold.test_start)
    assert [r.identity for r in selected['train']]==['train']
    assert [r.identity for r in selected['validation']]==['validation'] and 'test' not in selected
    assert excluded['label_not_available_before_boundary']==2
    with_test,_=select_fold(rows,fold,as_of=fold.test_end,include_test=True)
    assert [r.identity for r in with_test['test']]==['test']


def test_duplicate_groups_and_future_features_are_rejected():
    fold=folds(START,START+timedelta(days=365))[0];row=sample('buy',2)
    with pytest.raises(ValueError,match='duplicate'):select_fold([row,row],fold,as_of=fold.test_start)
    future=TemporalExample('future',row.decision_at,row.decision_at+timedelta(minutes=1),row.label_available_at)
    with pytest.raises(ValueError,match='chronology'):select_fold([future],fold,as_of=fold.test_start)



def test_future_test_labels_cannot_be_unsealed_by_a_flag_alone():
    fold=folds(START,START+timedelta(days=365))[0]
    with pytest.raises(ValueError,match='sealed'):select_fold([sample('test',152)],fold,as_of=fold.test_start,include_test=True)
    with pytest.raises(ValueError,match='unfinished'):select_fold([],fold,as_of=fold.test_start-timedelta(seconds=1))
