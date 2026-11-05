from datetime import timedelta
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from test_local_source_provenance import example, NOW
from cryptoforge.local_source_observer import query_sql
from cryptoforge.local_source_provenance import canonical, digest
from cryptoforge.reference_aware_feeder import build_plan, run_cycle, bounded_stage, MAX_ADDRESS_SPACE

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(CRYPTOFORGE_BACKEND='local', CRYPTOFORGE_LOCAL_API_KEY='never-print-this-secret')


def observation(pair, stale=False):
    result = example()
    source = json.loads(result['raw_response'])
    seed = json.loads(source['rows'][0]['raw_json'])
    rows = []
    for i in range(120):
        at = NOW-timedelta(minutes=(120-i)*5, days=1 if stale else 0)
        value = dict(seed, id=f'00000000-0000-0000-0000-{i+1:012d}', pair=pair,
            symbol=pair.replace('/',''), open_time=at.isoformat(), close_time=(at+timedelta(minutes=5)).isoformat())
        rows.append(dict(source['rows'][0], raw_json=json.dumps(value)))
    source['rows'] = rows
    result['raw_response'] = json.dumps(source)
    result['query'] = dict(pair=pair, timeframe='5m', limit=120)
    result['query_sha256'] = digest(query_sql(pair, '5m', 120, NOW).encode())
    return result


def setup(tmp_path, monkeypatch):
    # Runtime is pinned to real source files; all side effects are confined to
    # injected stage/provider functions and a temporary per-test lease.
    import cryptoforge.reference_aware_feeder as m
    from contextlib import contextmanager
    @contextmanager
    def lease(root):
        yield
    monkeypatch.setattr(m, '_lease', lease)
    monkeypatch.setattr(m, '_cooldown_path', lambda root:tmp_path.with_suffix('.cooldown.json'))
    universe = ROOT/'.local/state/test-reference-feeder-universe.json'
    plan = build_plan(ROOT, universe)
    monkeypatch.setattr(m, 'build_plan', lambda *a: plan)
    original_read = m.read_file
    monkeypatch.setattr(m, 'read_file', lambda path, **kwargs:
        canonical(dict(pairs=['SOL/USDT'])) if Path(path) == universe else original_read(path, **kwargs))
    calls = []
    def invoke(argv, env, root):
        calls.append(argv)
        if '--pair' in argv:
            return 0, ('synced_pairs='+argv[argv.index('--pair')+1]+'\n').encode()
        if 'select_live_universe.py' in argv[1]:
            return 0, b'pairs=SOL/USDT\n'
        return 0, b'synced_pairs=SOL/USDT\n'
    return plan, calls, invoke


def test_plan_is_btc_eth_first_and_never_adds_benchmarks_to_trading_ranking():
    plan = build_plan(ROOT, ROOT/'.local/state/live-universe.json')
    assert [s['name'] for s in plan['stages']] == ['reference_btc','reference_eth','select','selected_sync']
    for stage, pair in zip(plan['stages'], ('BTC/USDT','ETH/USDT')):
        assert stage['argv'][stage['argv'].index('--pair')+1] == pair
        assert stage['argv'][stage['argv'].index('--candle-limit')+1] == '121'
    assert '--live-config' not in plan['stages'][2]['argv']
    assert plan['maximum_child_address_space_bytes'] == 512*1024**2


def test_reference_refresh_then_selection_with_fixed_snapshot_and_exact_receipts(tmp_path, monkeypatch):
    plan, calls, invoke = setup(tmp_path, monkeypatch)
    result = run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=observation)
    assert result['success'] and result['reference_refresh_verified']
    assert len(calls) == 4
    assert calls[-1][calls[-1].index('--live-config')+1] == str(tmp_path/'selected-universe.json')
    assert 'never-print-this-secret' not in json.dumps(result)
    assert all(result[k] is False for k in ('paper_evidence_pass','live_admission_granted','full_worker_or_host_qualified'))


@pytest.mark.parametrize('fault', ['nonzero','partial_success','stale','wrong_pair','probe_failure'])
def test_failed_btc_never_suppresses_eth_refresh_or_runs_selection(tmp_path, monkeypatch, fault):
    plan, calls, original = setup(tmp_path, monkeypatch)
    def invoke(argv, env, root):
        result = original(argv, env, root)
        if 'BTC/USDT' in argv:
            if fault == 'nonzero':
                return 1, b'failed={"BTC/USDT":"unavailable"}\n'
            if fault == 'partial_success':
                return 0, b'synced_pairs=BTC/USDT\nfailed={}\n'
        return result
    def probe(pair):
        if pair == 'BTC/USDT':
            if fault == 'probe_failure':
                raise ValueError('do not serialize exception details or secrets')
            if fault == 'wrong_pair':
                return observation('OTHER/USDT')
        return observation(pair, stale=fault == 'stale' and pair == 'BTC/USDT')
    result = run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=probe)
    assert len(calls) == 2 and 'ETH/USDT' in calls[1]
    assert not result['success'] and not result['reference_refresh_verified']
    assert result['stages'][1]['success'] is True


