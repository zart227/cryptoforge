from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading

import pytest

from test_llm_research_requests import Advisor, report
from test_llm_training_advisor import export, proposal, catalog
from cryptoforge import llm_prompt_preflight as preflight
from cryptoforge import llm_provider_worker as worker
from cryptoforge import llm_research_coordinator as coordinator
from cryptoforge.llm_research_advisor import FreeAdvisor, SYSTEM, PROMPT_VERSION, DEFAULT_MODEL
from cryptoforge.llm_research_contracts import CATALOG, PROPOSAL_VERSION
from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.research_run_budget import BudgetCancelled
from cryptoforge.training_diagnostics import canonical, digest, validate_diagnostics


def large_report():
    value = report(); metrics = value['evidence']['overall']
    value['evidence'].update({f'pair:ASSET{i}/USDT': deepcopy(metrics) for i in range(200)})
    return validate_diagnostics(value)


def research(tmp_path):
    return coordinator.ResearchCoordinator(tmp_path/'common.sqlite', proposal_ledger=tmp_path/'api.sqlite',
        semantic_ledger=tmp_path/'semantic.sqlite', fit_ledger=tmp_path/'fit.sqlite')


def completed(advisor, value):
    result = Advisor().propose(value)
    return {**result, 'provider': advisor.provider, 'model': advisor.model, 'requested_model': advisor.model}


@pytest.mark.parametrize('provider', ['openrouter', 'ollama'])
def test_preflight_counts_exact_wire_bytes_and_preserves_old_messages(provider):
    advisor = FreeAdvisor(provider=provider, parameters=('l2', 'threshold'))
    value = report(); prepared = advisor.preflight(value)
    expected = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': canonical({
        'diagnostics': value, 'catalog': {p: CATALOG[p] for p in advisor.parameters}, 'schema_version': PROPOSAL_VERSION})}]
    assert prepared['messages'] == expected
    assert prepared['audit']['messages_sha256'] == digest(expected)
    assert prepared['audit']['message_bytes'] == len(canonical(expected).encode())
    assert prepared['audit']['request_payload_bytes'] == len(canonical(prepared['payload']).encode())
    assert prepared['audit']['request_payload_sha256'] == digest(prepared['payload'])
    assert prepared['audit']['input_tokens_upper_bound'] is None
    assert not prepared['audit']['hard_input_token_limit_verified']
    assert not prepared['audit']['byte_limit_is_token_limit']
    assert prepared['audit']['maximum_message_bytes'] == 24000
    assert prepared['audit']['maximum_request_bytes'] == 32000


def test_no_evidence_is_truncated_or_selected_to_fit_the_request():
    value = large_report(); before = canonical(value)
    with pytest.raises(ValueError, match='no truncation'): FreeAdvisor().preflight(value)
    assert canonical(value) == before


def test_large_prompt_is_rejected_before_transport_worker_or_both_journals(tmp_path, monkeypatch):
    called = []; value = large_report()
    with pytest.raises(ValueError, match='byte limit'):
        FreeAdvisor(api_key='synthetic-key', transport=lambda *a, **k: called.append(1)).propose(value)
    with pytest.raises(ValueError, match='byte limit'):
        ResearchRequests(tmp_path/'api.sqlite').propose(FreeAdvisor(), value)
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(ValueError, match='byte limit'):
        worker.run_provider_worker(FreeAdvisor(), value, wall_seconds=1, jobpilot_env=tmp_path/'missing')
    with pytest.raises(ValueError, match='byte limit'):
        research(tmp_path).propose(value, provider='openrouter', jobpilot_env=tmp_path/'missing')
    assert called == [] and not list(tmp_path.glob('*.sqlite'))


def test_large_fractional_timestamp_is_not_a_hidden_unbounded_input():
    value = report(); value['development_end'] = '2026-01-02T00:00:00.'+'1'*25000+'Z'
    validate_diagnostics(value)
    with pytest.raises(ValueError, match='byte limit'): FreeAdvisor().preflight(value)


def test_extra_fields_cannot_supply_token_proof():
    value = report(); value['hard_input_token_limit_verified'] = True
    with pytest.raises(ValueError): FreeAdvisor().preflight(value)


@pytest.mark.parametrize('provider', ['openrouter', 'ollama'])
def test_strict_uncached_provider_refusal_precedes_admission_and_credentials(tmp_path, provider, monkeypatch):
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(ValueError, match=preflight.UNVERIFIED_LIMIT):
        research(tmp_path).propose(report(), provider=provider, jobpilot_env=tmp_path/'missing', require_verified_input_limit=True)
    assert not list(tmp_path.glob('*.sqlite'))


