"""Prospective calendar freeze, separate from selection and outcome qualification."""
from datetime import timedelta
from cryptoforge.walk_forward import folds
from cryptoforge.walk_forward_selection import fold_payload


def make_schedule(*,observed_at,first_test_start,minimum_windows=6):
    if observed_at.tzinfo is None or first_test_start.tzinfo is None:
        raise ValueError('aware schedule observation and first test required')
    if first_test_start.utcoffset()!=timedelta(0):
        raise ValueError('first test boundary must explicitly use UTC')
    if type(minimum_windows) is not int or minimum_windows<6:
        raise ValueError('at least six future test windows required')
    embargo=timedelta(days=1)
    if first_test_start-embargo<=observed_at:
        raise ValueError('first test purge boundary must follow all currently viewed data')
    if any((first_test_start.hour,first_test_start.minute,first_test_start.second,first_test_start.microsecond)):
        raise ValueError('whole UTC day test boundary required')
    start=first_test_start-timedelta(days=150);end=first_test_start+timedelta(days=30*minimum_windows)
    generated=folds(start,end,train_days=120,validation_days=30,test_days=30,step_days=30,
        embargo=embargo,maximum_label_duration=timedelta(hours=4))
    if len(generated)!=minimum_windows:raise ValueError('complete declared fold calendar required')
    return {'schema_version':'prospective-walk-forward-calendar-v1','observed_at':observed_at.isoformat(),
        'folds':[fold_payload(fold) for fold in generated],
        'reviewed_information_through':observed_at.isoformat(),
        'previously_viewed_policy':'all information viewed through observation is development',
        'purge_rule':'label_available_at strictly before next split boundary minus embargo',
        'selection_window_rule':'test_start <= observed_selection < test_start + embargo',
        'test_outcomes_rule':'do not read before test_end or use for same-fold selection',
        'calendar_frozen_only':True,'selection_procedure_preregistered':False,
        'selected_models':[],'independent_results_completed':False,'live_promotion_allowed':False}
