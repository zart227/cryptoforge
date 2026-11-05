"""Verified extraction of historical train/validation, never test, for research.

The trusted local extractor reads the full archive to verify its checksum. Test
values are neither exported, scored nor sent to an advisor. Archived code is
verified as text and is never executed.
"""
import argparse
import hashlib
import os
from pathlib import Path

from cryptoforge.model_training import FEATURE_NAMES, FEATURE_VERSION
from cryptoforge.training_snapshot import load_training_snapshot, load_runtime_sources
from cryptoforge.research_training_diagnostics import canonical, digest, number
from cryptoforge.training_experiment_planner import DATA_VERSION, parse_development, read_json


def extract_development(reference):
    payload = load_training_snapshot(reference)
    if (payload.get('target_version') != 'fixed-future-return-v1' or
            payload.get('source_kind') != 'historical_candle_primary_examples' or
            payload.get('counts_as_real_executed_buys') is not False):
        raise ValueError('historical primary target provenance required')
    meta = payload['metadata']
    if meta.get('feature_version') != FEATURE_VERSION or meta.get('feature_names') != list(FEATURE_NAMES):
        raise ValueError('source feature contract incompatible')
    if meta.get('feature_calculation_contract') != 'bounded-window-candle-v1':
        raise ValueError('bounded causal source features required')
    source_hashes = meta['implementation_hashes']
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise ValueError('archived implementation identity required')
    load_runtime_sources(meta['runtime_source_bundle'], source_hashes)
    cost = number(meta['round_trip_cost'], 0, 0.1)
    minimum = number(meta['min_label_return'], cost, 1)
    if type(meta['horizon_candles']) is not int or meta['horizon_candles'] < 1:
        raise ValueError('source horizon required')
    data = {'schema_version': DATA_VERSION, 'target_version': payload['target_version'],
            'feature_version': FEATURE_VERSION, 'feature_names': list(FEATURE_NAMES)}
    for split in ('train', 'validation'):
        data[split] = [{key: row[key] for key in
                       ('pair', 'open_time', 'label_end_time', 'features', 'label')}
                      for row in payload['splits'][split]]
    parse_development(data)
    receipt = {'schema_version': 'llm-development-export-v1', 'dataset_sha256': digest(data),
        'source_snapshot_sha256': reference['sha256'],
        'source_runtime_sha256': meta['runtime_source_bundle']['sha256'],
        'source_implementation_hashes': source_hashes, 'target_version': payload['target_version'],
        'feature_version': FEATURE_VERSION, 'feature_calculation_contract': meta['feature_calculation_contract'],
        'timeframe': meta['timeframe'], 'horizon_candles': meta['horizon_candles'],
        'round_trip_cost': cost, 'min_label_return': minimum,
        'split_counts': {split: len(data[split]) for split in ('train', 'validation')},
        'test_exported': False, 'archived_code_executed': False,
        'independent_evidence': False, 'source_kind': payload['source_kind'],
        'exporter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return data, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True, help='primary training snapshot reference JSON')
    parser.add_argument('--directory', type=Path, required=True, help='new private export directory')
    args = parser.parse_args(argv)
    data, receipt = extract_development(read_json(args.reference))
    args.directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    for name, content in (('development.json', data), ('provenance.json', receipt)):
        fd = os.open(args.directory/name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical(content)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
    print('Verified historical development export; no test values exported')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
