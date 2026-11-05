"""Independent endpoint lineage detects self-consistent but false native labels."""
from copy import deepcopy
from decimal import localcontext
import json
import math
from pathlib import Path
import stat
import subprocess

import pytest
from cryptoforge import research_label_oracle as m
from cryptoforge import research_label_reference_worker as ref
from cryptoforge.research_training_diagnostics import canonical, digest
from test_research_revision_bridge import native_fixture
from test_research_value_audit import value_base


@pytest.mark.parametrize('future,threshold,expected', [
    ('100', '0', (0, 0)), ('101', '0', (1, 0)), ('99', '0', (0, 1)),
    ('100.3', '0.003', (0, 0)), ('99.7', '0.003', (0, 0)),
    ('100.30000000000001', '0.003', (1, 0)), ('99.69999999999999', '0.003', (0, 1)),
])
def test_exact_rational_return_and_strict_binary64_boundary(future, threshold, expected):
    result = ref.labels('100', future, threshold)
    assert (result['long_label'], result['short_label']) == expected
    with localcontext() as context:
        context.prec = 2
        assert ref.labels('100', future, threshold) == result


@pytest.mark.parametrize('threshold', ['NaN', '0.1001', '-0', '1e-3', '00.01', '0.0000000000001', 0, True])
def test_unsupported_thresholds_refused(threshold):
    with pytest.raises(ValueError): ref.labels('100', '101', threshold)


@pytest.fixture(scope='module')
def label_base(value_base, tmp_path_factory):
    _, _, binding, source, selection, native = value_base
    directory = tmp_path_factory.mktemp('label-native-pack')/'pack'; directory.mkdir(mode=0o700)
    report = m.values.compose(binding, source, selection, m.values.TARGET, native)
    for name, value in (('policy.json', m.values.POLICY), ('binding.json', binding), ('selection.json', selection),
        ('target.json', m.values.TARGET), ('native.json', native), ('audit.json', report)):
        m.values.files._write(directory, name, value)
    bound = m.bind(directory)
    oracle = m._worker(bound[1], bound[2], bound[5], tmp_path_factory.mktemp('label-worker'))
    return directory, bound, oracle


def test_original_endpoint_replay_and_explicit_partial_scope(label_base):
    _, bound, oracle = label_base; report = m.compose(*bound, oracle)
    assert report['status'] == 'available_labels_match' and report['mismatch_samples'] == 0
    assert report['label_windows_checked'] == 4 and report['source_rows_read'] == 16
    assert report['endpoint_values_checked'] == report['binary_labels_checked'] == 8
    assert report['all_samples_have_label_comparisons']
    for key in ('training_data_admitted', 'native_values_rerun', 'provider_called', 'fit_performed',
        'model_prediction_performed', 'candidate_numeric_worker_executed', 'target_parameters_approved',
        'production_promotion_authorized', 'statistical_validation_complete', 'current_future_holdout_status_verified'):
        assert report[key] is False


def test_consistent_fabricated_native_endpoints_are_detected_against_original_source(label_base):
    _, bound, oracle = label_base; changed = list(deepcopy(bound))
    for native in changed[3]['samples']:
        native.update(reference_close='100', future_close='102', future_return_hex=float(.02).hex(), long_label=1, short_label=0)
    # Earlier arithmetic comparison alone accepts these internally consistent native endpoints.
    report = m.values.compose(changed[0], changed[1], changed[2], changed[5], changed[3])
    assert report['numeric_mismatch_samples'] == 0
    result = m.compose(*changed, oracle)
    assert result['mismatch_samples'] == 4 and result['status'] == 'blocked'
    assert not result['samples'][0]['comparisons']['future_close']['exact_match']


def test_one_ulp_native_return_change_is_a_failure_without_tolerance(label_base):
    _, bound, oracle = label_base; changed = list(deepcopy(bound))
    original = float.fromhex(changed[3]['samples'][0]['future_return_hex'])
    changed[3]['samples'][0]['future_return_hex'] = math.nextafter(original, math.inf).hex()
    assert m.compose(*changed, oracle)['mismatch_samples'] == 1