def test_strict_read_cached_advice_is_current_zero_work_without_fabricating_old_proof(tmp_path, monkeypatch):
    advisor = FreeAdvisor(parameters=('l2', 'threshold')); value = report()
    original = ResearchRequests(tmp_path/'api.sqlite').propose(advisor, value, execute=lambda: completed(advisor, value))
    monkeypatch.setattr(coordinator, 'run_provider_worker', lambda *a, **k: pytest.fail('cache must not launch'))
    result = research(tmp_path).propose(value, provider='openrouter', jobpilot_env=tmp_path/'missing', require_verified_input_limit=True)
    advice = result['result']['advice']
    assert advice['api_cached'] and advice['request_key'] == original['request_key']
    assert 'input_preflight' not in advice
    assert result['invocation_observed']['remote_completions'] == 0
    assert result['invocation_resources']['tokens']['input_tokens'] == 0
    assert result['input_admission']['require_verified_input_limit']
    assert not result['input_admission']['current_preflight']['hard_input_token_limit_verified']
    repeated = research(tmp_path).propose(value, provider='openrouter', require_verified_input_limit=True)
    assert repeated['coordinator_cached']


def test_cached_lookup_is_read_only_and_keeps_original_request_identity(tmp_path):
    path = tmp_path/'api.sqlite'; advisor = FreeAdvisor(parameters=('l2', 'threshold')); value = report()
    assert ResearchRequests(path).read_cached(advisor, value) is None and not path.exists()
    result = ResearchRequests(path).propose(advisor, value, execute=lambda: completed(advisor, value))
    before = path.read_bytes()
    cached = ResearchRequests(path).read_cached(advisor, value)
    assert cached['request_key'] == result['request_key'] and path.read_bytes() == before
    old_inputs = {'report': value, 'provider': advisor.provider, 'model': advisor.model, 'endpoint_sha256': None,
        'parameters': list(advisor.parameters), 'prompt_version': PROMPT_VERSION, 'system_sha256': digest(SYSTEM),
        'catalog': {p: CATALOG[p] for p in advisor.parameters}}
    assert cached['request_key'] == digest(old_inputs)


@pytest.mark.parametrize('damage', ["UPDATE advisor_requests SET payload_sha256='bad'",
    "UPDATE advisor_requests SET status='reserved'", 'UPDATE request_policy SET maximum=1', 'DELETE FROM request_policy'])
def test_strict_mode_refuses_corrupt_interrupted_or_rebound_cache_without_new_common_attempt(tmp_path, damage):
    advisor = FreeAdvisor(parameters=('l2', 'threshold')); value = report()
    ResearchRequests(tmp_path/'api.sqlite').propose(advisor, value, execute=lambda: completed(advisor, value))
    with sqlite3.connect(tmp_path/'api.sqlite') as db: db.execute(damage)
    with pytest.raises(ValueError): research(tmp_path).propose(value, provider='openrouter', require_verified_input_limit=True)
    assert not (tmp_path/'common.sqlite').exists()


def test_fresh_admission_is_rechecked_even_if_prior_readonly_lookup_was_successful(tmp_path, monkeypatch):
    fake = {'api_cached': True}
    monkeypatch.setattr(ResearchRequests, 'read_cached', lambda *a, **k: fake)
    monkeypatch.setattr(coordinator, 'run_provider_worker', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(RuntimeError): research(tmp_path).propose(report(), provider='openrouter', require_verified_input_limit=True)
    with sqlite3.connect(tmp_path/'api.sqlite') as db:
        assert db.execute('SELECT count(*) FROM advisor_requests').fetchone()[0] == 0
    assert research(tmp_path).budget.snapshot()['statuses'] == {'failed': 1}


@pytest.mark.parametrize('required', [1, None, 'yes'])
def test_nonboolean_requirement_is_not_accepted(tmp_path, required):
    with pytest.raises(ValueError): research(tmp_path).propose(report(), provider='openrouter', require_verified_input_limit=required)
    assert not list(tmp_path.glob('*.sqlite'))


def test_precancellation_takes_priority_over_strict_cache_lookup(tmp_path, monkeypatch):
    cancel = threading.Event(); cancel.set()
    monkeypatch.setattr(ResearchRequests, 'read_cached', lambda *a, **k: pytest.fail('must not read cache'))
    with pytest.raises(BudgetCancelled):
        research(tmp_path).propose(report(), provider='openrouter', require_verified_input_limit=True, cancel_event=cancel)


def test_strict_mock_does_not_require_provider_capability(tmp_path):
    result = research(tmp_path).propose(report(), mock=Advisor().propose(report())['proposal'], require_verified_input_limit=True)
    assert result['input_admission']['current_preflight'] is None and result['invocation_observed']['remote_completions'] == 0


@pytest.mark.parametrize('strict', [False, True])
def test_offline_audit_cli_is_private_and_does_not_call_providers(tmp_path, monkeypatch, strict):
    diagnostics = tmp_path/'report.json'; diagnostics.write_text(canonical(report())); output = tmp_path/'audit.json'
    monkeypatch.setattr(FreeAdvisor, 'propose', lambda *a, **k: pytest.fail('no inference'))
    args = ['--diagnostics', str(diagnostics), '--provider', 'openrouter', '--output', str(output)]
    if strict: args.append('--require-verified-input-limit')
    assert preflight.main(args) == int(strict)
    result = json.loads(output.read_text())
    assert result['status'] == ('rejected' if strict else 'completed')
    assert result['api_calls'] == result['journal_mutations'] == 0 and not result['credentials_read']
    assert result['input_preflight']['input_tokens_upper_bound'] is None
    assert output.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob('*.sqlite'))
    with pytest.raises(FileExistsError): preflight.main(args)


