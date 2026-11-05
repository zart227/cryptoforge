"""Offline allowlisted interpretation of provider limit metadata; never grants calls or exports IDs."""
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path

from cryptoforge.training_diagnostics import canonical, digest, timestamp

POLICY = {'schema_version': 'research-provider-limits-policy-v1', 'provider': 'openrouter',
    'metadata_endpoint': 'https://openrouter.ai/api/v1/key', 'generation_endpoint_enabled': False,
    'maximum_budgets': 16, 'maximum_credit_decimal_places': 24, 'maximum_credit_magnitude': '1000000000000', 'maximum_free_request_counter': 10000000,
    'identity_label_key_and_response_body_exported': False, 'unknown_is_zero': False,
    'native_limits_are_project_authorization': False}
AMOUNTS = ('limit', 'limit_remaining', 'usage', 'usage_daily', 'usage_weekly', 'usage_monthly',
    'byok_usage', 'byok_usage_daily', 'byok_usage_weekly', 'byok_usage_monthly')
SCOPES = {'workspace_default_member', 'workspace_default_key', 'member', 'api_key', 'workspace', 'key_limit'}
INTERVALS = {None, 'daily', 'weekly', 'monthly'}


def implementation():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fixed_provider_limit_metadata_policy_required')


def amount(value, *, signed=False):
    if value is None: return None
    if type(value) not in (int, float, str, Decimal) or len(str(value)) > 64:
        raise ValueError('bounded_provider_credit_amount_required')
    try: number = Decimal(str(value))
    except InvalidOperation: raise ValueError('finite_provider_credit_amount_required') from None
    if not number.is_finite() or number.copy_abs() > Decimal(POLICY['maximum_credit_magnitude']) or (not signed and number < 0):
        raise ValueError('finite_bounded_provider_credit_amount_required')
    if number and number.as_tuple().exponent < -POLICY['maximum_credit_decimal_places']:
        raise ValueError('bounded_provider_credit_precision_required')
    return format(number, 'f') if number else '0'


def budget(value):
    if value is None: return None
    if type(value) is not dict or type(value.get('scope')) is not str or value.get('scope') not in SCOPES:
        raise ValueError('known_provider_budget_scope_and_reset_required')
    if value.get('reset_interval') is not None and (type(value['reset_interval']) is not str or value['reset_interval'] not in INTERVALS):
        raise ValueError('known_provider_budget_scope_and_reset_required')
    include = value.get('include_byok'); reset = value.get('resets_at')
    if include is not None and type(include) is not bool: raise ValueError('boolean_provider_byok_scope_required')
    if reset is not None:
        if type(reset) is not str or len(reset) > 64: raise ValueError('bounded_provider_reset_time_required')
        try: timestamp(reset)
        except (ValueError, TypeError, AttributeError):
            raise ValueError('valid_provider_reset_timestamp_required') from None
    return {'scope': value['scope'], 'limit_usd': amount(value.get('limit_usd')), 'spend_usd': amount(value.get('spend_usd')),
        'remaining_usd': amount(value.get('remaining_usd'), signed=True), 'reset_interval': value.get('reset_interval'),
        'resets_at': reset, 'include_byok': include}


def normalize(payload, observed_at, *, response_sha256):
    _guard()
    try: timestamp(observed_at)
    except (ValueError, TypeError, AttributeError):
        raise ValueError('valid_provider_observation_timestamp_required') from None
    if (type(payload) is not dict or type(payload.get('data')) is not dict or type(response_sha256) is not str
            or len(response_sha256) != 64 or any(c not in '0123456789abcdef' for c in response_sha256)):
        raise ValueError('fixed_provider_metadata_envelope_required')
    data = payload['data']; fields = {name: amount(data.get(name), signed=name == 'limit_remaining') for name in AMOUNTS}
    reset = data.get('limit_reset')
    if reset is not None and (type(reset) is not str or reset not in INTERVALS): raise ValueError('known_provider_limit_reset_required')
    flags = {}
    for name in ('is_free_tier', 'include_byok_in_limit'):
        value = data.get(name)
        if value is not None and type(value) is not bool: raise ValueError('boolean_provider_limit_flag_required')
        flags[name] = value
    counters = None; free = data.get('free_model_daily_requests')
    if free is not None:
        if type(free) is not dict: raise ValueError('provider_free_request_metadata_required')
        counters = {}
        for name in ('used', 'limit', 'remaining'):
            value = free.get(name)
            if value is not None and (type(value) is not int or not 0 <= value <= POLICY['maximum_free_request_counter']):
                raise ValueError('bounded_integer_free_request_counter_required')
            counters[name] = value
    budgets = data.get('budgets')
    if budgets is not None and (type(budgets) is not list or len(budgets) > POLICY['maximum_budgets']):
        raise ValueError('bounded_provider_budget_list_required')
    sanitized_budgets = None if budgets is None else [budget(item) for item in budgets]
    if sanitized_budgets is not None and any(item is None for item in sanitized_budgets):
        raise ValueError('provider_budget_records_cannot_be_null')
    expected = (*AMOUNTS, 'limit_reset', 'is_free_tier', 'include_byok_in_limit', 'free_model_daily_requests', 'budgets', 'effective_budget')
    core = {'schema_version': 'research-provider-limit-observation-v1', 'provider': 'openrouter',
        'implementation_sha256': _LOADED, 'policy_sha256': digest(POLICY), 'observed_at': observed_at,
        'response_sha256': response_sha256, 'credit_amounts': fields, 'limit_reset': reset, 'native_flags': flags,
        'free_model_daily_requests': counters, 'budgets': sanitized_budgets, 'effective_budget': budget(data.get('effective_budget')),
        'missing_native_fields': [name for name in expected if name not in data],
        'scope': 'credential_reported_spend_and_provider_free_limits_snapshot_shared_with_jobpilot',
        'all_account_keys_or_historical_requests_reconciled': False, 'this_bot_spend_separated_from_jobpilot': False,
        'unknown_or_unlimited_value_assumed_zero': False, 'atomic_capacity_reservation': False,
        'generation_fit_prediction_or_numerical_allowance_created': False, 'identity_or_credentials_exported': False,
        'provider_limits_or_existing_journals_modified': False, 'deprecated_rate_limit_used_as_enforcement': False}
    return {**core, 'observation_sha256': digest(core)}
