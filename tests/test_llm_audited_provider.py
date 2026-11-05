"""Synthetic loopback and accounting only; no external model or credentials."""
from contextlib import contextmanager
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import stat
import subprocess
import threading
import time

import pytest
from test_llm_research_requests import report, Advisor
from test_llm_research_coordinator import coordinator
from test_llm_exchange_audit import response, SECRET
from cryptoforge import llm_audited_provider as m
from cryptoforge import llm_prompt_preflight as prompt
from cryptoforge.research_run_budget import DEFAULT_POLICY


@contextmanager
def local(mode='success'):
    calls = []; started = threading.Event(); stop = threading.Event()
    proposal = Advisor().propose(report())['proposal']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path, payload, self.headers.get('Authorization'))); started.set()
            if mode == 'slow_headers': stop.wait(3)
            body = {'model': 'fixture-local', 'done': True, 'done_reason': 'stop',
                'message': {'role': 'assistant', 'content': m.canonical(proposal)},
                'prompt_eval_count': 100, 'eval_count': 50}
            if mode == 'tools': body['message']['tool_calls'] = [{'name': 'shell'}]
            if mode == 'secret': body['message']['content'] = SECRET
            if mode == 'invalid_usage': body['eval_count'] = True
            raw = m.canonical(body).encode()
            if mode == 'bad_json': raw = b'not JSON private response'
            self.send_response(400 if mode == 'HTTP400' else 302 if mode == 'redirect' else 200)
            if mode == 'redirect': self.send_header('Location', 'https://unrequested.example')
            self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try:
                if mode == 'slow_drip':
                    for byte in raw:
                        self.wfile.write(bytes([byte])); self.wfile.flush()
                        if stop.wait(.01): break
                else: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True); thread.start()
    try:
        yield m.FreeAdvisor(provider='ollama', model='fixture-local',
            ollama_url=f'http://127.0.0.1:{server.server_port}', parameters=('l2', 'threshold')), calls, started
    finally:
        stop.set(); server.shutdown(); server.server_close(); thread.join(timeout=1)


def root(tmp_path):
    p = tmp_path/'audit'; p.mkdir(mode=0o700); return p


def call(research, adapter, output, **kwargs):
    return m.propose_audited(research, report(), audit_root=output, provider=adapter.provider,
        model=adapter.model, ollama_url=adapter.ollama_url, require_verified_input_limit=False, **kwargs)


def binding(tmp_path, adapter):
    journal = m.ResearchRequests(tmp_path/'api.sqlite')
    return m._journal_binding(journal, adapter, report())


def test_real_fixed_child_success_is_bound_private_and_cached_without_HTTP_or_key(tmp_path, monkeypatch):
    output = root(tmp_path); research = coordinator(tmp_path)
    monkeypatch.setenv('UNRELATED_SECRET', 'must-not-be-inherited')
    launched = []; original = subprocess.Popen
    def launch(*args, **kwargs):
        assert 'UNRELATED_SECRET' not in kwargs['env']
        assert kwargs['stderr'] == subprocess.DEVNULL
        p = original(*args, **kwargs); launched.append(p); return p
    monkeypatch.setattr(m.subprocess, 'Popen', launch)
    with local() as (adapter, calls, _):
        first = call(research, adapter, output)
        assert first['original_exchange_verified'] and len(calls) == 1
        monkeypatch.setattr(m, '_run_worker', lambda *a, **k:pytest.fail('no recapture'))
        second = call(research, adapter, output, jobpilot_env=tmp_path/'absent.env')
    assert second['coordinator_cached'] and second['invocation_observed'] == m.ZERO_USAGE
    assert second['operation_key'] == first['operation_key'] and len(calls) == 1
    advice = first['result']['advice']; directory = output/advice['request_key']
    checked = m.verify_attempt(directory, expected_binding=binding(tmp_path, adapter))
    assert checked['validation']['usage']['total_tokens'] == 150
    assert checked['local_outcome']['child_reaped'] and launched[0].poll() is not None
    assert checked['validation']['status'] == 'proposal_schema_valid_only'
    assert calls[0][2] is None and calls[0][1]['options']['num_predict'] == 2048
    for p in [output, *output.rglob('*')]:
        assert stat.S_IMODE(p.stat().st_mode) == (0o700 if p.is_dir() else 0o600)
    assert research.budget.snapshot()['total_reserved_actions'] == 1
    assert not (tmp_path/'fit.sqlite').exists()


