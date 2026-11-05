from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from test_llm_research_requests import Advisor, report
from cryptoforge import llm_provider_worker as worker
from cryptoforge import llm_research_coordinator as coordinator
from cryptoforge.llm_research_advisor import FreeAdvisor, AdvisorUnavailable, AdvisorCancelled, AdvisorTimedOut, DEFAULT_MODEL
from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.research_resource_budget import DEFAULT_RESOURCES
from cryptoforge.research_run_budget import BudgetCancelled, BudgetTimedOut
from cryptoforge.training_diagnostics import canonical


@pytest.fixture(autouse=True)
def synthetic_key_only(monkeypatch):
    monkeypatch.setenv('CRYPTOFORGE_OPENROUTER_API_KEY', 'synthetic-test-key')


@contextmanager
def local_provider(mode='success'):
    started, stop = threading.Event(), threading.Event(); calls = []
    proposal = Advisor().propose(report())['proposal']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append({'path': self.path, 'data': data, 'authorization': self.headers.get('Authorization')})
            started.set()
            if mode == 'slow_headers': stop.wait(3)
            if mode == 'redirect':
                self.send_response(302); self.send_header('Location', 'https://unrequested.example'); self.end_headers(); return
            body = canonical({'model': 'local-model', 'done': True, 'done_reason': 'stop',
                'message': {'content': canonical(proposal)}, 'prompt_eval_count': 12, 'eval_count': 3}).encode()
            if mode == 'bad_json': body = b'{invalid private body'
            self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
            try:
                if mode == 'slow_drip':
                    for byte in body:
                        self.wfile.write(bytes([byte])); self.wfile.flush()
                        if stop.wait(0.02): break
                else: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True); thread.start()
    try:
        yield FreeAdvisor(provider='ollama', model='local-model', ollama_url=f'http://127.0.0.1:{server.server_port}',
                          parameters=('l2', 'threshold')), started, calls
    finally:
        stop.set(); server.shutdown(); server.server_close(); thread.join(timeout=1)


def capture_processes(monkeypatch):
    processes, invocations = [], []; real = subprocess.Popen
    def launch(*args, **kwargs):
        invocations.append((args, kwargs)); process = real(*args, **kwargs); processes.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    return processes, invocations


def test_real_loopback_worker_has_minimal_env_private_stdin_and_reaped_process(monkeypatch):
    monkeypatch.setenv('UNRELATED_SECRET', 'must-not-be-inherited')
    processes, invocations = capture_processes(monkeypatch)
    with local_provider() as (advisor, started, calls):
        result = worker.run_provider_worker(advisor, report(), wall_seconds=3, api_key='synthetic-private-key')
    assert result['proposal']['parameter'] == 'l2'
    assert result['usage'] == {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15}
    assert not result['provider_execution']['server_cancellation_verified']
    assert calls[0]['path'] == '/api/chat' and calls[0]['authorization'] is None
    assert calls[0]['data']['options']['num_predict'] == 2048
    args, kwargs = invocations[0]
    assert 'synthetic-private-key' not in repr(args)+repr(kwargs['env'])
    assert 'UNRELATED_SECRET' not in kwargs['env'] and 'OPENROUTER_API_KEY' not in kwargs['env']
    assert kwargs['stderr'] == subprocess.DEVNULL and kwargs['start_new_session']
    assert all(process.poll() is not None and process.stdin.closed for process in processes)


@pytest.mark.parametrize('mode', ['slow_headers', 'slow_drip'])
def test_one_deadline_stops_slow_headers_or_continuously_dripping_socket(monkeypatch, mode):
    processes, _ = capture_processes(monkeypatch)
    with local_provider(mode) as (advisor, started, calls):
        before = time.monotonic()
        with pytest.raises(AdvisorTimedOut): worker.run_provider_worker(advisor, report(), wall_seconds=0.6)
        elapsed = time.monotonic()-before
        assert started.is_set() and len(calls) == 1
        assert 0.4 <= elapsed < 2
    assert processes and all(process.poll() is not None for process in processes)


