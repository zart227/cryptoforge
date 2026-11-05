from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.research_training_diagnostics import build_diagnostics, digest


def report(offset=0):
    return build_diagnostics({'partition': 'validation', 'dataset_sha256': str(offset)*64,
        'source_sha256': 'a'*64, 'development_end': '2025-01-02T00:00:00Z', 'rows': [
            {'pair': 'BTC/USDT', 'open_time': '2025-01-01T00:00:00Z',
             'label_end_time': '2025-01-01T00:01:00Z', 'probability': 0.5, 'label': 1}]})


class Advisor:
    provider = 'openrouter'
    model = 'fixed/model:free'
    parameters = ('l2', 'threshold')
    calls = 0
    def propose(self, diagnostics):
        self.calls += 1
        return {'report_sha256': digest(diagnostics), 'provider': self.provider, 'model': self.model,
            'proposal': {'schema_version': 'llm-training-proposal-v1', 'hypothesis_id': 'check-l2',
                'evidence_ids': ['overall'], 'parameter': 'l2', 'value': 0.1,
                'rationale': 'Check stability.', 'expected_effect': 'Lower loss.',
                'falsification': 'Reject if validation deteriorates.'}}


def test_exact_request_cached_across_instances_without_reusing_api(tmp_path):
    path = tmp_path/'api.sqlite'
    advisor = Advisor()
    a = ResearchRequests(path).propose(advisor, report())
    b = ResearchRequests(path).propose(advisor, report())
    assert advisor.calls == 1
    assert not a['api_cached'] and b['api_cached'] and a['request_key'] == b['request_key']
    assert path.stat().st_mode & 0o777 == 0o600


def test_daily_quota_counts_failed_requests_and_resets_on_utc_day(tmp_path):
    path = tmp_path/'api.sqlite'
    day = datetime(2025, 1, 1, tzinfo=timezone.utc)
    class Failing(Advisor):
        def propose(self, report):
            raise RuntimeError('private server response')
    with pytest.raises(RuntimeError):
        ResearchRequests(path, daily_maximum=1, clock=lambda: day).propose(Failing(), report())
    with pytest.raises(ValueError, match='quota exhausted'):
        ResearchRequests(path, daily_maximum=1, clock=lambda: day).propose(Advisor(), report(1))
    later = ResearchRequests(path, daily_maximum=1, clock=lambda: day+timedelta(days=1))
    assert not later.propose(Advisor(), report(1))['api_cached']
    with sqlite3.connect(path) as db:
        serialized = repr(db.execute('SELECT * FROM advisor_requests').fetchall())
    assert 'private server response' not in serialized


def test_quota_policy_cannot_change_on_restart(tmp_path):
    path = tmp_path/'api.sqlite'
    ResearchRequests(path, daily_maximum=1).propose(Advisor(), report())
    with pytest.raises(ValueError, match='cannot silently change'):
        ResearchRequests(path, daily_maximum=20).propose(Advisor(), report(1))


def test_failed_identical_request_not_retried_even_next_day(tmp_path):
    path = tmp_path/'api.sqlite'
    class Failing(Advisor):
        def propose(self, report):
            raise RuntimeError('failure')
    with pytest.raises(RuntimeError):
        ResearchRequests(path).propose(Failing(), report())
    with pytest.raises(ValueError, match='no automatic retry'):
        ResearchRequests(path).propose(Advisor(), report())


def test_concurrent_identical_request_has_single_owner(tmp_path):
    path = tmp_path/'api.sqlite'
    started, finish = threading.Event(), threading.Event()
    class Slow(Advisor):
        def propose(self, diagnostics):
            started.set()
            assert finish.wait(timeout=5)
            return super().propose(diagnostics)
    advisor = Slow()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(ResearchRequests(path).propose, advisor, report())
        assert started.wait(timeout=5)
        try:
            with pytest.raises(ValueError, match='interrupted API request'):
                ResearchRequests(path).propose(advisor, report())
        finally:
            finish.set()
        assert future.result(timeout=5)['api_cached'] is False
    assert advisor.calls == 1


def test_cached_advice_corruption_detected(tmp_path):
    path = tmp_path/'api.sqlite'
    ResearchRequests(path).propose(Advisor(), report())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE advisor_requests SET payload='{}'")
    with pytest.raises(ValueError, match='checksum mismatch'):
        ResearchRequests(path).propose(Advisor(), report())


def test_api_store_does_not_open_existing_training_ledger(tmp_path):
    path = tmp_path/'attempts.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE studies (id TEXT)')
    with pytest.raises(ValueError, match='separate isolated database'):
        ResearchRequests(path).propose(Advisor(), report())
