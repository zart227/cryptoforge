from contextlib import contextmanager, closing
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import threading
import time

import pytest

from cryptoforge import local_semantic_contracts as contracts
from cryptoforge import local_semantic_requests as journal_module
from cryptoforge import local_semantic_worker as worker
from cryptoforge import llm_research_coordinator as coordinator
from cryptoforge.research_run_budget import ResearchRunBudget, DEFAULT_POLICY as COMMON_POLICY, ZERO_USAGE, BudgetCancelled, BudgetTimedOut
from cryptoforge.research_resource_budget import ZERO_TOKENS
from cryptoforge.research_semantic_budget import DEFAULT_SEMANTIC_POLICY
from cryptoforge.semantic_research_catalog import SemanticResearchCatalog
from cryptoforge.research_training_diagnostics import canonical, digest
from test_ollama_systemone import catalog, response


def record(index=0):
    return {'schema_version': 'semantic-research-record-v1', 'experiment_id': digest({'synthetic': index}),
        'artifact_sha256': 'a'*64, 'dataset_sha256': 'b'*64, 'source_sha256': 'c'*64,
        'partition': 'validation', 'config': {'l2': 0.01, 'threshold': 0.6}, 'decision_threshold': 0.6,
        'metrics': {'count': 8, 'positive_rate': 0.5, 'predicted_positive_rate': 0.5, 'precision': 0.5,
            'recall': 0.5, 'calibration_error_10': 0.2, 'brier_score': 0.25, 'log_loss': 0.7},
        'hypothesis': 'Synthetic threshold hypothesis.', 'conclusion': 'Synthetic protocol fixture, no measured gain.',
        'independent_evidence': False}


def prepare(catalog, endpoint='http://127.0.0.1:11434', index=0):
    return contracts.prepare_request(record(index), catalog, endpoint=endpoint, digest_pin='d'*64)


def transport_fixture(request, response):
    response = deepcopy(response); response['model'] = request['model_reference']
    version = digest({'version': '0.40.5'})
    return {'request_sha256': request['request_sha256'], 'inference_identity_sha256': contracts.inference_identity(request),
        'response': response, 'metadata': {
        'server_version': '0.40.5', 'model_reference': request['model_reference'],
        'version_before_sha256': version, 'version_after_sha256': version, 'show_sha256': 'e'*64,
        'capabilities': ['decision'], 'checked_at': '2026-10-18T00:00:00+00:00'}}


def inner(tmp_path, **kwargs):
    return journal_module.LocalSemanticRequests(tmp_path/'live.sqlite',
        {'common_path_sha256': 'a'*64, 'semantic_configuration_sha256': 'b'*64}, **kwargs)


@contextmanager
def backend(response, mode='success'):
    calls, started, stop = [], threading.Event(), threading.Event()
    versions = 0
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def respond(self):
            nonlocal versions
            body = None if self.command == 'GET' else json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'method': self.command, 'path': self.path, 'body': body,
                'authorization': self.headers.get('Authorization')})
            if self.path == '/api/version':
                versions += 1
                value = {'version': '0.35.1' if mode == 'old_version' else
                    '0.40.6' if mode == 'version_drift' and versions > 1 else '0.40.5'}
                if mode == 'slow_version': started.set(); stop.wait(4)
            elif self.path == '/api/show':
                value = {'capabilities': ['completion'] if mode == 'chat_only' else ['decision']}
                if mode in ('remote_host', 'remote_model'): value[mode] = 'paid remote'
                if mode == 'manifest_swap': value['manifests'] = [{'digest': 'f'*64, 'selected': True}]
                if mode == 'slow_metadata': started.set(); stop.wait(4)
            elif self.path == '/v1/systemone':
                started.set()
                if mode == 'slow_headers': stop.wait(4)
                if mode == 'redirect':
                    self.send_response(302); self.send_header('Location', 'https://unrequested.invalid'); self.end_headers(); return
                value = deepcopy(response); value['model'] = body['model']
                if mode == 'wrong_model': value['model'] = 'nimble:latest'
                if mode == 'invalid_usage': value['usage']['input_tokens'] = True
                if mode == 'usage_overrun': value['usage']['input_tokens'] = 32001
                if mode == 'bad_answer': value['answers']['supported']['confidence'] = 0.99
                if mode == 'missing_answer': value['answers'].pop('supported')
                if mode == 'unknown_question': value['answers']['unrequested'] = {'type': 'noul', 'noul': 1}
            else:
                self.send_error(500); return
            raw = canonical(value).encode()
            if self.path == '/v1/systemone':
                if mode == 'bad_json': raw = b'{private invalid response'
                if mode == 'duplicate_json': raw = b'{"model":"private","model":"duplicate"}'
                if mode == 'oversized': raw = b'x'*64001
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try:
                if mode == 'slow_drip' and self.path == '/v1/systemone':
                    for byte in raw:
                        self.wfile.write(bytes([byte])); self.wfile.flush()
                        if stop.wait(0.02): break
                else: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass
        do_GET = respond
        do_POST = respond
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}', calls, started
    finally: stop.set(); server.shutdown(); server.server_close(); thread.join(timeout=1)