@pytest.mark.parametrize('mode', ['tools', 'invalid_usage', 'bad_json', 'HTTP400', 'secret'])
def test_rejected_response_preserves_cleaned_evidence_and_failed_both_reservations(tmp_path, monkeypatch, mode):
    output = root(tmp_path); research = coordinator(tmp_path)
    monkeypatch.setenv('CRYPTOFORGE_OPENROUTER_API_KEY', SECRET)
    with local(mode) as (adapter, calls, _):
        with pytest.raises(RuntimeError, match='coordinated action failed'): call(research, adapter, output)
        with pytest.raises(ValueError, match='no automatic retry'): call(research, adapter, output)
    assert len(calls) == 1
    directory = output/binding(tmp_path, adapter)['request_key']; checked = m.verify_attempt(directory)
    assert checked['local_outcome']['status'] == 'failed' and checked['capture_available']
    assert checked['validation']['usage']['prompt_tokens'] == (None if mode == 'bad_json' else 100)
    for p in directory.rglob('*'):
        if p.is_file(): assert SECRET not in p.read_text() and 'not JSON private response' not in p.read_text()
    with sqlite3.connect(tmp_path/'api.sqlite') as db: assert db.execute('SELECT status FROM advisor_requests').fetchone()[0] == 'failed'
    assert research.budget.snapshot()['total_reserved_actions'] == 1
    if mode == 'secret': assert checked['validation']['status'] == 'rejected_response_privacy'


@pytest.mark.parametrize('mode', ['slow_headers', 'slow_drip'])
def test_timeout_reaps_child_and_keeps_unknown_nonrefunded_outcome(tmp_path, mode):
    output = root(tmp_path)
    with local(mode) as (adapter, calls, started):
        b = binding(tmp_path, adapter); before = time.monotonic()
        with pytest.raises(m.AdvisorTimedOut):
            m._run_worker(adapter, report(), output/b['request_key'], b, wall_seconds=.7)
        assert .4 <= time.monotonic()-before < 2 and started.is_set() and len(calls) == 1
    checked = m.verify_attempt(output/b['request_key'])
    assert not checked['capture_available'] and checked['local_outcome']['status'] == 'timed_out'
    assert not checked['local_outcome']['server_cancellation_verified']
    assert not checked['local_outcome']['missing_usage_means_zero']
    assert not checked['local_outcome']['failed_or_interrupted_attempt_refunded']


def test_cancellation_after_request_preserves_attempt_and_reaps(tmp_path):
    output = root(tmp_path); cancel = threading.Event()
    with local('slow_headers') as (adapter, calls, started):
        def trigger():
            assert started.wait(2); cancel.set()
        thread = threading.Thread(target=trigger); thread.start(); b = binding(tmp_path, adapter)
        with pytest.raises(m.AdvisorCancelled):
            m._run_worker(adapter, report(), output/b['request_key'], b, wall_seconds=3, cancel_event=cancel)
        thread.join(1)
    assert len(calls) == 1
    assert m.verify_attempt(output/b['request_key'])['local_outcome']['status'] == 'cancelled'


def test_strict_input_limit_refuses_before_any_reservation_key_or_directory(tmp_path, monkeypatch):
    output = root(tmp_path); research = coordinator(tmp_path)
    monkeypatch.setattr(m, '_run_worker', lambda *a, **k:pytest.fail('no worker'))
    with pytest.raises(ValueError, match=prompt.UNVERIFIED_LIMIT):
        m.propose_audited(research, report(), audit_root=output, jobpilot_env=tmp_path/'absent.env')
    assert not list(output.iterdir()) and not list(tmp_path.glob('*.sqlite'))