@pytest.mark.parametrize('change', [
    lambda v: v.update(reference_sha256='a'*64), lambda v: v.update(target_sha256='a'*64),
    lambda v: v.update(selection_sha256='a'*64), lambda v: v.update(specification_sha256='a'*64),
    lambda v: v.update(source_rows_read=True), lambda v: v.update(network_request_performed=True),
    lambda v: v.update(trainer_or_runtime_imported=True), lambda v: v['samples'].pop(),
    lambda v: v['samples'][0].update(id=True), lambda v: v['samples'][0].update(selected_raw_sha256='a'*64),
    lambda v: v['samples'][0]['values'].update(long_label=True),
    lambda v: v['samples'][0]['values'].update(exact_return_denominator='0'),
])
def test_fixed_result_contract_refuses_tampering(label_base, change):
    _, bound, oracle = label_base; oracle = deepcopy(oracle); change(oracle)
    with pytest.raises(ValueError): m.compose(*bound, oracle)


@pytest.mark.parametrize('group,index,field,value', [
    ('features', -1, 'known_at', '2026-10-23T00:00:00Z'),
    ('labels', 0, 'known_at', '2026-10-23T00:00:00Z'),
    ('labels', 1, 'revision_sha256', 'a'*64), ('labels', 2, 'symbol', 'ETHUSDT'),
    ('labels', 1, 'open_time', '2026-10-22T10:06:00Z'),
    ('labels', 0, 'close_time', '2026-10-22T10:06:00Z'),
    ('labels', 0, 'observed_at', '2026-10-22T10:00:00Z'),
])
def test_original_reader_rejects_endpoint_or_middle_horizon_lineage_change(label_base, tmp_path, group, index, field, value):
    _, bound, _ = label_base; selected = deepcopy(bound[2]); selected[0][group][index][field] = value
    with pytest.raises(ValueError, match='independent_label_worker_refused'):
        m._worker(bound[1], selected, bound[5], tmp_path)


def test_original_source_checksum_required(label_base, tmp_path):
    _, bound, _ = label_base
    with pytest.raises(ValueError, match='independent_label_worker_refused'):
        m._worker({**bound[1], 'database_sha256': 'a'*64}, bound[2], bound[5], tmp_path)


@pytest.mark.parametrize('missing', ['features', 'labels'])
def test_missing_sources_remain_null_and_partial(label_base, tmp_path, missing):
    _, bound, _ = label_base; changed = list(deepcopy(bound)); changed[2][0][missing] = None
    oracle = m._worker(changed[1], changed[2], changed[5], tmp_path)
    result = m.compose(*changed, oracle)
    assert result['label_windows_checked'] == 3 and result['source_rows_read'] == 12
    assert not result['all_samples_have_label_comparisons']
    assert result['samples'][0]['comparisons'] is None
    oracle['samples'][0]['values'] = {}
    with pytest.raises(ValueError, match='missing_label_source'): m.compose(*changed, oracle)


def test_private_pack_verify_replays_only_independent_worker_and_rejects_rehashed_promotion(label_base, tmp_path, monkeypatch):
    directory, _, _ = label_base; pack = tmp_path/'pack'; result = m.prepare(pack, directory)
    monkeypatch.setattr(m.values, '_native', lambda *_: pytest.fail('native functions must not rerun'))
    assert m.verify(pack) == result
    assert stat.S_IMODE(pack.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in pack.iterdir())
    with pytest.raises(ValueError, match='new_label_oracle'): m.prepare(pack, directory)
    forged = json.loads((pack/'audit.json').read_text()); forged['training_data_admitted'] = True
    forged['audit_sha256'] = digest({k: v for k, v in forged.items() if k != 'audit_sha256'})
    (pack/'audit.json').write_text(canonical(forged))
    with pytest.raises(ValueError, match='label_oracle_audit_changed'): m.verify(pack)


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('fixed', 15), KeyboardInterrupt()])
def test_worker_deadline_interrupt_cleared_env_and_cleanup(label_base, tmp_path, monkeypatch, failure):
    observed = {}
    class Process:
        pid = 32101; calls = 0
        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1: raise failure
            return 0
    process = Process()
    def popen(args, **kwargs): observed.update(args=args, **kwargs); return process
    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: observed.update(killed=pid))
    _, bound, _ = label_base
    with pytest.raises(type(failure)): m._worker(bound[1], bound[2], bound[5], tmp_path)
    assert process.calls == 2 and observed['killed'] == 32101
    assert observed['stdin'] == subprocess.DEVNULL and observed['start_new_session']
    assert set(observed['env']) == {'PATH', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONHASHSEED', 'LANG', 'TZ'}


def test_frozen_configs_and_safe_cli_refusal(tmp_path, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-label-oracle-v1.json').read_text()) == m.POLICY
    assert json.loads((root/'config/research-label-reference-v1.json').read_text()) == ref.SPEC
    assert m.main(['verify', '--directory', str(tmp_path/'private-secret')]) == 2
    assert 'private-secret' not in capsys.readouterr().out