def make_coordinator(tmp_path, *, migrate=True, policy=None):
    paths = {kind: tmp_path/(kind+'.sqlite') for kind in ('proposal', 'semantic_fixture', 'fit')}
    common = tmp_path/'common.sqlite'
    ResearchRunBudget(common, paths, policy=policy).run('fit', {'synthetic_setup': True},
        lambda: {'result': {'origin': 'synthetic_fixture'}, 'observed': dict(ZERO_USAGE)})
    research = coordinator.ResearchCoordinator(common, proposal_ledger=paths['proposal'],
        semantic_ledger=paths['semantic_fixture'], fit_ledger=paths['fit'], semantic_live_ledger=tmp_path/'live.sqlite',
        semantic_live_policy=DEFAULT_SEMANTIC_POLICY, policy=policy)
    if migrate: research.budget.migrate_semantic_budget()
    store = SemanticResearchCatalog(tmp_path/'records.sqlite')
    with closing(store._db()) as db, db:
        value = record()
        db.execute('INSERT INTO semantic_records VALUES (?,?,?)', (value['experiment_id'], digest(value), canonical(value)))
    return research, store


def capture(monkeypatch):
    processes, launches = [], []; original = subprocess.Popen
    def launch(*args, **kwargs):
        launches.append((args, kwargs)); process = original(*args, **kwargs); processes.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    return processes, launches


def test_request_uses_closed_record_native_digest_and_code_side_thresholds(catalog):
    request = prepare(catalog)
    assert request['model_reference'] == 'sha256-'+'d'*64+':local'
    assert request['wire_request']['model'] == request['model_reference']
    assert request['wire_request']['state'] == {'experiment': record()}
    assert set(request['wire_request']) == {'model', 'state', 'questions', 'keep_alive'}
    for q in request['wire_request']['questions'].values(): assert set(q) == {'type', 'instructions', 'criteria'}
    assert not request['hard_input_token_limit_verified'] and not request['byte_limit_is_token_limit']


@pytest.mark.parametrize('change', ['test', 'secret_field', 'bad_digest', 'cloud_endpoint', 'old_version', 'oversized_state'])
def test_bad_inputs_are_rejected_before_any_worker_or_journal(tmp_path, catalog, monkeypatch, change):
    value, kwargs = record(), {'endpoint': 'http://127.0.0.1:11434', 'digest_pin': 'd'*64}
    if change == 'test': value['partition'] = 'test'
    elif change == 'secret_field': value['credentials'] = 'must not be accepted'
    elif change == 'bad_digest': kwargs['digest_pin'] = 'short'
    elif change == 'cloud_endpoint': kwargs['endpoint'] = 'https://ollama.com'
    elif change == 'old_version': kwargs['version'] = '0.35.1'
    else: value['hypothesis'] = '\U0001f4c8'*4000
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('no worker'))
    with pytest.raises(ValueError): contracts.prepare_request(value, catalog, **kwargs)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('field', ['record', 'catalog', 'wire_request', 'model_digest', 'implementation'])
