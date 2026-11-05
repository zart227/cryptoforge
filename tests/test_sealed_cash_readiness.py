from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from test_live_learning_protocol import START, protocol, ready_rows, row
from cryptoforge.local_source_provenance import canonical, digest
from cryptoforge.sealed_cash_readiness import guarded_cash_readiness, bounded_available_experiences


def test_unfinished_windows_do_not_invoke_any_payload_loader():
    def poison(*args):
        pytest.fail('unfinished or holdout outcome payload was read')
    result = guarded_cash_readiness(protocol(), as_of=START+timedelta(days=20), load_split=poison)
    assert result['status'] == 'calendar_only_no_outcome_payloads_read'
    assert result['inspected_splits'] == []
    assert all(s['counts'] is None and s['outcomes_hidden'] for s in result['splits'].values())
    assert result['data_ready_for_offline_fit'] is False


def test_train_opens_at_exact_end_but_validation_remains_unread():
    calls = []
    def load(split, cutoff):
        calls.append((split, cutoff))
        assert split == 'train'
        return ready_rows()['train']
    result = guarded_cash_readiness(protocol(), as_of=START+timedelta(days=28), load_split=load)
    assert result['inspected_splits'] == ['train']
    assert result['splits']['train']['counts']['buy_orders'] == 2
    assert result['splits']['validation']['counts'] is None
    assert calls[0][1] == START+timedelta(days=28)-timedelta(seconds=protocol()['embargo_seconds'])
    assert not result['data_ready_for_offline_fit']


def test_completed_development_windows_use_original_readiness_rules_and_never_holdout():
    calls = []
    def load(split, cutoff):
        calls.append(split)
        return ready_rows()[split]
    result = guarded_cash_readiness(protocol(), as_of=START+timedelta(days=100), load_split=load, source_healthy=True)
    assert calls == ['train', 'validation']
    assert result['data_ready_for_offline_fit'] is True
    assert result['sealed_test_data_ready'] is False
    assert result['splits']['sealed_test']['counts'] is None
    assert result['splits']['paper']['counts'] is None
    assert not result['automatic_training_allowed'] and not result['live_promotion_allowed']


def test_calendar_alone_cannot_qualify_collection_or_make_candidate_ready():
    result = guarded_cash_readiness(protocol(), as_of=START+timedelta(days=43), load_split=lambda s, c: ready_rows()[s])
    assert not result['data_ready_for_offline_fit']
    assert 'unverified_stale_or_incomplete_collection_snapshot' in result['blocked_reasons']
    with pytest.raises(ValueError):
        guarded_cash_readiness(protocol(), as_of=START, load_split=lambda *a: [], source_healthy=1)


