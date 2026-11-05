"""Future local-cache versions remain tied to their original decision availability."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import stat
import subprocess

import pytest
from cryptoforge import research_local_cohort_audit as m
from cryptoforge.research_training_diagnostics import canonical, digest


@pytest.fixture(scope='module')
def base():
    anchor = datetime(2026, 10, 26, 6, 45, tzinfo=timezone.utc)
    plan = {'project': '/home/arthur/Projects/personal/CryptoForge', 'pairs': ['AAA/USDT', 'BBB/USDT'], 'decision_anchor': anchor.isoformat(),
        'decision_time': (anchor+timedelta(minutes=2)).isoformat(),
        'label_end_time': (anchor+timedelta(minutes=15)).isoformat(),
        'label_information_end': (anchor+timedelta(minutes=20)).isoformat(), 'min_label_return': '0.003',
        'capture_slots': [(anchor+timedelta(minutes=t)).isoformat() for t in (1, 16)]}
    sources = []
    for slot in (0, 1):
        observed = anchor+timedelta(minutes=(1, 16)[slot]); rows = []
        for pair_index, pair in enumerate(plan['pairs']):
            for j in range(120+(3 if slot else 0)):
                opened = anchor+timedelta(minutes=5*(j-120)); closed = opened+timedelta(minutes=5)
                close = '103' if j == 122 else '101'
                row = {'id': '00000000-0000-0000-0000-'+f'{int(opened.timestamp())//300+pair_index*10000:012d}',
                    'exchange': 'bybit', 'market_type': 'spot', 'symbol': pair.replace('/', ''), 'pair': pair, 'timeframe': '5m',
                    'open_time': opened.isoformat(), 'close_time': closed.isoformat(), 'open': '100', 'high': '104',
                    'low': '99', 'close': close, 'volume': '10', 'turnover': '1000', 'source': 'bybit_public_api',
                    'ingested_at': observed.isoformat(), 'created_at': opened.isoformat(), 'updated_at': observed.isoformat(),
                    'storage_xmin': str(100+slot)}
                row['observed_revision_sha256'] = digest(row); rows.append(row)
        source = {'schema_version': 'local-primary-cohort-observation-v1', 'slot_index': slot, 'plan_sha256': digest(plan),
            'fixed_slot': plan['capture_slots'][slot], 'pairs': plan['pairs'],
            'source_kind': 'local_cache_version_observed_at_client_completion', 'historical_first_seen_backdated': False,
            'training_data_admitted': False, 'production_reader_equivalence_claimed': False, 'model_fit_prediction_provider_operations': 0,
            'table_oid': '16390', 'rows': rows, 'rows_by_pair': {p: len(rows)//2 for p in plan['pairs']},
            'client_observed_at': observed.isoformat(), 'read_completed_at': (observed-timedelta(milliseconds=100)).isoformat(),
            'database': {'database': 'cryptoforge', 'login': 'authenticator', 'role': 'service_role', 'server_version_num': '170010',
                'read_only': 'on', 'isolation': 'repeatable read', 'statement_timeout': '3s', 'lock_timeout': '250ms',
                'idle_timeout': '5s', 'login_superuser': False, 'database_oid': '16384', 'server_address': '172.20.0.2',
                'server_port': 5432, 'snapshot': '3000:3000:', 'read_started_at': (observed-timedelta(milliseconds=300)).isoformat()},
            'columns': [{'name': n, 'type': t, 'not_null': True} for n, t in m.values.private.COLUMNS.items()],
            'unique_keys': [{'columns': m.values.private.KEY}]}
        sources.append(source)
    return plan, sources


@pytest.fixture(scope='module')
def native_base(base, tmp_path_factory):
    plan, sources = base; selections = m.select(plan, sources)
    packet = {'plan': plan, 'selections': selections}
    native = m._native(Path('/home/arthur/Projects/personal/CryptoForge'), packet, tmp_path_factory.mktemp('local-native'))
    return plan, sources, selections, native


def test_original_closed_source_and_complete_native_independent_values_match(native_base):
    plan, sources, selected, native = native_base
    for slot, source in enumerate(sources): assert m.validate_source(plan, source, slot) is source
    report = m.compose({}, plan, selected, native)
    assert report['status'] == 'all_declared_local_samples_compatible'
    assert report['independent_feature_components'] == 14 and report['independent_label_windows'] == 2
    assert report['feature_component_mismatches'] == report['label_mismatch_samples'] == 0
    assert report['native_selected_rows_read'] == 246
    assert selected[0]['later_feature_physical_revision_changes'] == 120
    assert selected[0]['later_feature_value_changes'] == 0
    assert not report['actual_production_reader_invoked'] and not report['training_data_admitted']


def test_later_recovered_feature_is_never_borrowed_from_label_snapshot(base):
    plan, sources = deepcopy(base); sources[0]['rows'].pop(119)
    selected = m.select(plan, sources)
    assert selected[0]['features'] is None and selected[0]['missing_feature_candles'] == 1
    assert selected[0]['feature_candles_only_observed_later'] == 1
    assert selected[0]['late_recovered_features_used'] is False
    assert selected[1]['features'] is not None


def test_delivered_but_forming_at_ingestion_is_not_a_known_closed_label(base):
    plan, sources = deepcopy(base); row = sources[1]['rows'][122]
    row['ingested_at'] = row['open_time']
    selected = m.select(plan, sources)
    assert selected[0]['labels'] is None and selected[0]['missing_label_candles'] == 1
    assert selected[0]['label_row_delivery'] == {'not_delivered': 0, 'delivered_but_not_known_closed': 1}


def test_capture_after_fixed_decision_cannot_supply_earlier_features(base):
    plan, sources = deepcopy(base); sources[0]['client_observed_at'] = plan['label_information_end']
    selected = m.select(plan, sources)
    assert all(s['features'] is None and s['missing_feature_candles'] == 120 for s in selected)


def test_economic_and_physical_revisions_are_kept_separate(base):
    plan, sources = deepcopy(base); row = sources[1]['rows'][0]; row['volume'] = '11'
    row['observed_revision_sha256'] = digest({k: v for k, v in row.items() if k != 'observed_revision_sha256'})
    selected = m.select(plan, sources)
    assert selected[0]['later_feature_physical_revision_changes'] == 120
    assert selected[0]['later_feature_value_changes'] == 1


@pytest.mark.parametrize('change', [
    lambda s: s['rows'][0].update(close='102'), lambda s: s.update(plan_sha256='a'*64),
    lambda s: s.update(slot_index=True), lambda s: s.update(training_data_admitted=True),
    lambda s: s['rows_by_pair'].update({'AAA/USDT': 1}),
    lambda s: s['database'].update(read_only='off'), lambda s: s.update(table_oid='bad'),
])
def test_source_scope_hash_namespace_clock_or_counts_tampering_refused(base, change):
    plan, sources = deepcopy(base); change(sources[0])
    with pytest.raises(ValueError): m.validate_source(plan, sources[0], 0)


@pytest.mark.parametrize('change', [
    lambda n: n.update(packet_sha256='a'*64), lambda n: n.update(fit_performed=True),
    lambda n: n.update(actual_production_reader_invoked=True), lambda n: n.update(source_rows_read=True),
    lambda n: n['samples'][0].update(long_label=True), lambda n: n['samples'][0].update(pair='UNKNOWN/USDT'),
])
def test_native_result_cannot_change_scope_identity_or_accounting(native_base, change):
    plan, _, selected, native = deepcopy(native_base); change(native)
    with pytest.raises(ValueError): m.compose({}, plan, selected, native)


def test_one_ulp_feature_change_or_label_change_remains_recorded_failure(native_base):
    plan, _, selected, native = deepcopy(native_base)
    native['samples'][0]['feature_hex'][0] = math.nextafter(float.fromhex(native['samples'][0]['feature_hex'][0]), math.inf).hex()
    native['samples'][0]['long_label'] = 0
    report = m.compose({}, plan, selected, native)
    assert report['status'] == 'blocked' and report['feature_component_mismatches'] == 1 and report['label_mismatch_samples'] == 1


def test_missing_features_and_labels_stay_null_without_native_calculation(base, tmp_path):
    plan, sources = deepcopy(base); sources[0]['rows'] = []
    selected = m.select(plan, sources)
    native = m._native(Path('/home/arthur/Projects/personal/CryptoForge'), {'plan': plan, 'selections': selected}, tmp_path)
    report = m.compose({}, plan, selected, native)
    assert report['independent_feature_components'] == report['independent_label_windows'] == report['native_selected_rows_read'] == 0
    assert report['status'] == 'blocked'
    native['samples'][0]['feature_hex'] = ['0x0.0p+0']*7
    with pytest.raises(ValueError): m.compose({}, plan, selected, native)


def test_private_pack_offline_verify_does_not_rerun_native_worker(native_base, tmp_path, monkeypatch):
    plan, sources, _, native = native_base
    bound = ({'directory': str(tmp_path/'input')}, plan, sources)
    monkeypatch.setattr(m, '_load', lambda *_: bound); monkeypatch.setattr(m, '_native', lambda *_: native)
    result = m.prepare(tmp_path/'pack', tmp_path/'input')
    monkeypatch.setattr(m, '_native', lambda *_: pytest.fail('verify must not invoke native worker'))
    assert m.verify(tmp_path/'pack') == result
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in (tmp_path/'pack').iterdir())
    changed = json.loads((tmp_path/'pack/audit.json').read_text()); changed['late_recovered_features_used'] = True
    changed['audit_sha256'] = digest({k: v for k, v in changed.items() if k != 'audit_sha256'})
    (tmp_path/'pack/audit.json').write_text(canonical(changed))
    with pytest.raises(ValueError): m.verify(tmp_path/'pack')


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('fixed', 15), KeyboardInterrupt()])
def test_fixed_worker_timeout_interrupt_and_process_group_cleanup(tmp_path, monkeypatch, failure):
    observed = {}
    class Process:
        pid = 54321; calls = 0
        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1: raise failure
            return 0
    process = Process()
    monkeypatch.setattr(m.subprocess, 'Popen', lambda args, **kw: observed.update(args=args, **kw) or process)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: observed.update(killed=pid))
    with pytest.raises(type(failure)): m._native(Path('/tmp'), {'plan': {}, 'selections': []}, tmp_path)
    assert process.calls == 2 and observed['killed'] == 54321 and observed['start_new_session']
    assert set(observed['env']) == {'PATH', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONHASHSEED', 'LANG', 'TZ'}


def test_frozen_policy_and_safe_missing_capture_cli(tmp_path, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-local-cohort-audit-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out