def test_request_mutations_are_not_execution_instructions(catalog, field, monkeypatch):
    request = prepare(catalog)
    if field == 'record': request['record']['hypothesis'] = 'Changed evidence.'
    elif field == 'catalog': request['catalog']['questions']['supported']['accept_above'] = 0.9
    elif field == 'wire_request': request['wire_request']['tools'] = [{'command': 'must not execute'}]
    elif field == 'model_digest': request['model_digest'] = 'e'*64
    else: request['implementation']['contracts'] = '0'*64
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('no process'))
    with pytest.raises(ValueError): worker.run_worker(request, wall_seconds=1)


def test_legal_question_catalog_that_exceeds_wire_limit_is_not_truncated(catalog):
    large = deepcopy(catalog)
    question = deepcopy(catalog['questions']['supported']); question['instructions'] = 'x'*3000
    large['questions'] = {f'q{i:02d}': deepcopy(question) for i in range(16)}
    with pytest.raises(ValueError, match='no truncation'): prepare(large)
    assert len(large['questions']) == 16 and len(large['questions']['q00']['instructions']) == 3000


def test_pure_normalizer_keeps_live_transport_separate_from_mock_predictions(catalog, response):
    request = prepare(catalog); result = contracts.normalize_transport(request, transport_fixture(request, response))
    assert result['origin'] == 'ollama_local_systemone' and result['api_calls'] == 1
    assert result['answers']['mechanism']['value'] == 'threshold'
    assert result['answers']['supported']['status'] == 'abstain'
    assert result['answers']['clarity']['value'] == 1.8
    assert not result['calibrated_policy'] and not result['live_model_quality_evaluated']
    assert not result['independent_trading_evidence']
    assert 'not_runtime_attestation' in result['model_identity_assurance']


def test_worker_real_loopback_has_fixed_argv_minimal_env_and_digest_only(catalog, response, monkeypatch):
    processes, launches = capture(monkeypatch)
    monkeypatch.setenv('UNRELATED_SECRET', 'not-inherited')
    monkeypatch.setenv('OLLAMA_API_KEY', 'synthetic-unused-key')
    monkeypatch.setenv('HTTP_PROXY', 'http://unrequested.invalid:9999')
    with backend(response) as (endpoint, calls, _):
        request = prepare(catalog, endpoint)
        transport = worker.run_worker(request, wall_seconds=3)
    assert [(r['method'], r['path']) for r in calls] == [('GET', '/api/version'), ('POST', '/api/show'),
        ('POST', '/v1/systemone'), ('GET', '/api/version')]
    assert calls[1]['body'] == {'model': request['model_reference']}
    assert calls[2]['body'] == request['wire_request'] and all(c['authorization'] is None for c in calls)
    args, kwargs = launches[0]
    assert args[0][1:] == ['-m', 'cryptoforge.local_semantic_worker', '--worker']
    assert 'UNRELATED_SECRET' not in kwargs['env'] and 'OLLAMA_API_KEY' not in kwargs['env']
    assert 'HTTP_PROXY' not in kwargs['env'] and kwargs['start_new_session']
    assert all(p.poll() is not None and p.stdin.closed for p in processes)
    assert contracts.normalize_transport(request, transport)['provider_reported_usage'] == {'input_tokens': 123, 'output_tokens': 7}


@pytest.mark.parametrize('mode,requests', [('old_version', 1), ('remote_host', 2), ('remote_model', 2),
    ('chat_only', 2), ('manifest_swap', 2), ('wrong_model', 4), ('invalid_usage', 4), ('unknown_question', 4),
    ('version_drift', 4), ('redirect', 3), ('bad_json', 3), ('duplicate_json', 3), ('oversized', 3)])
def test_worker_rejects_unsafe_metadata_or_response_without_retry(catalog, response, mode, requests):
    with backend(response, mode) as (endpoint, calls, _):
        with pytest.raises(worker.SemanticUnavailable) as error:
            worker.run_worker(prepare(catalog, endpoint), wall_seconds=3)
    assert len(calls) == requests and 'private' not in str(error.value)
    assert sum(c['path'] == '/v1/systemone' for c in calls) <= 1