def test_cancellation_during_http_kills_and_reaps_worker(monkeypatch):
    processes, _ = capture_processes(monkeypatch); cancel = threading.Event()
    with local_provider('slow_headers') as (advisor, started, _):
        def cancel_after_request():
            assert started.wait(timeout=2); cancel.set()
        thread = threading.Thread(target=cancel_after_request); thread.start()
        with pytest.raises(AdvisorCancelled):
            worker.run_provider_worker(advisor, report(), wall_seconds=3, cancel_event=cancel)
        thread.join(timeout=1)
    assert all(process.poll() is not None for process in processes)


@pytest.mark.parametrize('mode', ['redirect', 'bad_json'])
def test_bad_response_or_redirect_is_sanitized_without_retry(mode):
    with local_provider(mode) as (advisor, _, calls):
        with pytest.raises(AdvisorUnavailable) as error: worker.run_provider_worker(advisor, report(), wall_seconds=3)
        assert len(calls) == 1 and 'private body' not in str(error.value)


def test_pre_cancellation_never_launches_worker_or_creates_common_journal(tmp_path, monkeypatch):
    cancel = threading.Event(); cancel.set()
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(AdvisorCancelled): worker.run_provider_worker(FreeAdvisor(), report(), wall_seconds=1, cancel_event=cancel)
    research = coordinator.ResearchCoordinator(tmp_path/'common.sqlite', proposal_ledger=tmp_path/'api.sqlite',
        semantic_ledger=tmp_path/'semantic.sqlite', fit_ledger=tmp_path/'fit.sqlite')
    with pytest.raises(BudgetCancelled): research.propose(report(), provider='openrouter', cancel_event=cancel,
        jobpilot_env=tmp_path/'nonexistent.env')
    assert not list(tmp_path.glob('*.sqlite'))


def test_inner_cache_does_not_launch_or_read_missing_credentials(tmp_path, monkeypatch):
    with local_provider() as (advisor, _, calls):
        first = ResearchRequests(tmp_path/'api.sqlite').propose(advisor, report(),
            execute=lambda: worker.run_provider_worker(advisor, report(), wall_seconds=3))
        monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('cache must not launch'))
        second = ResearchRequests(tmp_path/'api.sqlite').propose(advisor, report(),
            execute=lambda: worker.run_provider_worker(advisor, report(), wall_seconds=3, jobpilot_env=tmp_path/'missing'))
        assert second['api_cached'] and len(calls) == 1
        assert first['request_key'] == second['request_key']


@pytest.mark.parametrize('error,status', [(AdvisorTimedOut, 'timed_out'), (AdvisorCancelled, 'cancelled'), (KeyboardInterrupt, 'cancelled')])
def test_terminal_inner_status_keeps_identity_across_new_day_and_executor(tmp_path, error, status):
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    def fail(): raise error('private provider details')
    with pytest.raises((AdvisorTimedOut, AdvisorCancelled)):
        ResearchRequests(tmp_path/'api.sqlite', clock=lambda: now).propose(Advisor(), report(), execute=fail)
    with sqlite3.connect(tmp_path/'api.sqlite') as db:
        assert db.execute('SELECT status FROM advisor_requests').fetchone()[0] == status
        assert 'private provider details' not in repr(db.execute('SELECT * FROM advisor_requests').fetchall())
    with pytest.raises(ValueError, match='no automatic retry'):
        ResearchRequests(tmp_path/'api.sqlite', clock=lambda: now+timedelta(days=1)).propose(Advisor(), report(),
            execute=lambda: pytest.fail('must not repeat'))


