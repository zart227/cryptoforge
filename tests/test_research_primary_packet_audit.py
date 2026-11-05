"""Saved examples are audited independently of model prediction or source execution."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import stat

import pytest
from cryptoforge import research_primary_packet_audit as m
from cryptoforge.research_training_diagnostics import canonical, digest


@pytest.fixture
def packet(tmp_path):
    project = tmp_path/'project'; folder = project/'src/cryptoforge'; folder.mkdir(parents=True)
    source = 'raise RuntimeError("archived source must never execute")\n'; (folder/'toy.py').write_text(source)
    sha = hashlib.sha256(source.encode()).hexdigest(); start = datetime(2026, 10, 25, tzinfo=timezone.utc)
    config = {'data_snapshot_at': (start+timedelta(hours=3)).isoformat(), 'timeframe': '5m',
        'feature_calculation_contract': 'bounded-window-candle-v1', 'feature_lookback_candles': 120,
        'horizon_candles': 3, 'min_label_return': .003, 'round_trip_cost': .003,
        'implementation_hashes': {'toy': sha}, 'source_admission': {'examples': 16, 'coverage_fraction': 1.0},
        'runtime_source_bundle': {'schema_version': 'primary-runtime-sources-v1'},
        'training_input_snapshot': {'split_counts': {s: 4 for s in m.SPLITS}}}
    rows = {}
    for offset, split in enumerate(m.SPLITS):
        rows[split] = []
        for i, future in enumerate((.01, -.01, 0, .01)):
            opened = start+timedelta(hours=offset, minutes=5*(i//2))
            rows[split].append({'pair': 'AAA/USDT' if i % 2 == 0 else 'BBB/USDT', 'open_time': opened.isoformat(),
                'label_end_time': (opened+timedelta(minutes=20)).isoformat(), 'features': [0.]*7,
                'future_return': future, 'label': int(future > .003), 'short_label': int(future < -.003)})
    config.update(training_label_end=rows['train'][-1]['label_end_time'], fit_information_end=rows['validation'][-1]['label_end_time'],
        evaluation_information_end=rows['test'][-1]['label_end_time'])
    artifact = {'model_family': 'pure-python-logistic', 'feature_version': 'candle-v1', 'threshold': .5,
        'model_version': 'toy-packet', 'feature_names': ['return_1', 'return_3', 'range_12', 'volume_ratio', 'ema_gap', 'rsi_14', 'candle_body'],
        'config': config, 'pairs': ['AAA/USDT', 'BBB/USDT'], 'probability_diagnostics': {}}
    for head, field, key in [('long', 'label', 'metrics'), ('short', 'short_label', 'short_metrics')]:
        artifact[key] = []; artifact['probability_diagnostics'][head] = {}
        for split in m.SPLITS:
            labels = [r[field] for r in rows[split]]; prior = sum(labels)/4; tp = 1 if head == 'long' else 0
            precision = tp/2; recall = tp/max(sum(labels), 1); accuracy = .5 if head == 'long' else .25
            artifact[key].append({'split': split, 'count': 4, 'positive_rate': .5, 'precision': precision,
                'recall': recall, 'accuracy': accuracy})
            artifact['probability_diagnostics'][head][split] = {'count': 4, 'signals': 2, 'fixed_threshold': .5,
                'observed_positive_rate': prior, 'train_positive_rate': prior,
                'selection_uses_these_diagnostics': False, 'live_profitability_established': False,
                'baseline_brier': sum((prior-y)**2 for y in labels)/4,
                'baseline_log_loss': sum(-y*math.log(prior)-(1-y)*math.log(1-prior) for y in labels)/4,
                'brier': .2, 'log_loss': .6, 'average_precision': .5}
    snapshot = {'schema_version': 'primary-training-input-snapshot-v1', 'metadata': {k: deepcopy(config[k]) for k in m.META_KEYS},
        'source_kind': 'historical_candle_primary_examples', 'target_version': 'fixed-future-return-v1',
        'counts_as_real_executed_buys': False, 'splits': rows}
    snapshot['metadata']['feature_names'] = artifact['feature_names']
    snapshot['metadata']['feature_version'] = 'candle-v1'
    runtime = {'schema_version': 'primary-runtime-sources-v1', 'python_version': [3, 12, 3],
        'python_implementation': 'CPython', 'machine': 'x86_64', 'automatically_execute_archived_code': False,
        'sources': {'toy': {'module_filename': 'toy.py', 'sha256': sha, 'source_utf8': source}}}
    binding = {'project': str(project), 'candidate_artifact_sha256': 'a'*64, 'candidate_event_time': config['data_snapshot_at']}
    return binding, artifact, snapshot, runtime


def compose(packet):
    return m.compose(*packet, '2026-10-26T00:00:00Z')


def test_exact_class_counts_baselines_and_derived_source_limits_without_execution(packet):
    r = compose(packet)
    assert r['snapshot_examples'] == 12 and r['examples_not_in_saved_splits'] == 4
    assert r['runtime_source_count'] == 1 and r['current_source_matches_fitted_source']
    assert r['heads']['long']['train']['target_positives'] == 2
    assert r['heads']['short']['test']['target_positives'] == 1
    assert r['heads']['short']['test']['always_negative_class_accuracy'] == .75
    assert r['heads']['short']['test']['reported_accuracy'] == .25
    assert len(r['exposures']) == 6 and r['all_existing_splits_now_declared_exposed_development_data']
    for k in ('training_data_admitted', 'model_prediction_performed', 'fit_performed', 'standardizer_refit_performed',
        'archived_source_executed', 'historical_first_seen_revision_lineage_verified', 'native_reader_selection_verified',
        'model_metrics_independently_recomputed', 'classification_baselines_are_trading_profitability_evidence'):
        assert r[k] is False


@pytest.mark.parametrize('change', [
    lambda p: p[2]['splits']['train'][0].update(label=True),
    lambda p: p[2]['splits']['train'][0].update(label=0),
    lambda p: p[2]['splits']['train'][0].update(future_return=.003),
    lambda p: p[2]['splits']['train'][0].update(features=[float('nan')]*7),
    lambda p: p[2]['splits']['train'][0].update(features=[0.]*6),
    lambda p: p[2]['splits']['train'][0].update(pair='UNKNOWN/USDT'),
    lambda p: p[2]['splits']['train'][0].update(label_end_time='2026-10-25T00:15:00Z'),
    lambda p: p[2]['splits']['train'].reverse(),
    lambda p: p[2]['splits']['validation'].__setitem__(0, deepcopy(p[2]['splits']['train'][0])),
    lambda p: p[1]['config'].update(fit_information_end='2026-10-25T02:25:00+00:00'),
    lambda p: p[2].update(counts_as_real_executed_buys=True),
    lambda p: p[3].update(automatically_execute_archived_code=True),
    lambda p: p[3].update(schema_version='unreviewed-v2'),
    lambda p: p[2].update(raw_candles=[]),
    lambda p: p[2]['metadata'].update(feature_version='other-features'),
    lambda p: p[3]['sources']['toy'].update(sha256='a'*64),
    lambda p: p[3]['sources']['toy'].update(module_filename='../secret.py'),
])
def test_invalid_identity_labels_purge_derived_values_or_source_contracts_refused(packet, change):
    p = deepcopy(packet); change(p)
    with pytest.raises((ValueError, KeyError)): compose(p)


@pytest.mark.parametrize('change', [
    lambda p: p[1]['metrics'][0].update(count=5),
    lambda p: p[1]['metrics'][0].update(positive_rate=.25),
    lambda p: p[1]['metrics'][0].update(precision=1),
    lambda p: p[1]['probability_diagnostics']['long']['train'].update(observed_positive_rate=.75),
    lambda p: p[1]['probability_diagnostics']['long']['train'].update(train_positive_rate=.75),
    lambda p: p[1]['probability_diagnostics']['long']['train'].update(signals=3),
    lambda p: p[1]['probability_diagnostics']['long']['train'].update(baseline_brier=.01),
    lambda p: p[1]['probability_diagnostics']['long']['train'].update(baseline_log_loss=.01),
])
def test_reported_metrics_cannot_change_observed_labels_or_train_prior(packet, change):
    p = deepcopy(packet); change(p)
    with pytest.raises(ValueError): compose(p)


def test_current_source_difference_is_reported_without_executing_archive(packet):
    path = Path(packet[0]['project'])/'src/cryptoforge/toy.py'; path.write_text('raise RuntimeError("different")\n')
    assert not compose(packet)['current_source_matches_fitted_source']


def test_audit_cannot_precede_captured_data(packet):
    with pytest.raises(ValueError): m.compose(*packet, '2026-10-24T00:00:00Z')


def test_explicit_pair_example_and_runtime_count_bounds(packet):
    p = deepcopy(packet); p[1]['pairs'] = [f'A{i}/USDT' for i in range(33)]
    with pytest.raises(ValueError): compose(p)
    p = deepcopy(packet); p[2]['splits']['train'] *= 2501
    with pytest.raises(ValueError): compose(p)
    p = deepcopy(packet); p[3]['sources'] = {str(i): p[3]['sources']['toy'] for i in range(17)}
    with pytest.raises(ValueError): compose(p)


def write_gzip(project, payload, *, declared_size=None):
    raw = payload if type(payload) is bytes else canonical(payload).encode()
    sha = hashlib.sha256(raw).hexdigest(); directory = project/'.local/models/input-snapshots'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True); path = directory/(sha+'.json.gz')
    path.write_bytes(gzip.compress(raw, mtime=0)); path.chmod(0o600)
    return {'schema_version': 'primary-training-input-snapshot-v1', 'path': str(path), 'sha256': sha,
        'compression': 'gzip', 'uncompressed_bytes': len(raw) if declared_size is None else declared_size}


def test_bounded_original_gzip_checksum_duplicates_and_no_path_reconstruction(packet):
    project = Path(packet[0]['project']); ref = write_gzip(project, {'hello': 'original'})
    parsed, binding = m._gzip(ref, project, ref['schema_version'], 1024)
    assert parsed == {'hello': 'original'} and binding['uncompressed_sha256'] == ref['sha256']
    for changed in ({**ref, 'sha256': 'a'*64}, {**ref, 'uncompressed_bytes': 2}, {**ref, 'uncompressed_bytes': 1025}):
        with pytest.raises(ValueError): m._gzip(changed, project, ref['schema_version'], 1024)
    ref = write_gzip(project, b'{"a":1,"a":2}')
    with pytest.raises(ValueError): m._gzip(ref, project, ref['schema_version'], 1024)


def test_gzip_bound_prevents_decompressing_an_entire_oversize_member(packet):
    project = Path(packet[0]['project']); ref = write_gzip(project, b'x'*1000000, declared_size=16)
    with pytest.raises(ValueError): m._gzip(ref, project, ref['schema_version'], 1024)


def test_private_artifact_replay_preserves_full_source_binding_and_rejects_rehashed_admission(packet, tmp_path, monkeypatch):
    binding = {**packet[0], 'registry': str(tmp_path/'registry')}; bound = (binding, *packet[1:])
    monkeypatch.setattr(m, 'bind', lambda *_: bound)
    result = m.prepare(tmp_path/'pack', tmp_path/'registry', Path(binding['project']))
    assert m.verify(tmp_path/'pack') == result
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in (tmp_path/'pack').iterdir())
    with pytest.raises(ValueError): m.prepare(tmp_path/'pack', tmp_path, tmp_path)
    changed = json.loads((tmp_path/'pack/audit.json').read_text()); changed['training_data_admitted'] = True
    changed['audit_sha256'] = digest({k: v for k, v in changed.items() if k != 'audit_sha256'})
    (tmp_path/'pack/audit.json').write_text(canonical(changed))
    with pytest.raises(ValueError): m.verify(tmp_path/'pack')


def test_frozen_config_and_safe_missing_pack_cli(tmp_path, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-primary-packet-audit-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out
