from copy import deepcopy
from datetime import timedelta

import pytest
from cryptoforge.walk_forward import folds
from cryptoforge.walk_forward_selection import fold_payload
from cryptoforge.walk_forward_cash_test import validate_cash_job, cash_test_status, evaluate_cash_reference
from test_walk_forward import START


def fixture():
    fold = folds(START, START+timedelta(days=365))[0]
    observed = fold.test_start+timedelta(hours=1)
    receipt = dict(schema_version='walk-forward-cash-selection-v1', policy='no_candidate_cash_only',
        fold=fold_payload(fold), observed_at=observed.isoformat(),
        live_promotion_allowed=False, independent_profitability_established=False)
    job = dict(schema_version='walk-forward-cash-reference-job-v1', scope='virtual_idle_cash_only',
        registered_at=(observed+timedelta(seconds=1)).isoformat(), selection_receipt=receipt,
        initial_cash='100', live_promotion_allowed=False)
    return fold, job


def test_actual_end_clock_required_even_for_idle_cash():
    fold, job = fixture()
    assert cash_test_status(job, fold.test_start+timedelta(hours=2)) == 'waiting_eligible_test_start'
    assert cash_test_status(job, fold.test_start+fold.embargo) == 'waiting_test_end'
    for stamp in (fold.test_start+fold.embargo, fold.test_end-timedelta(microseconds=1)):
        with pytest.raises(ValueError, match='has not ended'): evaluate_cash_reference(job, stamp)
    result = evaluate_cash_reference(job, fold.test_end)
    assert result['cash_component_completed'] and result['net_pnl'] == '0'
    assert not result['independent_procedure_evaluation_completed']
    assert not result['independent_profitability_established']
    assert result['native_control_status'] == 'not_evaluated'


@pytest.mark.parametrize('change', ['late_job', 'early_selection', 'future_job', 'live_receipt', 'wrong_policy', 'profit_claim'])
def test_unobserved_or_changed_selection_not_used(change):
    fold, job = fixture(); now = fold.test_end
    if change == 'late_job': job['registered_at'] = (fold.test_start+fold.embargo).isoformat()
    if change == 'early_selection': job['selection_receipt']['observed_at'] = (fold.test_start-timedelta(seconds=1)).isoformat()
    if change == 'future_job': now = fold.test_start
    if change == 'live_receipt': job['selection_receipt']['live_promotion_allowed'] = True
    if change == 'wrong_policy': job['selection_receipt']['policy'] = 'selected_model'
    if change == 'profit_claim': job['selection_receipt']['independent_profitability_established'] = True
    with pytest.raises(ValueError): validate_cash_job(job, now)


@pytest.mark.parametrize('capital', ['NaN', 'Infinity', '0', '-100'])
def test_virtual_cash_capital_must_be_finite_positive(capital):
    fold, job = fixture(); job['initial_cash'] = capital
    with pytest.raises(ValueError): evaluate_cash_reference(job, fold.test_end)
