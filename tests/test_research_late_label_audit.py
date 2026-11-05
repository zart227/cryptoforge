"""Late targets cannot repair a prior decision's feature window or observation history."""
from copy import deepcopy
from datetime import timedelta
import gzip
import hashlib
import json
from pathlib import Path
import stat

import pytest
from test_research_local_cohort_audit import base
from cryptoforge import research_late_label_audit as m
from cryptoforge.training_diagnostics import canonical, digest, timestamp


@pytest.fixture(scope='module')
def scenario(base):
    plan, sources = deepcopy(base)
    late = deepcopy(sources[1]); late['client_observed_at'] = (timestamp(plan['label_information_end'])+timedelta(minutes=40)).isoformat()
    for source in sources:
        source['rows'] = [r for r in source['rows'] if timestamp(r['open_time']) < timestamp(plan['decision_anchor'])]
    return plan, sources, late


@pytest.fixture(scope='module')
def native_case(scenario, tmp_path_factory):
    plan, sources, late = scenario; original, selected = m.select(plan, sources, late)
    native = m._native(Path(plan['project']), {'plan': plan, 'selections': selected}, tmp_path_factory.mktemp('late-native'))
    return plan, sources, late, original, selected, native


def test_late_values_match_but_original_deadline_remains_unqualified(native_case):
    plan, _, _, original, selected, native = native_case
    result = m.compose({}, plan, original, selected, native)
    assert result['status'] == 'late_values_compatible_original_admission_remains_blocked'
    assert result['original_complete_label_horizons'] == 0 and result['late_values_checked_with_original_features'] == 2
    assert result['value_audit']['independent_feature_components'] == 14
    assert result['value_audit']['feature_component_mismatches'] == result['value_audit']['label_mismatch_samples'] == 0
    for key in ('original_deadline_status_changed', 'historical_availability_backdated', 'original_features_recovered_or_replaced',
                'training_data_admitted', 'model_fit_or_prediction_performed', 'provider_or_database_accessed_by_audit'):
        assert result[key] is False


def test_late_complete_source_cannot_recover_missing_original_feature(scenario):
    plan, sources, late = deepcopy(scenario); sources[0]['rows'].pop(119)
    original, selected = m.select(plan, sources, late)
    assert original[0]['features'] is selected[0]['features'] is None
    assert selected[0]['labels'] is not None and selected[0]['missing_feature_candles'] == 1
    assert original[1]['features'] == selected[1]['features']


def test_forming_late_label_stays_missing(scenario):
    plan, sources, late = deepcopy(scenario); late['rows'][122]['ingested_at'] = late['rows'][122]['open_time']
    _, selected = m.select(plan, sources, late)
    assert selected[0]['labels'] is None and selected[0]['missing_label_candles'] == 1


@pytest.mark.parametrize('delta', [-1, 0])
def test_on_time_source_cannot_be_mislabeled_as_late(scenario, delta):
    plan, sources, late = deepcopy(scenario); late['client_observed_at'] = (timestamp(plan['label_information_end'])+timedelta(seconds=delta)).isoformat()
    with pytest.raises(ValueError): m.select(plan, sources, late)


@pytest.mark.parametrize('change', [
    lambda s: s[0].update(features=None), lambda s: s[0].update(original_label_deadline_qualified_by_this_audit=True),
    lambda s: s[0].update(original_missing_label_candles=0), lambda s: s[0].update(pair='OTHER/USDT'),
    lambda s: s[0].update(late_label_available_at='2026-10-26T07:05:00+00:00'),
])
def test_original_feature_deadline_or_identity_repair_refused(native_case, change):
    plan, _, _, original, selected, native = deepcopy(native_case); change(selected)
    with pytest.raises(ValueError): m.compose({}, plan, original, selected, native)


def test_label_mismatch_is_recorded_not_hidden_as_success(native_case):
    plan, _, _, original, selected, native = deepcopy(native_case); native['values']['samples'][0]['long_label'] ^= 1
    report = m.compose({}, plan, original, selected, native)
    assert report['status'] == 'blocked' and report['value_audit']['label_mismatch_samples'] == 1