@pytest.mark.parametrize('mode', ['bad_answer', 'missing_answer'])
def test_bad_question_becomes_error_while_companions_survive(catalog, response, mode):
    with backend(response, mode) as (endpoint, _, _):
        request = prepare(catalog, endpoint)
        result = contracts.normalize_transport(request, worker.run_worker(request, wall_seconds=3))
    assert result['answers']['supported']['status'] == 'error'
    assert 'decision' not in result['answers']['supported']
    assert result['answers']['mechanism']['status'] == 'available'


@pytest.mark.parametrize('mode', ['slow_headers', 'slow_drip', 'slow_version', 'slow_metadata'])
def test_one_deadline_covers_metadata_and_dripping_inference(catalog, response, monkeypatch, mode):
    processes, _ = capture(monkeypatch)
    with backend(response, mode) as (endpoint, calls, started):
        before = time.monotonic()
        with pytest.raises(worker.SemanticTimedOut): worker.run_worker(prepare(catalog, endpoint), wall_seconds=0.7)
        assert 0.4 <= time.monotonic()-before < 2.5 and started.is_set()
    assert all(p.poll() is not None for p in processes)
    if mode in ('slow_version', 'slow_metadata'): assert not any(c['path'] == '/v1/systemone' for c in calls)


def test_cancellation_during_http_kills_and_reaps_client(catalog, response, monkeypatch):
    processes, _ = capture(monkeypatch); cancel = threading.Event()
    with backend(response, 'slow_headers') as (endpoint, _, started):
        def cancel_when_started(): assert started.wait(timeout=3); cancel.set()
        thread = threading.Thread(target=cancel_when_started); thread.start()
        with pytest.raises(worker.SemanticCancelled): worker.run_worker(prepare(catalog, endpoint), wall_seconds=3, cancel_event=cancel)
        thread.join(timeout=1)
    assert all(p.poll() is not None for p in processes)


def test_inner_cache_is_read_without_network_keys_or_worker(tmp_path, catalog, response, monkeypatch):
    with backend(response) as (endpoint, calls, _):
        request = prepare(catalog, endpoint); journal = inner(tmp_path)
        first = journal.evaluate(request, wall_seconds=3)
    def forbidden(*args, **kwargs): pytest.fail('cache must not read keys or launch a worker')
    monkeypatch.setattr(journal_module, 'run_worker', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden); monkeypatch.setattr(os, 'getenv', forbidden)
    second = inner(tmp_path).evaluate(request, wall_seconds=0.1)
    assert not first['semantic_cached'] and second['semantic_cached'] and len(calls) == 4
    assert second['semantic_request_key'] == first['semantic_request_key']
    assert second['invocation_inference_requests'] == 0
    assert journal.snapshot()['total_requests'] == 1


@pytest.mark.parametrize('error,status', [(RuntimeError, 'failed'), (worker.SemanticCancelled, 'cancelled'),
    (worker.SemanticTimedOut, 'timed_out'), (SystemExit, 'reserved')])
def test_inner_failures_remain_charged_and_never_replay(tmp_path, catalog, monkeypatch, error, status):
    def fail(*args, **kwargs): raise error('private server body')
    monkeypatch.setattr(journal_module, 'run_worker', fail)
    journal = inner(tmp_path); request = prepare(catalog)
    with pytest.raises((RuntimeError, SystemExit)): journal.evaluate(request)
    assert journal.snapshot()['statuses'] == {status: 1} and journal.snapshot()['total_questions'] == 3
    with pytest.raises(ValueError, match='no automatic retry'): journal.evaluate(request)
    with sqlite3.connect(journal.path) as db:
        assert 'private server body' not in repr(db.execute('SELECT * FROM local_semantic_requests').fetchall())


@pytest.mark.parametrize('limit', ['requests', 'questions'])
def test_inner_lifetime_quotas_survive_next_day_and_freeze_policy(tmp_path, catalog, response, monkeypatch, limit):
    day = datetime(2026, 10, 18, tzinfo=timezone.utc)
    policy = {**journal_module.DEFAULT_POLICY, 'total_requests': 1 if limit == 'requests' else 5,
        'total_questions': 3}
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **kwargs: transport_fixture(request, response))
    first = inner(tmp_path, policy=policy, clock=lambda: day); first.evaluate(prepare(catalog))
    later = inner(tmp_path, policy=policy, clock=lambda: day+timedelta(days=1))
    with pytest.raises(ValueError, match='quota exhausted'): later.evaluate(prepare(catalog, index=1))
    with pytest.raises(ValueError, match='policy or common binding'): inner(tmp_path).snapshot()