def test_audit_module_entrypoint_rejects_strict_limit_without_traceback(tmp_path):
    path = tmp_path/'report.json'; path.write_text(canonical(report())); output = tmp_path/'audit.json'
    result = subprocess.run([sys.executable, '-m', 'cryptoforge.llm_prompt_preflight', '--diagnostics', str(path),
        '--provider', 'ollama', '--require-verified-input-limit', '--output', str(output)], capture_output=True,
        env={'PYTHONPATH': str(Path(preflight.__file__).resolve().parents[1]), 'PYTHONDONTWRITEBYTECODE': '1'}, timeout=3)
    assert result.returncode == 1 and b'Traceback' not in result.stderr
    assert json.loads(output.read_text())['error'] == preflight.UNVERIFIED_LIMIT


def test_payload_bound_counts_escaping_and_model_bytes():
    messages = [{'role': 'user', 'content': '\U0001f600'*3000}]
    with pytest.raises(ValueError, match='payload byte limit'):
        preflight.provider_payload(messages, 'ollama', 'local-model')


def test_advice_audit_matches_actual_transport_payload():
    payloads = []
    def transport(url, payload=None, *args, **kwargs):
        if url.endswith('/models'): return catalog()
        payloads.append(payload)
        return {'model': DEFAULT_MODEL, 'choices': [{'finish_reason': 'stop', 'message': {'content': canonical(proposal())}}]}
    advice = FreeAdvisor(api_key='synthetic-key', transport=transport).propose(report())
    assert advice['input_preflight']['request_payload_sha256'] == digest(payloads[0])
    assert advice['request_sha256'] == digest(payloads[0]['messages'])


def test_large_cache_payload_within_worker_bound_can_be_read_without_new_execution(tmp_path):
    advisor = Advisor(); value = report(); result = advisor.propose(value); result['fixture_padding'] = 'x'*70000
    original = ResearchRequests(tmp_path/'api.sqlite').propose(advisor, value, execute=lambda: result)
    cached = ResearchRequests(tmp_path/'api.sqlite').read_cached(advisor, value)
    assert cached['request_key'] == original['request_key'] and cached['fixture_padding'] == result['fixture_padding']


def test_exact_message_byte_boundary_is_accepted_and_next_byte_is_rejected():
    value = report(); value['development_end'] = '2026-01-02T00:00:00.1Z'
    advisor = FreeAdvisor(); first = advisor.preflight(value)
    extra = preflight.MAX_MESSAGE_BYTES-first['audit']['message_bytes']
    value['development_end'] = '2026-01-02T00:00:00.'+'1'*(extra+1)+'Z'
    assert advisor.preflight(value)['audit']['message_bytes'] == preflight.MAX_MESSAGE_BYTES
    value['development_end'] = value['development_end'][:-1]+'1Z'
    with pytest.raises(ValueError, match='byte limit'): advisor.preflight(value)


def test_oversized_cache_result_fails_without_persisting_its_content(tmp_path):
    advisor = Advisor(); value = report(); result = advisor.propose(value); result['fixture_padding'] = 'x'*512000
    with pytest.raises(ValueError, match='cache payload'):
        ResearchRequests(tmp_path/'api.sqlite').propose(advisor, value, execute=lambda: result)
    with sqlite3.connect(tmp_path/'api.sqlite') as db:
        assert db.execute('SELECT status,payload FROM advisor_requests').fetchone() == ('failed', None)


def test_coordinator_cli_strict_fresh_refusal_has_reason_and_no_journal(tmp_path):
    value = report(); artifact = {'production_compatible': False, 'origin': 'synthetic_fixture'}
    receipt = {'status': 'completed', 'command': 'run', 'result': {'artifact': artifact,
        'artifact_sha256': digest(artifact), 'dataset_sha256': value['dataset_sha256'],
        'reports': {'validation': {'diagnostics': value}}}}
    source = tmp_path/'baseline.json'; source.write_text(canonical(receipt)); output = tmp_path/'denied.json'
    assert coordinator.main(['--database', str(tmp_path/'common.sqlite'), '--proposal-ledger', str(tmp_path/'api.sqlite'),
        '--semantic-ledger', str(tmp_path/'semantic.sqlite'), '--fit-ledger', str(tmp_path/'fit.sqlite'),
        '--output', str(output), 'proposal', '--experiment-receipt', str(source), '--provider', 'openrouter',
        '--require-verified-input-limit', '--jobpilot-env', str(tmp_path/'missing.env')]) == 1
    assert json.loads(output.read_text())['error_code'] == preflight.UNVERIFIED_LIMIT
    assert output.stat().st_mode & 0o777 == 0o600 and not list(tmp_path.glob('*.sqlite'))