def test_mixed_local_instances_block_dynamic_selection(tmp_path, monkeypatch):
    plan, calls, invoke = setup(tmp_path, monkeypatch)
    def probe(pair):
        value = observation(pair)
        if pair == 'ETH/USDT':
            source = json.loads(value['raw_response']);source['system_identifier'] = '7500123412341234124'
            value['raw_response'] = json.dumps(source)
        return value
    assert not run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=probe)['success']
    assert len(calls) == 2


def test_old_selected_sync_partial_success_exit_zero_is_not_health_success(tmp_path, monkeypatch):
    plan, calls, original = setup(tmp_path, monkeypatch)
    def invoke(argv, env, root):
        code, raw = original(argv, env, root)
        if '--live-config' in argv:
            return 0, b'synced_pairs=SOL/USDT\nfailed={"OTHER/USDT":"timeout"}\n'
        return code, raw
    result = run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=observation)
    assert result['reference_refresh_verified'] is True and result['success'] is False


def test_cloud_backend_rejected_before_any_stage_or_probe(tmp_path, monkeypatch):
    plan, calls, invoke = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='local backend'):
        run_cycle(plan, tmp_path, env=dict(CRYPTOFORGE_BACKEND='supabase',SUPABASE_URL='https://example.supabase.co',SUPABASE_SERVICE_ROLE_KEY='test'), invoke=invoke, observe=observation)
    assert calls == []


def test_real_child_address_space_cap_and_private_failure_output(tmp_path):
    code, raw = bounded_stage([sys.executable,'-c','import resource;print(resource.getrlimit(resource.RLIMIT_AS)[0])'], dict(os.environ), tmp_path)
    assert code == 0 and int(raw) == MAX_ADDRESS_SPACE


@pytest.mark.parametrize('fault', ['bytes','timeout'])
def test_real_child_caps_kill_the_process_group(tmp_path, monkeypatch, fault):
    import cryptoforge.reference_aware_feeder as m
    monkeypatch.setattr(m, 'MAX_STAGE_SECONDS', .3)
    command = 'print("x"*70000)' if fault == 'bytes' else 'import time;time.sleep(10)'
    with pytest.raises(ValueError, match='budget exhausted'):
        bounded_stage([sys.executable,'-c',command], dict(os.environ), tmp_path)


def test_default_cli_only_plans_without_keys_or_primary_writes(tmp_path):
    command = [sys.executable,'scripts/run_reference_aware_feeder.py','--output',str(tmp_path/'plan')]
    result = subprocess.run(command, capture_output=True, text=True,
        env={k:v for k,v in os.environ.items() if k not in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','CRYPTOFORGE_LOCAL_API_KEY')})
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['primary_database_write_attempted'] is False
    assert report['status'] == 'plan_only_no_network_or_database_access'


def test_used_output_root_is_rejected_before_repeating_any_write(tmp_path, monkeypatch):
    plan, calls, invoke = setup(tmp_path, monkeypatch)
    (tmp_path/'stage-1.json').write_bytes(b'old receipt')
    with pytest.raises(ValueError, match='no silent resume'):
        run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=observation)
    assert calls == []


def test_disk_reserve_is_enforced_before_child_writes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    plan, calls, invoke = setup(tmp_path, monkeypatch)
    monkeypatch.setattr('cryptoforge.reference_aware_feeder.shutil.disk_usage', lambda _:SimpleNamespace(free=2048*1024**2))
    with pytest.raises(ValueError, match='disk reserve'):
        run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=observation)
    assert calls == []


def test_venue_rate_limit_stops_eth_and_persists_cooldown_across_cycles(tmp_path, monkeypatch):
    import cryptoforge.reference_aware_feeder as m
    plan, calls, original = setup(tmp_path, monkeypatch)
    # Keep the original bounded file reader for cooldown, while universe remains
    # a deterministic injected source in this test.
    monkeypatch.setattr(m, 'read_file', lambda p, **kw:p.read_bytes())
    def invoke(argv, env, root):
        calls.append(argv)
        return 1, b'failed={"BTC/USDT":"Bybit request was rate-limited: HTTP 429"}\n'
    first = run_cycle(plan, tmp_path, env=ENV, invoke=invoke, observe=observation)
    assert len(calls) == 1 and first['venue_cooldown']
    next_root = tmp_path/'next'
    next_root.mkdir()
    second = run_cycle(plan, next_root, env=ENV, invoke=invoke, observe=observation)
    assert len(calls) == 1 and second['stages'] == []
    assert second['primary_database_write_attempted'] is False
    assert not second['success']