@pytest.fixture
def source_files(scenario, tmp_path, monkeypatch):
    plan, sources, late = deepcopy(scenario); plan['reviewed_main_profile'] = {}
    old = tmp_path/'original'; old.mkdir(mode=0o700); oldrun = old/'collection-run'; oldrun.mkdir(mode=0o700)
    write = m.cohort.values.files._write
    write(old, 'future-plan.json', plan); write(old, 'capture-freeze.json', {'worker_sha256': hashlib.sha256(b'worker').hexdigest(), 'original_journals': {}})
    for n in ('source-slot-0.json.gz', 'source-slot-1.json.gz', 'receipt-0.json', 'receipt-1.json', 'registration.json', 'complete.json'):
        write(oldrun, n, {'original': n})
    binding = {'directory': str(old), 'database_namespace': ['16384', '172.20.0.2', 5432, '16390']}
    monkeypatch.setattr(m.cohort, '_load', lambda p: (binding, plan, sources))
    directory = tmp_path/'late'; directory.mkdir(mode=0o700); run = directory/'collection-run'; run.mkdir(mode=0o700)
    observed = late['client_observed_at']; slot = (timestamp(observed)-timedelta(seconds=1)).isoformat()
    late_plan = {**plan, 'schema_version': 'late-local-primary-cohort-source-v1',
        'purpose': 'late_retrospective_label_value_compatibility_only_not_original_deadline_repair',
        'capture_slots': [slot], 'registered_at': (timestamp(slot)-timedelta(seconds=90)).isoformat(),
        'original_cohort_directory': str(old), 'maximum_capture_transactions': 1, 'original_M38_captures_consumed': 2,
        'metadata_only_preflight_transactions': 0, 'original_feature_windows_preserved': True,
        'original_deadline_status_may_change': False, 'new_model_fit_prediction_numeric_provider_allowances': False,
        'source_available_at_is_current_observation_only': True, 'original_information_end': plan['label_information_end'], 'round_trip_cost': '0.003'}
    plan['round_trip_cost'] = '0.003'
    late.update(slot_index=0, fixed_slot=slot, plan_sha256=digest(late_plan), read_completed_at=observed)
    late['database']['read_started_at'] = (timestamp(observed)-timedelta(seconds=1)).isoformat()
    write(directory, 'late-plan.json', late_plan)
    for n, content in (('capture-worker.py', b'worker'), ('collect-once.py', b'collector')):
        (directory/n).write_bytes(content); (directory/n).chmod(0o600)
    raw = (canonical(late)+'\n').encode(); packed = gzip.compress(raw, mtime=0)
    (run/'source-slot-0.json.gz').write_bytes(packed); (run/'source-slot-0.json.gz').chmod(0o600)
    receipt = {'raw_source_path': str(run/'source-slot-0.json.gz'), 'slot_index': 0, 'plan_sha256': digest(late_plan),
        'uncompressed_bytes': len(raw), 'compressed_bytes': len(packed), 'compressed_sha256': hashlib.sha256(packed).hexdigest(),
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'database_transactions': 1, 'HTTP_or_provider_requests': 0,
        'fit_model_prediction_or_budget_actions': 0, 'automatic_retry': False, 'source_mutated': False,
        'client_observed_at': observed, 'rows': len(late['rows']), 'rows_by_pair': late['rows_by_pair']}
    write(run, 'receipt-0.json', receipt)
    write(run, 'registration.json', {'plan_sha256': digest(late_plan), 'maximum_source_transactions': 1, 'old_captures_consumed': 2,
        'original_deadline_status_unchanged': True, 'registered_at': late_plan['registered_at']})
    write(run, 'complete.json', {'source_slots_completed': [0], 'source_transactions': 1, 'plan_sha256': digest(late_plan),
        'original_deadline_status_unchanged': True, 'model_fit_prediction_or_provider_actions': 0, 'automatic_retries': 0})
    oldpaths = [old/'future-plan.json', old/'capture-freeze.json', *sorted(oldrun.iterdir())]
    freeze = {'plan_file_sha256': m._sha(directory/'late-plan.json'), 'worker_sha256': m._sha(directory/'capture-worker.py'),
        'collector_sha256': m._sha(directory/'collect-once.py'), 'original_journals': {}, 'original_cohort_files': {str(p): m._sha(p) for p in oldpaths}}
    write(directory, 'capture-freeze.json', freeze)
    return directory, plan, sources, late


def test_single_late_source_load_checks_original_namespace_lineage_and_hashes(source_files):
    directory, plan, sources, late = source_files
    bound, p, original, got = m.load(directory)
    assert p == plan and original == sources and got == late
    assert bound['late_directory'] == str(directory)


