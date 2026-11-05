"""Provider metadata is nullable evidence, not a project budget grant or identity export."""
import json
from pathlib import Path

import pytest
from cryptoforge import research_provider_limits as m
from cryptoforge.training_diagnostics import canonical, digest

NOW = '2026-10-26T08:10:00+00:00'
SHA = 'a'*64


def test_all_unavailable_fields_remain_null_and_no_zero_spend_or_permission_is_invented():
    r = m.normalize({'data': {}}, NOW, response_sha256=SHA)
    assert all(v is None for v in r['credit_amounts'].values())
    assert r['budgets'] is r['effective_budget'] is r['free_model_daily_requests'] is None
    assert len(r['missing_native_fields']) == 16
    for name in ('all_account_keys_or_historical_requests_reconciled', 'this_bot_spend_separated_from_jobpilot',
                 'unknown_or_unlimited_value_assumed_zero', 'atomic_capacity_reservation',
                 'generation_fit_prediction_or_numerical_allowance_created', 'identity_or_credentials_exported',
                 'provider_limits_or_existing_journals_modified', 'deprecated_rate_limit_used_as_enforcement'):
        assert r[name] is False
    assert digest({k:v for k,v in r.items() if k != 'observation_sha256'}) == r['observation_sha256']


def test_native_zero_and_negative_remaining_are_preserved_without_identity_or_deprecated_quota():
    data = {'usage': 0, 'usage_daily': '0.00000125', 'limit': None, 'limit_remaining': '-0.01',
        'label': 'sk-or-v1-PRIVATE', 'creator_user_id': 'PRIVATE', 'organization_id': 'PRIVATE',
        'rate_limit': {'requests': 9999}, 'injected_instructions': 'PRIVATE',
        'is_free_tier': True, 'include_byok_in_limit': False,
        'free_model_daily_requests': {'used': 10, 'limit': 50, 'remaining': 40},
        'budgets': [{'scope': 'api_key', 'limit_usd': 50, 'spend_usd': 60, 'remaining_usd': -10,
            'budget_id': 'PRIVATE', 'guardrail_id': 'PRIVATE', 'reset_interval': 'monthly',
            'resets_at': '2026-11-01T00:00:00Z', 'include_byok': True}]}
    r = m.normalize({'data': data}, NOW, response_sha256=SHA)
    assert r['credit_amounts']['usage'] == '0' and r['credit_amounts']['limit'] is None
    assert r['credit_amounts']['limit_remaining'] == '-0.01'
    assert r['budgets'][0]['remaining_usd'] == '-10' and r['free_model_daily_requests']['remaining'] == 40
    assert 'PRIVATE' not in canonical(r) and 'requests' not in r


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), '1e1000000', '1e-1000000', 'x', '1'*65])
def test_credit_amount_type_precision_and_magnitude_caps_refuse_unbounded_formatting(value):
    with pytest.raises(ValueError): m.normalize({'data': {'usage': value}}, NOW, response_sha256=SHA)


@pytest.mark.parametrize('free', [[], {'used': True}, {'used': -1}, {'limit': 10000001}])
def test_unknown_free_counters_cannot_be_boolean_or_unbounded(free):
    with pytest.raises(ValueError): m.normalize({'data': {'free_model_daily_requests': free}}, NOW, response_sha256=SHA)


@pytest.mark.parametrize('data', [
    {'is_free_tier': 'yes'}, {'limit_reset': []}, {'limit_reset': 'hourly'}, {'budgets': {}}, {'budgets': [None]},
    {'budgets': [{}]*17}, {'effective_budget': {'scope': 'unrecognized'}},
    {'effective_budget': {'scope': []}}, {'effective_budget': {'scope': 'api_key', 'reset_interval': []}},
    {'effective_budget': {'scope': 'api_key', 'include_byok': 'yes'}},
])
def test_invalid_native_budget_shape_or_scope_refused_without_export(data):
    with pytest.raises(ValueError): m.normalize({'data': data}, NOW, response_sha256=SHA)


def test_policy_config_and_mutation_are_checked(monkeypatch):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-provider-limits-v1.json').read_text()) == m.POLICY
    monkeypatch.setitem(m.POLICY, 'native_limits_are_project_authorization', True)
    with pytest.raises(ValueError): m.normalize({'data': {}}, NOW, response_sha256=SHA)


@pytest.mark.parametrize('field', ['observed_at', 'reset'])
def test_invalid_native_timestamps_never_appear_in_error_messages(field):
    data = {} if field == 'observed_at' else {'effective_budget': {'scope': 'api_key', 'resets_at': 'PRIVATE_NATIVE_ID'}}
    with pytest.raises(ValueError) as caught:
        m.normalize({'data': data}, 'PRIVATE_NATIVE_ID' if field == 'observed_at' else NOW, response_sha256=SHA)
    assert 'PRIVATE_NATIVE_ID' not in str(caught.value)
