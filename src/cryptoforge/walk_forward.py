"""Temporal fold construction and label-availability purge; no model selection."""
from dataclasses import dataclass
from datetime import datetime,timedelta


@dataclass(frozen=True)
class Fold:
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    embargo: timedelta


def folds(start,end,*,train_days=120,validation_days=30,test_days=30,step_days=30,
          embargo=timedelta(days=1),maximum_label_duration=timedelta(hours=4)):
    if start.tzinfo is None or end.tzinfo is None or start>=end:raise ValueError('ordered aware fold range required')
    if any(type(value) is not int or value<1 for value in (train_days,validation_days,test_days,step_days)):
        raise ValueError('positive integer calendar windows required')
    if step_days<test_days:raise ValueError('test windows must not overlap')
    if embargo<maximum_label_duration or maximum_label_duration<timedelta(0):raise ValueError('embargo must cover maximum label duration')
    if min(timedelta(days=validation_days),timedelta(days=test_days))<=embargo*2:
        raise ValueError('insufficient validation/test duration after embargo')
    result=[];anchor=start
    while True:
        train_end=anchor+timedelta(days=train_days);validation_end=train_end+timedelta(days=validation_days)
        test_end=validation_end+timedelta(days=test_days)
        if test_end>end:break
        result.append(Fold(anchor,train_end,train_end,validation_end,validation_end,test_end,embargo))
        anchor+=timedelta(days=step_days)
    return result


@dataclass(frozen=True)
class TemporalExample:
    identity: str
    decision_at: datetime
    feature_available_at: datetime
    label_available_at: datetime
    payload: object=None


def select_fold(examples,fold,*,as_of,include_test=False):
    """Test rewards are excluded unless explicitly requested after selection.

    Returned test examples are for a later evaluator, never model fitting. Data
    can reappear in later training folds once it is historically available;
    test intervals themselves remain nonoverlapping.
    """
    if as_of.tzinfo is None:raise ValueError('aware evaluation time required')
    if as_of<fold.test_start:raise ValueError('train/validation selection window is unfinished')
    if include_test and as_of<fold.test_end:raise ValueError('test outcomes remain sealed until window end')
    selected={'train':[],'validation':[]};excluded={};seen=set()
    if include_test:selected['test']=[]
    for row in examples:
        if row.identity in seen:raise ValueError('duplicate sample identity within snapshot')
        seen.add(row.identity)
        if any(stamp.tzinfo is None for stamp in (row.decision_at,row.feature_available_at,row.label_available_at)):
            raise ValueError('aware sample information times required')
        if not row.feature_available_at<=row.decision_at<=row.label_available_at:
            raise ValueError('feature/decision/label chronology invalid')
        split=None;cutoff=None
        if fold.train_start<=row.decision_at<fold.train_end:
            split='train';cutoff=fold.validation_start-fold.embargo
        elif fold.validation_start+fold.embargo<=row.decision_at<fold.validation_end:
            split='validation';cutoff=fold.test_start-fold.embargo
        elif include_test and fold.test_start+fold.embargo<=row.decision_at<fold.test_end:
            split='test';cutoff=fold.test_end-fold.embargo
        if split is None:reason='outside_requested_windows_or_embargo'
        elif row.label_available_at>=cutoff:reason='label_not_available_before_boundary'
        else:selected[split].append(row);continue
        excluded[reason]=excluded.get(reason,0)+1
    for values in selected.values():values.sort(key=lambda row:(row.decision_at,row.identity))
    return selected,excluded