def test_inner_cache_corruption_and_binding_changes_are_refused(tmp_path, catalog, response, monkeypatch):
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **kwargs: transport_fixture(request, response))
    request = prepare(catalog); journal = inner(tmp_path); journal.evaluate(request)
    with sqlite3.connect(journal.path) as db: db.execute("UPDATE local_semantic_requests SET payload='{}'")
    with pytest.raises(ValueError, match='checksum'): journal.evaluate(request)
    changed = journal_module.LocalSemanticRequests(journal.path,
        {'common_path_sha256': 'f'*64, 'semantic_configuration_sha256': 'b'*64})
    with pytest.raises(ValueError, match='common binding'): changed.snapshot()


def test_executor_hash_change_does_not_repeat_completed_inference(tmp_path, catalog, response, monkeypatch):
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **kwargs: transport_fixture(request, response))
    request = prepare(catalog); journal = inner(tmp_path); first = journal.evaluate(request)
    original_execution = deepcopy(first['local_execution'])
    newer = {name: 'f'*64 for name in worker.SOURCE_NAMES}
    monkeypatch.setattr(worker, 'implementation', lambda: newer)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('code update is not new inference'))
    repeat = journal.evaluate(request)
    assert repeat['semantic_cached'] and repeat['semantic_request_key'] == first['semantic_request_key']
    assert repeat['local_execution'] == original_execution and journal.snapshot()['total_requests'] == 1


def test_executor_hash_change_does_not_retry_failed_inference(tmp_path, catalog, monkeypatch):
    def fail(*args, **kwargs): raise RuntimeError('synthetic failure')
    monkeypatch.setattr(journal_module, 'run_worker', fail)
    request = prepare(catalog); journal = inner(tmp_path)
    with pytest.raises(RuntimeError): journal.evaluate(request)
    monkeypatch.setattr(worker, 'implementation', lambda: {name: 'f'*64 for name in worker.SOURCE_NAMES})
    with pytest.raises(ValueError, match='no automatic retry'): journal.evaluate(request)
    assert journal.snapshot()['total_requests'] == 1


def test_code_side_threshold_changes_renormalize_saved_raw_answers_without_inference(tmp_path, catalog, response, monkeypatch):
    monkeypatch.setattr(journal_module, 'run_worker', lambda request, **kwargs: transport_fixture(request, response))
    original = prepare(catalog); journal = inner(tmp_path); first = journal.evaluate(original)
    changed = deepcopy(catalog); changed['questions']['mechanism']['minimum_confidence'] = 0.95
    prepared = prepare(changed)
    assert prepared['request_sha256'] != original['request_sha256']
    assert contracts.inference_identity(prepared) == contracts.inference_identity(original)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('policy re-evaluation is not inference'))
    second = journal.evaluate(prepared)
    assert second['semantic_cached'] and second['answers']['mechanism']['status'] == 'abstain'
    assert first['answers']['mechanism']['status'] == 'available'
    assert second['source_request_sha256'] == original['request_sha256']
    assert second['request_sha256'] == prepared['request_sha256']


def test_concurrent_inner_admission_cannot_both_take_last_request(tmp_path, catalog, response, monkeypatch):
    barrier = threading.Barrier(2); calls = []
    policy = {**journal_module.DEFAULT_POLICY, 'total_requests': 1}
    def fake_worker(request, **kwargs):
        calls.append(request['request_sha256']); return transport_fixture(request, response)
    monkeypatch.setattr(journal_module, 'run_worker', fake_worker)
    def attempt(index):
        barrier.wait(timeout=3)
        try: inner(tmp_path, policy=policy).evaluate(prepare(catalog, index=index)); return 'completed'
        except ValueError as error:
            assert 'quota exhausted' in str(error); return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, index) for index in range(2)]
        assert sorted(f.result(timeout=5) for f in futures) == ['completed', 'rejected']
    assert len(calls) == 1 and inner(tmp_path, policy=policy).snapshot()['total_requests'] == 1


