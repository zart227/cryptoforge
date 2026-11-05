"""Prospective v3 request format and identity; no transport or journals."""
from copy import deepcopy
import pytest
from test_llm_research_requests import report
from cryptoforge import llm_candidate_payload_v3 as m


def test_preview_uses_new_output_field_and_separate_identity_without_side_effects(monkeypatch):
    monkeypatch.setattr(m.candidate.subprocess,'Popen',lambda *a,**k:pytest.fail('no worker'))
    monkeypatch.setattr(m.advisor,'jobpilot_credentials',lambda *a,**k:pytest.fail('no credentials'))
    monkeypatch.setattr(m.requests.ResearchRequests,'_db',lambda *a,**k:pytest.fail('no journal'))
    value=m.preview(report());payload=value['payload']
    assert payload['model']==m.candidate.CANDIDATE_MODEL
    assert payload['max_completion_tokens']==2048 and 'max_tokens' not in payload
    assert payload['provider']['max_price']=={'prompt':0,'completion':0}
    assert payload['stream'] is False and payload['temperature']==0
    legacy=m.advisor.FreeAdvisor(model=m.candidate.CANDIDATE_MODEL,parameters=('l2','threshold')).preflight(report())
    assert payload['messages']==legacy['payload']['messages'] and legacy['payload']['max_tokens']==2048
    assert value['legacy_native_request_key']!=value['prospective_v3_request_identity']
    assert value['request_payload_sha256']==m.digest(payload)
    assert value['input_preflight']['request_payload_sha256']==value['request_payload_sha256']
    assert value['input_preflight']['request_payload_bytes']==value['request_payload_bytes']
    assert value['legacy_native_payload_sha256']==legacy['audit']['request_payload_sha256']
    assert value['prospective_v3_request_identity']==m.digest(value['prospective_identity_inputs'])
    assert not value['request_or_journal_admission_authorized'] and not value['transport_or_accounting_connected']
    assert not value['new_native_input_token_limit_verified']


def test_preview_is_deterministic_and_bound_to_diagnostics():
    first=m.preview(report());second=m.preview(report())
    assert first==second
    changed=deepcopy(report());changed['dataset_sha256']='f'*64
    changed_value=m.preview(changed)
    assert first['request_payload_sha256']!=changed_value['request_payload_sha256']
    assert first['legacy_native_request_key']!=changed_value['legacy_native_request_key']
    assert first['prospective_v3_request_identity']!=changed_value['prospective_v3_request_identity']


def test_prospective_identity_contains_native_inputs_and_wire_contract():
    value=m.preview(report());inputs=value['prospective_identity_inputs']
    assert value['legacy_native_request_key']==m.digest(inputs['legacy_native_inputs'])
    assert inputs['legacy_native_inputs']['model']==m.candidate.CANDIDATE_MODEL
    assert inputs['payload_sha256']==value['request_payload_sha256']
    assert inputs['policy_sha256']==m.digest(m.POLICY)
    assert inputs['implementation']==m.implementation()


def test_strict_admission_refuses_without_reading_key_or_journal(monkeypatch):
    monkeypatch.setattr(m.requests.ResearchRequests,'_db',lambda *a,**k:pytest.fail('no journal'))
    monkeypatch.setattr(m.advisor,'jobpilot_credentials',lambda *a,**k:pytest.fail('no credentials'))
    with pytest.raises(ValueError,match=m.prompt.UNVERIFIED_LIMIT):m.admit_new_completion(report())


def test_even_a_fake_verified_bound_does_not_enable_unimplemented_transport(monkeypatch):
    monkeypatch.setattr(m.prompt,'require_verified_limit',lambda required:None)
    with pytest.raises(ValueError,match='candidate_v3_transport_and_accounting_not_integrated'):
        m.admit_new_completion(report())


def test_non_validation_report_is_rejected():
    value=deepcopy(report());value['partition']='train'
    with pytest.raises(ValueError):m.preview(value)


def test_policy_mutation_fails_closed(monkeypatch):
    monkeypatch.setitem(m.POLICY,'model','openrouter/free')
    with pytest.raises(ValueError,match='fixed_candidate_payload_v3_required'):m.preview(report())