def store(path, values):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE experience_versions (id INTEGER PRIMARY KEY,target TEXT,pair TEXT,entry_order TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        for v in values:
            db.execute('INSERT INTO experience_versions VALUES (NULL,?,?,?,?,?,?)',
                (v['target_version'], v['pair'], v['entry_order'], digest(canonical(v)), v['label_available_at'], canonical(v).decode()))
    return path


def read(path, **changes):
    return bounded_available_experiences(path, target=protocol()['target_version'], as_of=START+timedelta(days=28), **changes)


def test_original_snapshot_keeps_latest_available_version_and_withdrawal_without_mutation(tmp_path):
    a = row('a', 2)
    revision = dict(a, label_available_at=(START+timedelta(days=3)).isoformat(), example=dict(a['example'], label=1))
    b = row('b', 3)
    withdrawal = dict(b, eligible=False, label_available_at=(START+timedelta(days=4)).isoformat())
    future = row('c', 30)
    path = store(tmp_path/'memory.sqlite', [a, revision, b, withdrawal, future])
    before = path.read_bytes()
    assert read(path) == [revision]
    assert path.read_bytes() == before
    missing = tmp_path/'missing.sqlite'
    assert read(missing) == [] and not missing.exists()


@pytest.mark.parametrize('change', ['versions', 'bytes', 'oversize_row', 'duplicate_json', 'metadata', 'typed_eligible'])
def test_bounded_snapshot_rejects_bad_or_excess_payloads(tmp_path, change):
    values = [row('a', 2), row('b', 3)]
    if change == 'oversize_row':
        values[0]['padding'] = 'x'*262144
    elif change == 'bytes':
        values[0]['padding'] = 'x'*1200
    elif change == 'typed_eligible':
        values[0]['eligible'] = 1
    path = store(tmp_path/'memory.sqlite', values)
    if change in ('duplicate_json', 'metadata'):
        with sqlite3.connect(path) as db:
            if change == 'duplicate_json':
                db.execute('UPDATE experience_versions SET payload=? WHERE id=1', ('{"pair":"AAA/USDT","pair":"AAA/USDT"}',))
            else:
                db.execute('UPDATE experience_versions SET pair=? WHERE id=1', ('OTHER/USDT',))
    kwargs = dict(maximum_versions=1) if change == 'versions' else dict(maximum_bytes=1024) if change == 'bytes' else {}
    before = path.read_bytes()
    with pytest.raises(ValueError):
        read(path, **kwargs)
    assert path.read_bytes() == before


def test_original_store_aliases_and_sidecars_are_not_adopted(tmp_path):
    path = store(tmp_path/'memory.sqlite', [row('a', 2)])
    link = tmp_path/'alias.sqlite'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='canonical'):
        read(link)
    journal = Path(str(path)+'-journal')
    journal.write_bytes(b'uncertain')
    with pytest.raises(ValueError, match='sidecar'):
        read(path)
    assert journal.read_bytes() == b'uncertain'


def test_calendar_cli_does_not_read_primary_memory_or_publish_a_readiness_gate(tmp_path):
    from datetime import UTC, datetime
    from test_live_learning_protocol import SPLITS
    p = protocol()
    now = datetime.now(UTC)
    p['frozen_at'] = now.isoformat()
    for split, start, end in zip(SPLITS, (0,28,42,70), (28,42,70,98)):
        p['windows'][split] = dict(start=(now+timedelta(days=start)).isoformat(), end_exclusive=(now+timedelta(days=end)).isoformat())
    path = tmp_path/'protocol.json'
    raw = canonical(p)
    path.write_bytes(raw)
    path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    command = [sys.executable, 'scripts/check_sealed_cash_readiness.py', '--protocol', str(path), '--output', str(tmp_path/'preflight')]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt['inspected_splits'] == []
    report = json.loads((tmp_path/'preflight/preflight.json').read_bytes())
    assert report['source_health_qualified'] is False
    assert report['data_ready_for_offline_fit'] is False
    assert receipt['report_sha256'] == digest(canonical(report))
    bad = subprocess.run(command+['--as-of', '2027-01-01'], capture_output=True, text=True)
    assert bad.returncode == 2
    bad = subprocess.run([sys.executable, 'scripts/check_sealed_cash_readiness.py', '--output', str(tmp_path/'no-protocol')], capture_output=True, text=True)
    assert bad.returncode == 2


def test_unobserved_past_protocol_never_opens_original_memory(tmp_path, monkeypatch):
    import importlib.util
    from types import SimpleNamespace
    spec = importlib.util.spec_from_file_location('safe_cash_cli', Path('scripts/check_sealed_cash_readiness.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'load_cash_study', lambda _: (protocol(), SimpleNamespace(protocol_sha256='a'*64)))
    def not_frozen(*a):
        raise ValueError('no original freeze')
    monkeypatch.setattr(module, 'require_collection_freeze', not_frozen)
    def poison(*a, **k):
        pytest.fail('unobserved protocol opened primary memory')
    monkeypatch.setattr(module, 'bounded_available_experiences', poison)
    with pytest.raises(ValueError, match='unobserved protocol'):
        module.main(['--protocol', str(tmp_path/'unused.json'), '--output', str(tmp_path/'unused-output')])
    assert not (tmp_path/'unused-output').exists()