def test_same_inner_request_cannot_launch_twice_while_reserved(tmp_path, catalog, response, monkeypatch):
    started, release = threading.Event(), threading.Event(); calls = []
    request = prepare(catalog)
    def fake_worker(request, **kwargs):
        calls.append(True); started.set(); assert release.wait(timeout=5)
        return transport_fixture(request, response)
    monkeypatch.setattr(journal_module, 'run_worker', fake_worker)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(inner(tmp_path).evaluate, request)
        try:
            assert started.wait(timeout=3)
            with pytest.raises(ValueError, match='no automatic retry'): inner(tmp_path).evaluate(request)
        finally: release.set()
        future.result(timeout=5)
    assert calls == [True]


def test_coordinator_uses_both_journals_and_caches_without_new_work(tmp_path, catalog, response, monkeypatch):
    research, store = make_coordinator(tmp_path); before = store.path.read_bytes()
    with backend(response) as (endpoint, calls, _):
        first = research.semantic_live(store.path, record()['experiment_id'], catalog, digest_pin='d'*64, endpoint=endpoint)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('outer cache must not execute'))
    repeat = research.semantic_live(store.path, record()['experiment_id'], catalog, digest_pin='d'*64, endpoint=endpoint)
    assert repeat['coordinator_cached'] and len(calls) == 4 and store.path.read_bytes() == before
    assert first['kind'] == 'semantic_live' and first['invocation_observed']['local_llm_completions'] == 1
    assert first['original_resources']['tokens'] == {'input_tokens': 123, 'output_tokens': 7, 'total_tokens': 130}
    assert repeat['invocation_observed'] == ZERO_USAGE and repeat['invocation_resources']['tokens'] == ZERO_TOKENS
    snapshot = research.budget.snapshot()
    assert snapshot['reserved_by_kind'] == {'fit': 1, 'semantic_live': 1}
    assert snapshot['reserved_semantic_questions'] == 3
    assert all(not research.paths[kind].exists() for kind in research.paths)


def test_existing_inner_cache_is_used_after_a_new_outer_catalog_path(tmp_path, catalog, response, monkeypatch):
    research, store = make_coordinator(tmp_path)
    with backend(response) as (endpoint, calls, _):
        research.semantic_live(store.path, record()['experiment_id'], catalog, digest_pin='d'*64, endpoint=endpoint)
    copied = tmp_path/'same-closed-records.sqlite'; copied.write_bytes(store.path.read_bytes())
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('inner cache must not execute'))
    second = research.semantic_live(copied, record()['experiment_id'], catalog, digest_pin='d'*64, endpoint=endpoint)
    assert not second['coordinator_cached'] and second['result']['semantic_cached'] and len(calls) == 4
    assert second['invocation_observed'] == ZERO_USAGE and second['invocation_resources']['tokens'] == ZERO_TOKENS
    assert research.budget.snapshot()['total_reserved_actions'] == 3


@pytest.mark.parametrize('mode', ['not_migrated', 'exhausted', 'invalid_input', 'cancelled'])
def test_common_or_input_admission_precedes_inner_and_http(tmp_path, catalog, response, monkeypatch, mode):
    policy = {**COMMON_POLICY, 'total_actions': 1} if mode == 'exhausted' else None
    research, store = make_coordinator(tmp_path, migrate=mode != 'not_migrated', policy=policy)
    monkeypatch.setattr(journal_module, 'run_worker', lambda *a, **k: pytest.fail('no HTTP or worker'))
    cancel = threading.Event()
    if mode == 'cancelled': cancel.set()
    with pytest.raises((ValueError, BudgetCancelled)):
        research.semantic_live(store.path, record()['experiment_id'], catalog,
            digest_pin='short' if mode == 'invalid_input' else 'd'*64, cancel_event=cancel)
    assert not (tmp_path/'live.sqlite').exists()