def test_existing_legacy_cache_is_read_under_strict_limit_without_manufacturing_wire(tmp_path, monkeypatch):
    output = root(tmp_path); adapter = m.FreeAdvisor(parameters=('l2', 'threshold'))
    legacy = Advisor().propose(report()); legacy['provider'] = 'openrouter'; legacy['model'] = adapter.model
    m.ResearchRequests(tmp_path/'api.sqlite').propose(adapter, report(), execute=lambda:legacy)
    monkeypatch.setattr(m, '_run_worker', lambda *a, **k:pytest.fail('legacy cache must not recapture'))
    result = m.propose_audited(coordinator(tmp_path), report(), audit_root=output, jobpilot_env=tmp_path/'absent.env')
    assert result['result']['advice']['api_cached'] and not result['original_exchange_verified']
    assert not result['result']['exchange_capture']['available'] and not list(output.iterdir())
    assert result['invocation_observed'] == m.ZERO_USAGE


def test_common_cap_stops_before_inner_API_and_worker(tmp_path, monkeypatch):
    output = root(tmp_path); research = coordinator(tmp_path, policy={**DEFAULT_POLICY, 'total_actions': 1})
    research.propose(report(), mock=Advisor().propose(report())['proposal'])
    monkeypatch.setattr(m, '_run_worker', lambda *a, **k:pytest.fail('budget first'))
    with pytest.raises(ValueError, match='budget exhausted'):
        m.propose_audited(research, report(), audit_root=output, require_verified_input_limit=False)
    assert not list(output.iterdir()) and not (tmp_path/'api.sqlite').exists()


def test_missing_or_changed_capture_is_not_repaired_by_cache_hit(tmp_path):
    output = root(tmp_path); research = coordinator(tmp_path)
    with local() as (adapter, calls, _):
        result = call(research, adapter, output)
        directory = output/result['result']['advice']['request_key']
        path = directory/'exchange/response.json'; path.write_text('{}')
        with pytest.raises(ValueError): call(research, adapter, output)
    assert len(calls) == 1 and research.budget.snapshot()['total_reserved_actions'] == 1


def test_fixed_free_catalog_and_nonzero_cost_rejection_are_saved_without_external_network(tmp_path, monkeypatch):
    output = root(tmp_path); adapter = m.FreeAdvisor(parameters=('l2', 'threshold')); b = binding(tmp_path, adapter)
    directory = output/b['request_key']; directory.mkdir(mode=0o700)
    m.files._write(directory, 'attempt.json', {'binding': b, 'implementation': m._LOADED, 'policy': m.POLICY,
        'request_payload_sha256': m.digest(adapter.preflight(report())['payload'])})
    calls = []
    raw = response(change=lambda body:body['usage'].update(cost='0.02'))
    def http(url, payload=None, headers=None, timeout=30):
        calls.append((url, payload, headers))
        if payload is None: return 200, m.canonical({'data': [{'id':adapter.model,'pricing':{'prompt':'0','completion':'0'}}]}).encode()
        return 200, raw
    monkeypatch.setattr(m, '_http', http)
    data = {'report':report(), 'settings': {'provider':adapter.provider,'model':adapter.model,
        'ollama_url':adapter.ollama_url, 'parameters':list(adapter.parameters),'timeout':3,'api_key':SECRET,'jobpilot_env':None},
        'wall_seconds':3,'directory':str(directory),'binding':b,'implementation':m._LOADED}
    with pytest.raises(m.AdvisorUnavailable, match='response refused'): m._evaluate(data)
    checked = m.verify_attempt(directory, finished=False)
    assert checked['validation']['provider_reported_cost_usd'] == '0.02'
    assert checked['validation']['usage']['total_tokens'] == 150 and len(calls) == 2
    assert calls[1][2]['Authorization'] == 'Bearer '+SECRET
    assert SECRET not in ''.join(p.read_text() for p in directory.rglob('*') if p.is_file())


