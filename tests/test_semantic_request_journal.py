import copy
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_typesafe_sdk_bridge import catalog, sdk_request, response
from cryptoforge import semantic_request_journal as module
from cryptoforge.typesafe_sdk_bridge import evaluate_fixture
from cryptoforge.training_diagnostics import canonical


def policy(**overrides):
    return {**module.DEFAULT_POLICY, **overrides}


def changed_fixture(response, i=1):
    result = copy.deepcopy(response)
    result['usage']['input_tokens'] = i
    return result


@pytest.fixture
def fast_worker(monkeypatch):
    calls = []
    def run(request, fixture, **kwargs):
        calls.append(request['request_sha256'])
        return evaluate_fixture(request, fixture)
    monkeypatch.setattr(module, 'run_worker', run)
    return calls


def test_real_bounded_worker_and_cache_survive_restart(tmp_path, sdk_request, response, monkeypatch):
    path = tmp_path/'semantic.sqlite'
    spawned = []
    popen = module.subprocess.Popen
    def capture(*args, **kwargs):
        assert set(kwargs['env']) == {'PATH', 'LANG', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE'}
        child = popen(*args, **kwargs)
        spawned.append(child)
        return child
    monkeypatch.setattr(module.subprocess, 'Popen', capture)
    first = module.SemanticRequests(path).evaluate(sdk_request, response)
    assert not first['semantic_cached'] and first['api_calls'] == 0
    assert first['sdk_compatible_answer_count'] == 3
    assert len(spawned) == 1 and spawned[0].poll() == 0
    def forbidden(*args, **kwargs): raise AssertionError('cache must not spawn another worker')
    monkeypatch.setattr(module, 'run_worker', forbidden)
    repeat = module.SemanticRequests(path).evaluate(sdk_request, response)
    assert repeat['semantic_cached'] and repeat['semantic_request_key'] == first['semantic_request_key']
    assert module.SemanticRequests(path).snapshot()['total_requests'] == 1
    assert path.stat().st_mode & 0o777 == 0o600


def test_daily_and_total_quotas_count_questions_and_allow_cached_results(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    start = datetime(2025, 1, 1, 22, tzinfo=timezone(timedelta(hours=-3)))
    limits = policy(daily_requests=1, total_requests=2)
    first = module.SemanticRequests(path, policy=limits, clock=lambda: start)
    first.evaluate(sdk_request, response)
    assert first.snapshot()['utc_day'] == '2025-01-02'
    assert first.snapshot()['daily_questions'] == 3
    with pytest.raises(ValueError, match='request quota'):
        first.evaluate(sdk_request, changed_fixture(response))
    assert first.evaluate(sdk_request, response)['semantic_cached']
    second = module.SemanticRequests(path, policy=limits, clock=lambda: start+timedelta(days=1))
    second.evaluate(sdk_request, changed_fixture(response))
    third = module.SemanticRequests(path, policy=limits, clock=lambda: start+timedelta(days=2))
    with pytest.raises(ValueError, match='request quota'):
        third.evaluate(sdk_request, changed_fixture(response, 2))
    assert third.snapshot()['total_questions'] == 6 and len(fast_worker) == 2


@pytest.mark.parametrize('limits', [policy(daily_questions=2), policy(total_questions=2)])
def test_question_quota_is_reserved_for_whole_batch_before_execution(tmp_path, sdk_request, response, fast_worker, limits):
    journal = module.SemanticRequests(tmp_path/'semantic.sqlite', policy=limits)
    with pytest.raises(ValueError, match='question quota'): journal.evaluate(sdk_request, response)
    assert journal.snapshot()['total_requests'] == 0 and fast_worker == []
    with pytest.raises(ValueError, match='cannot silently change'):
        module.SemanticRequests(journal.path).evaluate(sdk_request, response)


def test_policy_cannot_expand_or_shrink_after_initialization(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    module.SemanticRequests(path).evaluate(sdk_request, response)
    for limits in (policy(daily_requests=21), policy(wall_seconds=10)):
        with pytest.raises(ValueError, match='cannot silently change'):
            module.SemanticRequests(path, policy=limits).evaluate(sdk_request, response)
    assert len(fast_worker) == 1


def test_failed_attempt_counts_and_cannot_auto_retry_or_leak_error_text(tmp_path, sdk_request, response, monkeypatch):
    path = tmp_path/'semantic.sqlite'
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    def fail(*args, **kwargs): raise RuntimeError('private provider body or key')
    monkeypatch.setattr(module, 'run_worker', fail)
    journal = module.SemanticRequests(path, policy=policy(daily_requests=1), clock=lambda: start)
    with pytest.raises(RuntimeError, match='details are not logged'): journal.evaluate(sdk_request, response)
    assert journal.snapshot()['statuses'] == {'failed': 1}
    assert journal.snapshot()['total_questions'] == 3
    with pytest.raises(ValueError, match='request quota'): journal.evaluate(sdk_request, changed_fixture(response))
    later = module.SemanticRequests(path, policy=policy(daily_requests=1), clock=lambda: start+timedelta(days=1))
    with pytest.raises(ValueError, match='no automatic retry'): later.evaluate(sdk_request, response)
    with sqlite3.connect(path) as db:
        saved = repr(db.execute('SELECT * FROM semantic_requests').fetchall())
    assert 'private provider body or key' not in saved


def test_pre_cancelled_request_does_not_create_journal(tmp_path, sdk_request, response, fast_worker):
    cancel = threading.Event(); cancel.set()
    path = tmp_path/'new'/'semantic.sqlite'
    with pytest.raises(module.RequestCancelled, match='before reservation'):
        module.SemanticRequests(path).evaluate(sdk_request, response, cancel_event=cancel)
    assert not path.parent.exists() and not fast_worker


def test_real_child_is_reaped_when_cancelled_after_reservation(tmp_path, sdk_request, response, monkeypatch):
    cancel = threading.Event()
    children = []
    popen = module.subprocess.Popen
    def start(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child); cancel.set()
        return child
    monkeypatch.setattr(module.subprocess, 'Popen', start)
    journal = module.SemanticRequests(tmp_path/'semantic.sqlite')
    with pytest.raises(module.RequestCancelled): journal.evaluate(sdk_request, response, cancel_event=cancel)
    assert children and children[0].poll() is not None
    assert journal.snapshot()['statuses'] == {'cancelled': 1}
    assert journal.snapshot()['total_questions'] == 3
    with pytest.raises(ValueError, match='no automatic retry'): journal.evaluate(sdk_request, response)


def test_real_worker_wall_timeout_is_persistent(tmp_path, sdk_request, response):
    journal = module.SemanticRequests(tmp_path/'semantic.sqlite', policy=policy(wall_seconds=0.01))
    with pytest.raises(module.RequestTimedOut): journal.evaluate(sdk_request, response)
    assert journal.snapshot()['statuses'] == {'timed_out': 1}
    with pytest.raises(ValueError, match='no automatic retry'): journal.evaluate(sdk_request, response)


def test_keyboard_interrupt_stops_child_and_records_cancellation(tmp_path, sdk_request, response, monkeypatch):
    children = []
    popen = module.subprocess.Popen
    def interrupt(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        communicate = child.communicate
        count = [0]
        def wrapped(*args, **kwargs):
            count[0] += 1
            if count[0] == 1: raise KeyboardInterrupt
            return communicate(*args, **kwargs)
        child.communicate = wrapped
        return child
    monkeypatch.setattr(module.subprocess, 'Popen', interrupt)
    journal = module.SemanticRequests(tmp_path/'semantic.sqlite')
    with pytest.raises(module.RequestCancelled): journal.evaluate(sdk_request, response)
    assert children[0].poll() is not None
    assert journal.snapshot()['statuses'] == {'cancelled': 1}


def test_crash_leaves_reserved_attempt_without_automatic_takeover(tmp_path, sdk_request, response, monkeypatch):
    def crash(*args, **kwargs): raise SystemExit(99)
    monkeypatch.setattr(module, 'run_worker', crash)
    path = tmp_path/'semantic.sqlite'
    with pytest.raises(SystemExit): module.SemanticRequests(path).evaluate(sdk_request, response)
    restarted = module.SemanticRequests(path)
    assert restarted.snapshot()['statuses'] == {'reserved': 1}
    with pytest.raises(ValueError, match='no automatic retry'): restarted.evaluate(sdk_request, response)


def test_concurrent_identical_request_has_one_owner(tmp_path, sdk_request, response, monkeypatch):
    path = tmp_path/'semantic.sqlite'
    started, finish = threading.Event(), threading.Event()
    def slow(request, fixture, **kwargs):
        started.set()
        assert finish.wait(timeout=5)
        return evaluate_fixture(request, fixture)
    monkeypatch.setattr(module, 'run_worker', slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(module.SemanticRequests(path).evaluate, sdk_request, response)
        assert started.wait(timeout=5)
        try:
            with pytest.raises(ValueError, match='interrupted fixture'):
                module.SemanticRequests(path).evaluate(sdk_request, response)
        finally:
            finish.set()
        assert not future.result(timeout=5)['semantic_cached']
    assert module.SemanticRequests(path).snapshot()['total_requests'] == 1


def test_cached_result_tampering_is_not_executed_again(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    journal = module.SemanticRequests(path)
    journal.evaluate(sdk_request, response)
    with sqlite3.connect(path) as db: db.execute("UPDATE semantic_requests SET payload='{}'")
    with pytest.raises(ValueError, match='checksum'): journal.evaluate(sdk_request, response)
    assert len(fast_worker) == 1


def test_concurrent_different_requests_cannot_share_last_budget_slot(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    barrier = threading.Barrier(2)
    def attempt(fixture):
        barrier.wait(timeout=5)
        try:
            module.SemanticRequests(path, policy=policy(daily_requests=1)).evaluate(sdk_request, fixture)
            return 'completed'
        except ValueError as error:
            assert 'request quota exhausted' in str(error)
            return 'quota_rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, fixture) for fixture in (response, changed_fixture(response))]
        assert sorted(f.result(timeout=5) for f in futures) == ['completed', 'quota_rejected']
    assert len(fast_worker) == 1
    assert module.SemanticRequests(path, policy=policy(daily_requests=1)).snapshot()['total_requests'] == 1


def test_bad_request_is_rejected_before_reservation(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    sdk_request['state']['injected'] = 'Changed evidence.'
    with pytest.raises(ValueError, match='changed before reservation'):
        module.SemanticRequests(path).evaluate(sdk_request, response)
    assert not path.exists() and not fast_worker


def test_invalid_worker_output_is_failure_not_a_negative_label(tmp_path, sdk_request, response, monkeypatch):
    monkeypatch.setattr(module, 'run_worker', lambda *args, **kwargs: {'api_calls': 1})
    journal = module.SemanticRequests(tmp_path/'semantic.sqlite')
    with pytest.raises(RuntimeError): journal.evaluate(sdk_request, response)
    assert journal.snapshot()['statuses'] == {'failed': 1}
    with sqlite3.connect(journal.path) as db:
        assert db.execute('SELECT payload FROM semantic_requests').fetchone()[0] is None


def test_real_worker_rejection_counts_failure(tmp_path, sdk_request, response):
    response['model'] = 'another-model'
    journal = module.SemanticRequests(tmp_path/'semantic.sqlite')
    with pytest.raises(RuntimeError): journal.evaluate(sdk_request, response)
    assert journal.snapshot()['statuses'] == {'failed': 1}


def test_budget_snapshot_is_read_only_and_never_initializes_missing_database(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    with pytest.raises(ValueError, match='existing'): module.SemanticRequests(path).snapshot()
    assert not path.exists()
    journal = module.SemanticRequests(path); journal.evaluate(sdk_request, response)
    before = path.read_bytes(); snapshot = journal.snapshot()
    assert path.read_bytes() == before
    assert snapshot['api_calls'] == 0 and not snapshot['includes_external_proposer_or_fit']


def test_foreign_database_content_and_permissions_unchanged(tmp_path, sdk_request, response):
    path = tmp_path/'attempts.sqlite'
    with sqlite3.connect(path) as db: db.execute('CREATE TABLE studies (id TEXT)')
    path.chmod(0o640); before = path.read_bytes()
    with pytest.raises(ValueError, match='separate isolated'):
        module.SemanticRequests(path).evaluate(sdk_request, response)
    assert path.read_bytes() == before and path.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize('change', [{'daily_requests': True}, {'total_questions': 0}, {'wall_seconds': 31}, {'daily_questions': '3'}])
def test_invalid_budget_policies_fail_before_database_creation(tmp_path, change):
    path = tmp_path/'semantic.sqlite'
    with pytest.raises(ValueError): module.SemanticRequests(path, policy=policy(**change))
    assert not path.exists()


def test_naive_clock_and_oversized_fixture_do_not_reserve(tmp_path, sdk_request, response, fast_worker):
    path = tmp_path/'semantic.sqlite'
    with pytest.raises(ValueError, match='aware'):
        module.SemanticRequests(path, clock=lambda: datetime(2025, 1, 1)).evaluate(sdk_request, response)
    response['large'] = 'x'*64000
    with pytest.raises(ValueError, match='too large'): module.SemanticRequests(path).evaluate(sdk_request, response)
    assert not path.exists() and not fast_worker


def test_cli_private_receipt_no_overwrite_and_cached_budget(tmp_path, sdk_request, response, fast_worker):
    request_path, response_path, first_path, repeat_path = [tmp_path/name for name in ('request.json','fixture.json','first.json','repeat.json')]
    request_path.write_text(canonical(sdk_request)); response_path.write_text(canonical(response))
    common = ['--request',str(request_path),'--response',str(response_path),'--database',str(tmp_path/'semantic.sqlite')]
    assert module.main([*common,'--output',str(first_path)]) == 0
    assert module.main([*common,'--output',str(repeat_path)]) == 0
    repeat = json.loads(repeat_path.read_text())
    assert repeat['result']['semantic_cached'] and repeat['budget']['total_requests'] == 1
    assert first_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): module.main([*common,'--output',str(first_path)])
    assert len(fast_worker) == 1