def test_actual_provider_timeout_charges_both_ledgers_and_preserves_unknown_tokens(tmp_path):
    policy = {**DEFAULT_RESOURCES, 'wall_ms_by_kind': {**DEFAULT_RESOURCES['wall_ms_by_kind'], 'proposal': 600}}
    with local_provider('slow_headers') as (advisor, _, calls):
        research = coordinator.ResearchCoordinator(tmp_path/'common.sqlite', proposal_ledger=tmp_path/'api.sqlite',
            semantic_ledger=tmp_path/'semantic.sqlite', fit_ledger=tmp_path/'fit.sqlite', resource_policy=policy)
        with pytest.raises(BudgetTimedOut): research.propose(report(), provider='ollama', model=advisor.model, ollama_url=advisor.ollama_url)
        snapshot = research.budget.snapshot()
        assert snapshot['statuses'] == {'timed_out': 1}
        assert snapshot['resources']['unknown_token_actions_by_field']['input_tokens'] == 1
        assert snapshot['resources']['reserved_allocations']['wall_ms'] == 600
        with sqlite3.connect(tmp_path/'api.sqlite') as db:
            assert db.execute('SELECT status FROM advisor_requests').fetchone()[0] == 'timed_out'
        with pytest.raises(ValueError, match='no automatic retry'):
            research.propose(report(), provider='ollama', model=advisor.model, ollama_url=advisor.ollama_url)
        fresh = coordinator.ResearchCoordinator(tmp_path/'other-common.sqlite', proposal_ledger=tmp_path/'api.sqlite',
            semantic_ledger=tmp_path/'semantic.sqlite', fit_ledger=tmp_path/'fit.sqlite')
        with pytest.raises(RuntimeError): fresh.propose(report(), provider='ollama', model=advisor.model, ollama_url=advisor.ollama_url)
        assert len(calls) == 1


@pytest.mark.parametrize('wall', [True, 0, -1, 66, float('nan')])
def test_invalid_deadline_is_rejected_before_launch(wall, monkeypatch):
    monkeypatch.setattr(worker.subprocess, 'Popen', lambda *a, **k: pytest.fail('must not launch'))
    with pytest.raises(ValueError): worker.run_provider_worker(FreeAdvisor(), report(), wall_seconds=wall)


def test_custom_python_transport_cannot_enter_fixed_worker():
    with pytest.raises(ValueError, match='without custom transport'):
        worker.run_provider_worker(FreeAdvisor(transport=lambda *a: {}), report(), wall_seconds=1)


@pytest.mark.parametrize('program', ["raise SystemExit(7)",
    "import sys; sys.stdin.buffer.read(); sys.stdout.write('{private malformed answer')",
    "import sys; sys.stdin.buffer.read(); sys.stdout.write('x'*512001)"])
def test_failed_malformed_or_oversized_worker_is_reaped_and_sanitized(monkeypatch, program):
    real = subprocess.Popen; processes = []
    def launch(*args, **kwargs):
        process = real([sys.executable, '-c', program], **kwargs); processes.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    with pytest.raises(AdvisorUnavailable) as error:
        worker.run_provider_worker(FreeAdvisor(), report(), wall_seconds=3)
    assert 'private malformed answer' not in str(error.value)
    assert all(process.poll() is not None for process in processes)