@pytest.mark.parametrize('change', ['capture_binding', 'response_hash', 'request_hash', 'manifest_hash', 'source', 'symlink'])
def test_transport_and_API_identity_tampering_is_rejected_without_model_or_network(tmp_path, change):
    output = root(tmp_path)
    with local() as (adapter, _, _):
        b = binding(tmp_path, adapter)
        m._run_worker(adapter, report(), output/b['request_key'], b, wall_seconds=3)
    directory = output/b['request_key']
    if change == 'source':
        attempt = m._read(directory, 'attempt.json'); attempt['implementation'] = {}
        (directory/'attempt.json').write_text(m.canonical(attempt))
    elif change == 'symlink':
        (directory/'capture.json').unlink(); (directory/'capture.json').symlink_to(directory/'attempt.json')
    else:
        capture = m._read(directory, 'capture.json')
        if change == 'capture_binding': capture['binding']['request_key'] = 'a'*64
        else: capture[{'response_hash':'response_body_sha256','request_hash':'request_payload_sha256','manifest_hash':'exchange_manifest_sha256'}[change]] = 'a'*64
        (directory/'capture.json').write_text(m.canonical(capture))
    with pytest.raises(ValueError): m.verify_attempt(directory, expected_binding=b)


def test_symlink_or_public_audit_root_and_precancellation_never_reserve(tmp_path):
    research = coordinator(tmp_path); public = tmp_path/'public'; public.mkdir(mode=0o755)
    with pytest.raises(ValueError, match='owner_private'):
        m.propose_audited(research, report(), audit_root=public, require_verified_input_limit=False)
    cancel = threading.Event(); cancel.set()
    with pytest.raises(m.BudgetCancelled): m.propose_audited(research, report(), audit_root=public, cancel_event=cancel)
    assert not list(tmp_path.glob('*.sqlite'))


def test_existing_v5_phase_history_allocations_and_numeric_cap_are_preserved(tmp_path):
    from types import MappingProxyType
    from test_research_phase import migrated
    from test_research_run_budget import bindings
    from cryptoforge import research_phase as phase
    budget, _, _ = migrated(tmp_path)
    # Reuse the fixture's already-bound v5 journal, not a replacement database.
    research = object.__new__(phase.PhaseResearchCoordinator)
    research.paths = MappingProxyType(bindings(tmp_path)); research.budget = budget
    before = budget.snapshot()
    with sqlite3.connect(budget.path) as db: history = phase._history(db)
    output = root(tmp_path)
    with local() as (adapter, calls, _):
        first = call(research, adapter, output); second = call(research, adapter, output)
    assert not first['coordinator_cached'] and second['cache_origin'] == 'v5' and len(calls) == 1
    after = budget.snapshot()
    assert after['total_reserved_actions'] == before['total_reserved_actions']+1
    assert after['numeric_control_lifetime_used'] == before['numeric_control_lifetime_used']
    assert after['numeric_control_lifetime_limit'] == before['numeric_control_lifetime_limit']
    with sqlite3.connect(budget.path) as db: assert phase._history(db) == history


def test_worker_start_failure_remains_charged_and_cannot_recreate_attempt(tmp_path, monkeypatch):
    output = root(tmp_path); research = coordinator(tmp_path)
    def fail(*a, **k): raise OSError('private process failure')
    monkeypatch.setattr(m.subprocess, 'Popen', fail)
    with pytest.raises(RuntimeError):
        m.propose_audited(research, report(), audit_root=output, require_verified_input_limit=False)
    directory = next(output.iterdir()); checked = m.verify_attempt(directory)
    assert checked['local_outcome']['status'] == 'failed' and not checked['capture_available']
    with pytest.raises(ValueError, match='no automatic retry'):
        m.propose_audited(research, report(), audit_root=output, require_verified_input_limit=False)
    assert research.budget.snapshot()['total_reserved_actions'] == 1


def test_redirect_cannot_become_another_request_or_claim_a_complete_exchange(tmp_path):
    output = root(tmp_path)
    with local('redirect') as (adapter, calls, _):
        b = binding(tmp_path, adapter)
        with pytest.raises(m.AdvisorUnavailable):
            m._run_worker(adapter, report(), output/b['request_key'], b, wall_seconds=3)
    assert len(calls) == 1
    checked = m.verify_attempt(output/b['request_key'])
    assert not checked['capture_available'] and checked['local_outcome']['status'] == 'failed'