@pytest.mark.parametrize('mode,status', [('wrong_model', 'failed'), ('slow_headers', 'timed_out')])
def test_coordinator_failure_maps_to_both_journals_and_unknown_tokens(tmp_path, catalog, response, mode, status):
    research, store = make_coordinator(tmp_path)
    policy = {**journal_module.DEFAULT_POLICY, 'wall_seconds': 0.7}
    with backend(response, mode) as (endpoint, _, _):
        with pytest.raises((RuntimeError, BudgetTimedOut)):
            research.semantic_live(store.path, record()['experiment_id'], catalog,
                digest_pin='d'*64, endpoint=endpoint, request_policy=policy)
    snapshot = research.budget.snapshot()
    assert snapshot['statuses'] == {'completed': 1, status: 1}
    assert snapshot['resources']['unknown_token_actions_by_field']['input_tokens'] == 1
    with sqlite3.connect(tmp_path/'live.sqlite') as db:
        assert db.execute('SELECT status FROM local_semantic_requests').fetchone()[0] == status


def test_coordinator_http_cancellation_records_both_journals_and_reaps(tmp_path, catalog, response, monkeypatch):
    research, store = make_coordinator(tmp_path); cancel = threading.Event()
    processes, _ = capture(monkeypatch)
    with backend(response, 'slow_headers') as (endpoint, _, started):
        def cancel_started(): assert started.wait(timeout=3); cancel.set()
        thread = threading.Thread(target=cancel_started); thread.start()
        try:
            with pytest.raises(BudgetCancelled):
                research.semantic_live(store.path, record()['experiment_id'], catalog,
                    digest_pin='d'*64, endpoint=endpoint, cancel_event=cancel)
        finally: thread.join(timeout=1)
    assert processes and all(p.poll() is not None for p in processes)
    assert research.budget.snapshot()['statuses'] == {'completed': 1, 'cancelled': 1}
    with sqlite3.connect(tmp_path/'live.sqlite') as db:
        assert db.execute('SELECT status FROM local_semantic_requests').fetchone()[0] == 'cancelled'


def test_provider_usage_overrun_blocks_next_fresh_semantic_action(tmp_path, catalog, response):
    research, store = make_coordinator(tmp_path)
    with backend(response, 'usage_overrun') as (endpoint, _, _):
        research.semantic_live(store.path, record()['experiment_id'], catalog, digest_pin='d'*64, endpoint=endpoint)
        changed = deepcopy(catalog); changed['policy_version'] = 'another-version'
        with pytest.raises(ValueError, match='overrun'):
            research.semantic_live(store.path, record()['experiment_id'], changed, digest_pin='d'*64, endpoint=endpoint)
    assert research.budget.snapshot()['resources']['overrun_actions'] == 1


def test_cli_requires_migration_then_writes_private_local_semantic_receipt(tmp_path, catalog, response):
    research, store = make_coordinator(tmp_path)
    question_path, policy_path = tmp_path/'questions.json', tmp_path/'semantic-policy.json'
    question_path.write_text(canonical(catalog)); policy_path.write_text(canonical(DEFAULT_SEMANTIC_POLICY))
    output = tmp_path/'result.json'
    with backend(response) as (endpoint, calls, _):
        args = ['--database', str(research.budget.path), '--proposal-ledger', str(research.paths['proposal']),
            '--semantic-ledger', str(research.paths['semantic_fixture']), '--fit-ledger', str(research.paths['fit']),
            '--semantic-live-ledger', str(research.live_path), '--semantic-live-policy', str(policy_path),
            '--output', str(output), 'semantic-live', '--catalog-database', str(store.path),
            '--experiment-id', record()['experiment_id'], '--questions', str(question_path),
            '--model-digest', 'd'*64, '--endpoint', endpoint]
        assert coordinator.main(args) == 0
        count = len(calls)
        with pytest.raises(FileExistsError): coordinator.main(args)
        assert len(calls) == count == 4
    receipt = json.loads(output.read_text())
    assert receipt['status'] == 'completed' and receipt['call']['kind'] == 'semantic_live'
    assert receipt['call']['result']['origin'] == 'ollama_local_systemone'
    assert output.stat().st_mode & 0o777 == 0o600