def test_keyboard_interrupt_during_communicate_still_kills_and_reaps(monkeypatch):
    real = subprocess.Popen; processes = []
    def launch(*args, **kwargs):
        process = real([sys.executable, '-c', 'import time; time.sleep(10)'], **kwargs)
        original = process.communicate; count = 0
        def communicate(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 1: raise KeyboardInterrupt()
            return original(*args, **kwargs)
        process.communicate = communicate; processes.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    with pytest.raises(AdvisorCancelled): worker.run_provider_worker(FreeAdvisor(), report(), wall_seconds=3)
    assert all(process.poll() is not None for process in processes)


def test_worker_self_alarm_overrides_ignored_signal_without_supervisor_timeout():
    import signal
    program = '''import signal,time
from cryptoforge import llm_provider_worker as m
from cryptoforge.llm_research_advisor import FreeAdvisor as Real
signal.signal(signal.SIGALRM,signal.SIG_IGN)
def stall(*args,**kwargs): time.sleep(3)
m.FreeAdvisor=lambda **kwargs:Real(**kwargs,transport=stall)
raise SystemExit(m.worker_main())
'''
    data = {'report': report(), 'wall_seconds': 0.2, 'implementation': worker._LOADED,
        'settings': {'provider': 'ollama', 'model': 'local-model', 'ollama_url': 'http://127.0.0.1:11434',
            'parameters': ['l2', 'threshold'], 'timeout': 1, 'api_key': None, 'jobpilot_env': None}}
    completed = subprocess.run([sys.executable, '-c', program], input=canonical(data).encode(),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
        env={'PYTHONPATH': str(Path(worker.__file__).resolve().parents[1]), 'PYTHONDONTWRITEBYTECODE': '1'})
    assert completed.returncode == -signal.SIGALRM


def test_cancellation_during_http_records_both_journals(tmp_path):
    cancel = threading.Event()
    with local_provider('slow_headers') as (advisor, started, calls):
        research = coordinator.ResearchCoordinator(tmp_path/'common.sqlite', proposal_ledger=tmp_path/'api.sqlite',
            semantic_ledger=tmp_path/'semantic.sqlite', fit_ledger=tmp_path/'fit.sqlite')
        def stop_after_request():
            assert started.wait(timeout=2); cancel.set()
        thread = threading.Thread(target=stop_after_request); thread.start()
        with pytest.raises(BudgetCancelled):
            research.propose(report(), provider='ollama', model=advisor.model, ollama_url=advisor.ollama_url, cancel_event=cancel)
        thread.join(timeout=1)
        assert research.budget.snapshot()['statuses'] == {'cancelled': 1}
        with sqlite3.connect(tmp_path/'api.sqlite') as db:
            assert db.execute('SELECT status FROM advisor_requests').fetchone()[0] == 'cancelled'
        assert len(calls) == 1


def test_cli_local_timeout_writes_terminal_receipt(tmp_path):
    from test_llm_training_study import inputs
    from cryptoforge.training_experiment_planner import freeze_protocol, run_experiment
    dataset, _ = inputs(tmp_path); protocol = freeze_protocol(dataset, version='deadline-cli-synthetic', epochs=3)
    baseline = run_experiment(dataset, protocol, tmp_path/'fit.sqlite')
    evidence = tmp_path/'baseline.json'; evidence.write_text(canonical({'status': 'completed', 'command': 'run', 'result': baseline}))
    policy = {**DEFAULT_RESOURCES, 'wall_ms_by_kind': {**DEFAULT_RESOURCES['wall_ms_by_kind'], 'proposal': 600}}
    config = tmp_path/'resource-policy.json'; config.write_text(canonical(policy))
    output = tmp_path/'timeout.json'
    with local_provider('slow_drip') as (advisor, _, calls):
        code = coordinator.main(['--database', str(tmp_path/'common.sqlite'), '--proposal-ledger', str(tmp_path/'api.sqlite'),
            '--semantic-ledger', str(tmp_path/'semantic.sqlite'), '--fit-ledger', str(tmp_path/'fit.sqlite'),
            '--resource-policy', str(config), '--output', str(output), 'proposal', '--experiment-receipt', str(evidence),
            '--provider', 'ollama', '--model', advisor.model, '--ollama-url', advisor.ollama_url])
        assert code == 1 and len(calls) == 1
    assert json.loads(output.read_text())['status'] == 'timed_out'
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('catalog_delay,completion_delay,wall,expected_calls', [(0.8, 0, 0.4, ['catalog']), (0.4, 0.8, 0.9, ['catalog', 'completion'])])
def test_synthetic_openrouter_catalog_and_post_share_one_process_deadline(tmp_path, monkeypatch, catalog_delay, completion_delay, wall, expected_calls):
    # Test-only launcher replaces the transport in a child, never a production input.
    marker = tmp_path/'calls.txt'; real = subprocess.Popen; processes = []
    code = f'''import time
from pathlib import Path
from cryptoforge import llm_provider_worker as m
from cryptoforge.llm_research_advisor import FreeAdvisor as Real
def transport(url, *args, **kwargs):
    phase = 'catalog' if url.endswith('/models') else 'completion'
    with Path({str(marker)!r}).open('a') as stream: stream.write(phase+'\\n')
    time.sleep({catalog_delay!r} if phase=='catalog' else {completion_delay!r})
    if phase=='catalog': return {{'data':[{{'id':{DEFAULT_MODEL!r},'pricing':{{'prompt':'0','completion':'0'}}}}]}}
    raise RuntimeError('test never needs a completed answer')
m.FreeAdvisor=lambda **kwargs:Real(**kwargs,transport=transport)
raise SystemExit(m.worker_main())
'''
    def launch(*args, **kwargs):
        process = real([sys.executable, '-c', code], **kwargs); processes.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', launch)
    with pytest.raises(AdvisorTimedOut):
        worker.run_provider_worker(FreeAdvisor(api_key='synthetic-key'), report(), wall_seconds=wall)
    assert marker.read_text().splitlines() == expected_calls
    assert all(process.poll() is not None for process in processes)