@pytest.mark.parametrize('change', [
    lambda d: (d/'capture-worker.py').write_text('other'),
    lambda d: (d/'collection-run/source-slot-0.json.gz').write_bytes(b'changed'),
    lambda d: (d/'collection-run/complete.json').write_text('{}'),
    lambda d: (d/'late-plan.json').write_text('{}'),
])
def test_source_tampering_or_incomplete_slot_refused(source_files, change):
    directory, *_ = source_files; change(directory)
    with pytest.raises((ValueError, KeyError)): m.load(directory)


def test_offline_verify_never_reruns_native_worker(native_case, tmp_path, monkeypatch):
    plan, sources, late, _, _, native = native_case
    monkeypatch.setattr(m, 'load', lambda *_: ({'late_directory': str(tmp_path)}, plan, sources, late))
    monkeypatch.setattr(m, '_native', lambda *_: native)
    report = m.prepare(tmp_path/'pack', tmp_path)
    monkeypatch.setattr(m, '_native', lambda *_: pytest.fail('offline replay must not execute worker'))
    assert m.verify(tmp_path/'pack') == report
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in (tmp_path/'pack').iterdir())
    changed = json.loads((tmp_path/'pack/audit.json').read_text()); changed['training_data_admitted'] = True
    (tmp_path/'pack/audit.json').write_text(canonical(changed))
    with pytest.raises(ValueError): m.verify(tmp_path/'pack')


def test_policy_mutation_and_safe_missing_input_cli(tmp_path, capsys, monkeypatch):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-late-label-audit-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out
    monkeypatch.setitem(m.POLICY, 'training_admission_enabled', True)
    with pytest.raises(ValueError): m._guard()


@pytest.mark.parametrize('change', [
    lambda n: n.update(original_deadline_qualified=True),
    lambda n: n['late_cutoff_by_pair'].update({'AAA/USDT': '2026-10-26T07:05:00+00:00'}),
    lambda n: n['values'].update(model_prediction_performed=True),
])
def test_native_wrapper_cannot_claim_earlier_availability_or_prediction(native_case, change):
    plan, _, _, original, selected, native = deepcopy(native_case); change(native)
    with pytest.raises(ValueError): m.compose({}, plan, original, selected, native)


@pytest.mark.parametrize('change', [
    lambda s: s['database'].update(database_oid='99999'),
    lambda s: s.update(training_data_admitted=True),
    lambda s: s['rows_by_pair'].update({'AAA/USDT': 1}),
])
def test_rehashed_source_with_wrong_namespace_admission_or_counts_refused(source_files, change):
    directory, _, _, late = source_files; change(late)
    raw = canonical(late).encode(); packed = gzip.compress(raw, mtime=0); run = directory/'collection-run'
    (run/'source-slot-0.json.gz').write_bytes(packed)
    receipt = json.loads((run/'receipt-0.json').read_text())
    receipt.update(uncompressed_bytes=len(raw), compressed_bytes=len(packed), source_sha256=hashlib.sha256(raw).hexdigest(), compressed_sha256=hashlib.sha256(packed).hexdigest())
    (run/'receipt-0.json').write_text(canonical(receipt))
    with pytest.raises(ValueError): m.load(directory)


@pytest.mark.parametrize('interrupt', [False, True])
def test_late_worker_timeout_or_interrupt_kills_process_group_and_reaps(tmp_path, monkeypatch, interrupt):
    import subprocess
    observed = {}
    class Process:
        pid = 43210; calls = 0
        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                if interrupt: raise KeyboardInterrupt()
                raise subprocess.TimeoutExpired('fixed', 15)
            return 0
    process = Process()
    monkeypatch.setattr(m.subprocess, 'Popen', lambda a, **kw: observed.update(args=a, **kw) or process)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: observed.update(killed=pid))
    with pytest.raises(KeyboardInterrupt if interrupt else subprocess.TimeoutExpired): m._native(Path('/tmp'), {'selections': []}, tmp_path)
    assert observed['killed'] == 43210 and process.calls == 2 and observed['start_new_session']
    assert Path(observed['args'][2]).name == 'research_late_label_value_worker.py'
    assert set(observed['env']) == {'PATH', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONHASHSEED', 'LANG', 'TZ'}
