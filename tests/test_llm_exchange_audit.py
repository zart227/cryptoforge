"""Bounded full cleaned JSON, privacy before persistence and explicit schema-only validation."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import pytest
from test_llm_research_requests import report, Advisor
from cryptoforge import llm_exchange_audit as m

WHEN = '2026-10-26T12:30:00Z'
SECRET = 'synthetic-sensitive-key-123456789'


def response(*, provider='openrouter', change=None):
    proposal = Advisor().propose(report())['proposal']
    if provider == 'openrouter':
        body = {'id': 'synthetic-generation-id', 'model': m.advisor.DEFAULT_MODEL,
            'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': m.canonical(proposal)}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150, 'cost': 0}}
    else:
        body = {'model': 'fixture-local', 'message': {'role': 'assistant', 'content': m.canonical(proposal)},
            'done': True, 'done_reason': 'stop', 'prompt_eval_count': 100, 'eval_count': 50}
    if change: change(body)
    return json.dumps(body, separators=(',', ':')).encode()


def build(raw=None, **kwargs):
    return m.build(report(), raw if raw is not None else response(), observed_at=WHEN, **kwargs)


def test_full_cleaned_response_and_exact_factory_request_are_preserved():
    record = build()
    assert record['request'] == m.advisor.FreeAdvisor(parameters=('l2', 'threshold')).preflight(report())['payload']
    assert record['response']['full_cleaned_JSON_body_available']
    body = record['response']['cleaned_body']; assert body['id'] == '[REDACTED:identifier]'
    assert body['choices'][0]['message']['content'] == json.loads(response())['choices'][0]['message']['content']
    assert record['validation']['status'] == 'proposal_schema_valid_only'
    assert record['validation']['provider_reported_cost_usd'] == '0'
    assert record['validation']['usage']['total_tokens'] == 150
    assert not record['validation']['semantic_truth_or_usefulness_verified'] and not record['validation']['training_or_provider_action_authorized']
    assert not record['provenance']['provider_generation_performed_by_this_module']


def test_null_usage_and_cost_are_not_zero():
    record = build(response(change=lambda body:body.pop('usage')))
    assert record['validation']['status'] == 'proposal_schema_valid_only'
    assert record['validation']['provider_reported_cost_usd'] is None
    assert all(value is None for value in record['validation']['usage'].values())
    assert not record['validation']['usage_unavailable_means_zero']


def test_Ollama_native_usage_and_unknown_cost():
    record = build(response(provider='ollama'), provider='ollama', model='fixture-local')
    assert record['validation']['status'] == 'proposal_schema_valid_only'
    assert record['validation']['usage'] == {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
    assert record['validation']['provider_reported_cost_usd'] is None


@pytest.mark.parametrize('change', [
    lambda b:b.update(model='other/model:free'), lambda b:b['choices'][0].update(finish_reason='length'),
    lambda b:b['choices'][0]['message'].update(tool_calls=[{'function': {'name': 'shell'}}]),
    lambda b:b['choices'][0]['message'].update(refusal='declined'), lambda b:b['choices'][0]['message'].update(role='tool'),
    lambda b:b['usage'].update(prompt_tokens=True), lambda b:b['usage'].update(completion_tokens=-1),
    lambda b:b['usage'].update(total_tokens=151), lambda b:b['usage'].update(cost='0.000000000000000001'),
    lambda b:b['usage'].update(cost=True), lambda b:b['usage'].update(cost='1e99999'),
    lambda b:b['choices'][0]['message'].update(content='not JSON'), lambda b:b.update(choices=[]),
])
def test_invalid_identity_finish_tools_usage_cost_or_proposal_is_retained_as_rejection(change):
    raw = response(change=change); record = build(raw)
    assert record['validation']['status'] == 'rejected_response_contract'
    assert record['validation']['proposal'] is None and not record['validation']['training_or_provider_action_authorized']
    assert record['provenance']['original_response_body_sha256'] == hashlib.sha256(raw).hexdigest()
    assert record['response']['full_cleaned_JSON_body_available']


@pytest.mark.parametrize('text', [SECRET, ''.join('\\u%04x'%ord(c) for c in SECRET)])
def test_reflected_secret_in_nested_JSON_text_is_removed_before_disk_and_rejected(tmp_path, text):
    raw = response(change=lambda b:b['choices'][0]['message'].update(content='{"rationale":"'+text+'"}'))
    record = build(raw, known_secrets=(SECRET,))
    assert record['validation']['status'] == 'rejected_response_privacy'
    assert SECRET not in m.canonical(record)
    assert record['provenance']['response_redactions']['known_secret'] == 1
    m.save(tmp_path/'pack', record, known_secrets=(SECRET,))
    for path in (tmp_path/'pack').glob('*'): assert SECRET not in path.read_text()
    assert m.verify(tmp_path/'pack')['status'] == 'rejected_response_privacy'


@pytest.mark.parametrize('text', ['sk-or-v1-'+'a'*48, 'Bearer '+'b'*48, 'user@example.com', 'postgresql://name:password@localhost/db', 'OPENROUTER_API_KEY='+SECRET])
def test_credential_and_contact_patterns_are_sanitized_without_known_key_read(text):
    raw = response(change=lambda b:b.update(unexpected_message=text))
    record = build(raw)
    assert text not in m.canonical(record) and record['validation']['status'] == 'rejected_response_privacy'


def test_sensitive_fields_and_keys_are_removed_without_retaining_matched_values():
    raw = response(change=lambda b:b.update(headers={'Authorization': SECRET}, **{SECRET: 'value'}))
    record = build(raw, known_secrets=(SECRET,))
    assert SECRET not in m.canonical(record) and 'Authorization' not in m.canonical(record['response'])
    assert record['validation']['status'] == 'rejected_response_privacy'


@pytest.mark.parametrize('raw', [b'not-json '+SECRET.encode(), b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'\xff\x00'])
def test_invalid_outer_body_is_metadata_only_not_untrusted_raw_text(raw):
    record = build(raw)
    assert record['validation']['status'] == 'rejected_outer_response'
    assert record['response']['cleaned_body'] is None and not record['response']['full_cleaned_JSON_body_available']
    assert SECRET not in m.canonical(record)


def test_exact_provider_decimal_is_saved_as_string_without_binary_float_rounding():
    raw = response().replace(b'"cost":0', b'"cost":0.000000000000000000123456')
    record = build(raw)
    assert record['response']['cleaned_body']['usage']['cost'] == '1.23456E-19'
    assert record['validation']['status'] == 'rejected_response_contract'
    assert record['validation']['provider_reported_cost_usd'] == '1.23456E-19'


def test_usage_and_nonzero_cost_survive_rejection_instead_of_becoming_zero_or_unknown():
    record = build(response(change=lambda body:body['choices'][0]['message'].update(content='invalid proposal')))
    assert record['validation']['status'] == 'rejected_response_contract'
    assert record['validation']['usage']['total_tokens'] == 150 and record['validation']['provider_reported_cost_usd'] == '0'
    record = build(response(change=lambda body:body['usage'].update(cost='0.02')))
    assert record['validation']['status'] == 'rejected_response_contract'
    assert record['validation']['provider_reported_cost_usd'] == '0.02'
    assert record['validation']['usage_errors'] == ['nonzero_reported_cost_on_free_route']


def test_secret_reflected_in_identifier_is_also_a_privacy_rejection():
    record = build(response(change=lambda body:body.update(id=SECRET)), known_secrets=(SECRET,))
    assert record['validation']['status'] == 'rejected_response_privacy' and SECRET not in m.canonical(record)


@pytest.mark.parametrize('nested', ['{"password":"weak-example-value"}', '{"headers":{"Authorization":"weak-example-value"}}', '{"password":"weak-example-value",'])
def test_sensitive_fields_inside_embedded_or_malformed_JSON_text_are_redacted(nested):
    record = build(response(change=lambda body:body['choices'][0]['message'].update(content=nested)))
    assert 'weak-example-value' not in m.canonical(record)
    assert record['validation']['status'] == 'rejected_response_privacy'


def test_private_immutable_pack_tamper_and_symlink_refusal(tmp_path):
    record = build(); pack = tmp_path/'pack'; m.save(pack, record)
    assert m.verify(pack) == record['validation']; assert stat.S_IMODE(pack.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in pack.glob('*'))
    with pytest.raises(ValueError): m.save(pack, record)
    target = pack/'response.json'; raw = target.read_bytes(); target.write_bytes(raw+b' ')
    with pytest.raises(ValueError, match='file_changed'): m.verify(pack)
    target.unlink(); target.symlink_to(tmp_path/'outside')
    with pytest.raises((ValueError, OSError)): m.verify(pack)


def test_save_refuses_unsanitized_payload_or_missing_redaction_scope(tmp_path):
    record = build(); record['response']['cleaned_body']['injected'] = 'Bearer '+'a'*48
    with pytest.raises(ValueError, match='uncleaned'): m.save(tmp_path/'injected', record)
    record = build(known_secrets=(SECRET,))
    with pytest.raises(ValueError, match='same_ephemeral'): m.save(tmp_path/'no-scope', record)


def test_full_record_caps_and_scope_are_closed(tmp_path):
    with pytest.raises(ValueError): build(b' '*1000001)
    with pytest.raises(ValueError): build(known_secrets=('short',))
    with pytest.raises(ValueError): build(model='paid/model')
    with pytest.raises(ValueError): m.build(report(), response(), observed_at='secret')
    body = {}; child = body
    for _ in range(15): child['nested'] = {}; child = child['nested']
    assert build(json.dumps(body).encode())['response']['cleaned_body'] is None


def test_policy_and_offline_verification_never_start_worker_or_transport(tmp_path, monkeypatch, capsys):
    assert json.loads((Path(m.__file__).parents[2]/'config/llm-exchange-audit-v1.json').read_text()) == m.POLICY
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k:pytest.fail('worker forbidden'))
    monkeypatch.setattr(m.advisor, 'http_json', lambda *a, **k:pytest.fail('transport forbidden'))
    record = build(); m.save(tmp_path/'pack', record); assert m.verify(tmp_path/'pack')['status'] == 'proposal_schema_valid_only'
    assert m.main(['--directory', str(tmp_path/'private-name')]) == 2
    assert 'private-name' not in capsys.readouterr().out
