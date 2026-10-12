"""Original research net-target inputs, distinct from primary price snapshots."""
from dataclasses import asdict
import gzip
import hashlib
import json

from cryptoforge.net_regression import NET_TARGETS
from cryptoforge.training_snapshot import _save_raw, MAX_UNCOMPRESSED_BYTES

SCHEMA = 'development-net-training-input-snapshot-v1'


def save_net_training_snapshot(directory, *, train, validation, target_version, metadata):
    if target_version not in NET_TARGETS or not train or not validation:
        raise ValueError('explicit net target and two nonempty splits required')
    splits = {name: [asdict(row) for row in rows]
              for name, rows in (('train', train), ('validation', validation))}
    payload = {'schema_version': SCHEMA, 'target_version': target_version,
        'splits': splits, 'metadata': metadata, 'outer_test_included': False,
        'counts_as_real_executed_buys': False, 'live_promotion_allowed': False}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                     default=str, allow_nan=False).encode()
    return {'schema_version': SCHEMA, **_save_raw(directory, raw),
            'split_counts': {name: len(rows) for name, rows in splits.items()}}


def load_net_training_snapshot(reference, *, target_version):
    if (target_version not in NET_TARGETS or reference.get('schema_version') != SCHEMA
            or reference.get('compression') != 'gzip'):
        raise ValueError('supported net snapshot and explicit target required')
    size = reference.get('uncompressed_bytes')
    if type(size) is not int or not 0 < size <= MAX_UNCOMPRESSED_BYTES:
        raise ValueError('bounded net input snapshot required')
    with gzip.open(reference['path'], 'rb') as stream:
        raw = stream.read(size + 1)
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('net snapshot checksum mismatch')
    payload = json.loads(raw)
    if (payload.get('schema_version') != SCHEMA or payload.get('target_version') != target_version
            or payload.get('outer_test_included') is not False
            or payload.get('counts_as_real_executed_buys') is not False
            or payload.get('live_promotion_allowed') is not False
            or set(payload.get('splits', {})) != {'train', 'validation'}
            or {name: len(rows) for name, rows in payload['splits'].items()} != reference['split_counts']):
        raise ValueError('net snapshot contract mismatch')
    return payload
