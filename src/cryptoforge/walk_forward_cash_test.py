"""Clock-gated virtual cash reference; never a completed strategy comparison."""
from datetime import timedelta
from decimal import Decimal

from cryptoforge.live_learning_protocol import time
from cryptoforge.walk_forward_cash_selection import cash_selection_status


def validate_cash_job(job, observed):
    if (job.get('schema_version') != 'walk-forward-cash-reference-job-v1'
            or job.get('scope') != 'virtual_idle_cash_only'
            or job.get('live_promotion_allowed') is not False):
        raise ValueError('cash reference job required')
    receipt = job['selection_receipt']; fold = receipt['fold']
    selected = time(receipt['observed_at']); registered = time(job['registered_at'])
    eligible = time(fold['test_start']) + timedelta(seconds=fold['embargo'])
    if (receipt.get('schema_version') != 'walk-forward-cash-selection-v1'
            or receipt.get('policy') != 'no_candidate_cash_only'
            or receipt.get('live_promotion_allowed') is not False
            or receipt.get('independent_profitability_established') is not False
            or cash_selection_status(fold, selected) != 'ready_to_freeze'
            or not selected <= registered < eligible or registered > observed):
        raise ValueError('prospectively observed cash selection and job required')
    capital = Decimal(job['initial_cash'])
    if not capital.is_finite() or capital <= 0:
        raise ValueError('positive finite virtual capital required')
    return eligible, time(fold['test_end'])


def cash_test_status(job, observed):
    eligible, end = validate_cash_job(job, observed)
    return ('waiting_eligible_test_start' if observed < eligible else
        'waiting_test_end' if observed < end else 'ready_virtual_cash_reference')


def evaluate_cash_reference(job, observed):
    if cash_test_status(job, observed) != 'ready_virtual_cash_reference':
        raise ValueError('cash test window has not ended')
    return dict(schema_version='walk-forward-cash-reference-result-v1',
        observed_at=observed.isoformat(), scope='virtual_idle_cash_only',
        selection_observed_at=job['selection_receipt']['observed_at'],
        initial_cash=job['initial_cash'], final_cash=job['initial_cash'],
        trades=0, net_pnl='0', stress_net_pnl='0',
        idle_cash_assumptions='no orders, interest, transfers or account charges in virtual reference',
        cash_component_completed=True, native_control_status='not_evaluated',
        current_model_control_status='unknown_feature_contract',
        independent_procedure_evaluation_completed=False,
        independent_profitability_established=False, live_promotion_allowed=False)
