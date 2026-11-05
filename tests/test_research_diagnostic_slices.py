"""Descriptive prediction slices preserve boundaries, denominators and nulls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat

import pytest

from cryptoforge import research_diagnostic_slices as m


@pytest.fixture
def protocol():
    return {'schema_version': 'research-diagnostic-slices-protocol-v1',
        'analysis_kind': 'descriptive_development_only', 'decision_threshold': .5,
        'pairs': ['BTC/USDT', 'ETH/USDT'],
        'partitions': {'train': {'start': '2026-10-20T10:00:00Z', 'end': '2026-10-20T10:20:00Z'},
                       'validation': {'start': '2026-10-20T10:30:00Z', 'end': '2026-10-20T10:50:00Z'}},
        'windows': [{'id': 'train_first', 'partition': 'train', 'start': '2026-10-20T10:00:00Z', 'end': '2026-10-20T10:10:00Z'},
                    {'id': 'train_second', 'partition': 'train', 'start': '2026-10-20T10:10:00Z', 'end': '2026-10-20T10:20:00Z'},
                    {'id': 'validation_first', 'partition': 'validation', 'start': '2026-10-20T10:30:00Z', 'end': '2026-10-20T10:40:00Z'},
                    {'id': 'validation_second', 'partition': 'validation', 'start': '2026-10-20T10:40:00Z', 'end': '2026-10-20T10:50:00Z'}]}


@pytest.fixture
def exports(protocol):
    result = {}
    for partition, data in [('train', [(.9, 1), (.2, 0), (.8, 1), (.1, 0)]),
                            ('validation', [(.8, 0), (.7, 0), (.1, 1), (.2, 1)])]:
        start = m.diagnostics.timestamp(protocol['partitions'][partition]['start'])
        rows = [{'pair': 'BTC/USDT' if index < 2 else 'ETH/USDT',
                 'open_time': (start+timedelta(minutes=5*index)).isoformat(),
                 'label_end_time': (start+timedelta(minutes=5*(index+1))).isoformat(),
                 'probability': probability, 'label': label} for index, (probability, label) in enumerate(data)]
        result[partition] = {'partition': partition, 'dataset_sha256': 'a'*64, 'source_sha256': 'b'*64,
            'development_end': protocol['partitions'][partition]['end'], 'rows': rows}
    return result


def test_hand_computed_brier_gap_and_coverage(protocol, exports):
    report = m.build(protocol, exports)
    assert report['partitions']['train']['evidence']['overall']['brier_score'] == pytest.approx(.025)
    assert report['partitions']['validation']['evidence']['overall']['brier_score'] == pytest.approx(.645)
    assert report['train_validation_gap']['brier_score'] == pytest.approx(.62)
    assert report['gap_direction'] == 'validation_minus_train'
    assert report['partition_coverage']['train'] == {'expected_pair_observations': 8,
        'observed_pair_observations': 4, 'missing_pair_observations': 4, 'observation_coverage_fraction': .5,
        'largest_pair_observation_share': .5,
        'per_pair': {'BTC/USDT': {'expected': 4, 'observed': 2, 'missing': 2},
                     'ETH/USDT': {'expected': 4, 'observed': 2, 'missing': 2}}}
    assert sum(window['coverage']['observed_pair_observations'] for window in report['time_windows']) == 8
    assert report['time_windows'][0]['coverage']['largest_pair_observation_share'] == 1
    assert all(item['value'] is None and item['reason'] for item in report['unavailable'].values())
    for name in ('regimes_computed', 'strategy_economics_computed', 'upstream_data_admission_verified',
                 'original_revision_lineage_verified', 'purge_and_embargo_qualified',
                 'statistical_significance_established', 'independent_test_accessed', 'fit_performed',
                 'model_prediction_performed', 'provider_called', 'candidate_numeric_worker_executed',
                 'training_data_admitted', 'production_promotion_authorized'):
        assert report[name] is False


def test_partition_v2_metrics_remain_exactly_compatible(protocol, exports):
    report = m.build(protocol, exports)
    for partition in ('train', 'validation'):
        assert report['partitions'][partition] == m.diagnostics.build_diagnostics(exports[partition], threshold=.5)
        m.diagnostics.validate_diagnostics(report['partitions'][partition])


def test_row_order_does_not_change_evidence_or_gap(protocol, exports):
    expected = m.build(protocol, exports)
    for export in exports.values(): export['rows'].reverse()
    assert m.build(protocol, exports) == expected


def test_empty_slice_and_undefined_denominators_stay_null(protocol, exports):
    exports['validation']['rows'] = exports['validation']['rows'][:2]
    report = m.build(protocol, exports); empty = report['time_windows'][-1]
    assert empty['status'] == 'unavailable' and empty['metrics'] is None
    assert empty['observations_sha256'] is None and empty['label_information_end'] is None
    assert empty['coverage']['observed_pair_observations'] == 0
    assert empty['coverage']['missing_pair_observations'] == 4
    assert empty['coverage']['largest_pair_observation_share'] is None
    assert report['descriptive_window_metric_spread']['validation']['brier_score'] is None
    exports['validation']['rows'][0]['probability'] = .1
    exports['validation']['rows'][1]['probability'] = .2
    report = m.build(protocol, exports)
    assert report['time_windows'][2]['metrics']['overall']['precision'] is None
    assert report['time_windows'][2]['metrics']['overall']['recall'] is None


def test_observation_boundary_is_half_open_and_label_horizon_is_reported(protocol, exports):
    exports['train']['rows'][1]['label_end_time'] = '2026-10-20T10:15:00Z'
    report = m.build(protocol, exports)
    assert report['time_windows'][0]['labels_ending_after_slice_boundary'] == 1
    assert report['time_windows'][0]['label_information_end'] == '2026-10-20T10:15:00+00:00'
    assert report['time_windows'][1]['metrics']['overall']['count'] == 2
    assert report['time_windows'][0]['slice_is_independent_test'] is False


@pytest.mark.parametrize('change', [
    lambda p: p.update(schema_version='test-v1'),
    lambda p: p.update(analysis_kind='independent_final_test'),
    lambda p: p.update(decision_threshold=True),
    lambda p: p.update(decision_threshold=float('nan')),
    lambda p: p.update(pairs=['ETH/USDT', 'BTC/USDT']),
    lambda p: p.update(pairs=['BTC/USDT', 'BTC/USDT']),
    lambda p: p.update(pairs=['secrets']),
    lambda p: p['partitions'].update(final_test={'start': '2026-10-21T00:00:00Z', 'end': '2026-10-22T00:00:00Z'}),
    lambda p: p['partitions']['validation'].update(start='2026-10-20T10:15:00Z'),
    lambda p: p['windows'][1].update(start='2026-10-20T10:05:00Z'),
    lambda p: p['windows'][1].update(start='2026-10-20T10:15:00Z'),
    lambda p: p['windows'][0].update(id='../../private'),
    lambda p: p['windows'][1].update(id='train_first'),
    lambda p: p['windows'][0].update(partition='final_test'),
    lambda p: p['windows'][0].update(start='2026-10-20T09:55:00Z'),
    lambda p: p['windows'][0].update(start='2026-10-20T10:00:00.001Z'),
    lambda p: p['windows'].pop(),
    lambda p: p['partitions']['train'].update(start='2000-01-01T00:00:00Z'),
])
def test_changed_or_leaking_protocol_rejected(protocol, exports, change):
    change(protocol)
    with pytest.raises(ValueError): m.build(protocol, exports)


@pytest.mark.parametrize('change', [
    lambda e: e['validation'].update(partition='test'),
    lambda e: e['validation'].update(dataset_sha256='c'*64),
    lambda e: e['validation'].update(source_sha256='c'*64),
    lambda e: e['train'].update(development_end='2026-10-20T10:25:00Z'),
    lambda e: e['train']['rows'][0].update(open_time='2026-10-20T09:55:00Z'),
    lambda e: e['train']['rows'][0].update(pair='SOL/USDT'),
    lambda e: e['train']['rows'][0].update(label_end_time='2026-10-20T10:25:00Z'),
    lambda e: e['train']['rows'][0].update(label_end_time='2026-10-20T10:06:00Z'),
    lambda e: e['train']['rows'][0].update(probability=float('inf')),
    lambda e: e['train']['rows'][0].update(label=True),
    lambda e: e['train']['rows'].append(deepcopy(e['train']['rows'][0])),
    lambda e: e['validation'].update(rows=[]),
    lambda e: e['train'].update(secret='never-export'),
])
def test_export_boundaries_and_schema_rejected(protocol, exports, change):
    change(exports)
    with pytest.raises(ValueError): m.build(protocol, exports)


def test_private_sealed_pack_replay_and_rehashed_report_tampering(protocol, exports, tmp_path):
    report = m.prepare(tmp_path/'pack', protocol, exports)
    assert m.verify(tmp_path/'pack') == report
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in (tmp_path/'pack').iterdir())
    with pytest.raises(ValueError, match='new_diagnostic_slice'): m.prepare(tmp_path/'pack', protocol, exports)
    report['training_data_admitted'] = True
    report['report_sha256'] = m.diagnostics.digest({name: value for name, value in report.items() if name != 'report_sha256'})
    (tmp_path/'pack/report.json').write_text(m.diagnostics.canonical(report)+'\n')
    with pytest.raises(ValueError, match='diagnostic_slice_evidence'): m.verify(tmp_path/'pack')


def test_real_size_bounds_cannot_be_bypassed_in_direct_python_api(protocol, exports, monkeypatch):
    exports['train']['rows'] = exports['train']['rows']*5001
    with pytest.raises(ValueError, match='bounded_development_observations'): m.build(protocol, exports)


def test_fixed_config_and_policy_mutation_rejected(protocol, exports, monkeypatch):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-diagnostic-slices-v1.json').read_text()) == m.POLICY
    monkeypatch.setitem(m.POLICY, 'maximum_rows_per_partition', 30000)
    with pytest.raises(ValueError, match='policy_changed'): m.build(protocol, exports)


def test_safe_cli_and_duplicate_json_refusal(tmp_path, capsys):
    assert m.main(['verify', '--directory', str(tmp_path/'private-secret-path')]) == 2
    assert 'private-secret-path' not in capsys.readouterr().out
    directory = tmp_path/'inputs'; directory.mkdir(mode=0o700)
    path = directory/'input.json'; path.write_text('{"schema_version":"x","schema_version":"y"}'); path.chmod(0o600)
    assert m.main(['prepare', '--directory', str(tmp_path/'pack'), '--input', str(path)]) == 2
    assert not (tmp_path/'pack').exists()
