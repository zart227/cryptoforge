from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from cryptoforge.model_training import TrainingExample, FEATURE_NAMES
from cryptoforge.training_snapshot import save_training_snapshot, save_runtime_sources
from cryptoforge.llm_development_export import extract_development, main


def source(tmp_path, **overrides):
    module = tmp_path/'never_execute.py'
    module.write_text("raise RuntimeError('archived code must not execute')\n")
    hashes = {'primary': hashlib.sha256(module.read_bytes()).hexdigest()}
    runtime = save_runtime_sources(tmp_path/'runtime', {'primary': module}, hashes)
    metadata = {'feature_version': 'candle-v1', 'feature_names': list(FEATURE_NAMES),
        'feature_calculation_contract': 'bounded-window-candle-v1', 'implementation_hashes': hashes,
        'runtime_source_bundle': runtime, 'round_trip_cost': 0.003, 'min_label_return': 0.003,
        'horizon_candles': 3, 'timeframe': '5m', **overrides}
    start = datetime(2025,1,1,tzinfo=timezone.utc)
    def rows(day, pair='W/USDT'):
        return [TrainingExample(pair, start+timedelta(days=day,minutes=i*5),
            tuple(float(i%2) for _ in range(7)), i%2, 0,
            label_end_time=start+timedelta(days=day,minutes=i*5+1)) for i in range(4)]
    return save_training_snapshot(tmp_path/'snapshots', splits={
        'train': rows(0), 'validation': rows(1), 'test': rows(2, 'SECRETTEST/USDT')}, metadata=metadata)


def test_verified_export_never_contains_test_rows_or_archived_source(tmp_path):
    reference = source(tmp_path)
    data, provenance = extract_development(reference)
    serialized = json.dumps(data)+json.dumps(provenance)
    assert 'test' not in data and 'SECRETTEST' not in serialized
    assert 'archived code must not execute' not in serialized
    assert data['train'][0]['pair'] == 'W/USDT'
    assert provenance['test_exported'] is False
    assert provenance['archived_code_executed'] is False
    assert not provenance['independent_evidence']
    assert provenance['split_counts'] == {'train': 4, 'validation': 4}


@pytest.mark.parametrize('override', [
    {'feature_version': 'unknown'}, {'feature_calculation_contract': 'whole-history-ema'},
    {'min_label_return': 0.0001}, {'horizon_candles': True},
    {'implementation_hashes': {'primary': '0'*64}},
])
def test_incompatible_source_provenance_rejected(tmp_path, override):
    reference = source(tmp_path, **override)
    with pytest.raises(ValueError):
        extract_development(reference)


def test_corrupt_snapshot_rejected_before_any_export(tmp_path):
    reference = source(tmp_path)
    reference['sha256'] = '0'*64
    ref = tmp_path/'reference.json'
    ref.write_text(json.dumps(reference))
    output = tmp_path/'output'
    with pytest.raises(ValueError, match='checksum mismatch'):
        main(['--reference',str(ref),'--directory',str(output)])
    assert not output.exists()


def test_export_cli_private_outputs_and_no_overwrite(tmp_path):
    reference = source(tmp_path)
    ref = tmp_path/'reference.json'
    ref.write_text(json.dumps(reference))
    output = tmp_path/'export'
    assert main(['--reference',str(ref),'--directory',str(output)]) == 0
    assert (output/'development.json').stat().st_mode & 0o777 == 0o600
    assert (output/'provenance.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        main(['--reference',str(ref),'--directory',str(output)])
