"""Read pinned original source values, using only stdlib and independent math."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from cryptoforge.research_feature_reference import reference


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(text):
    parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('aware_source_timestamp_required')
    return parsed.astimezone(timezone.utc)


def evaluate(packet):
    source = packet['reference']
    path = Path(source['root'])/'source.sqlite'
    def check():
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 8*1024*1024:
            raise ValueError('bounded_original_source_required')
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['database_sha256']:
            raise ValueError('original_source_checksum_changed')
    check()
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=1)
    db.execute('PRAGMA query_only=ON')
    output = []; count = 0
    try:
        if db.execute('SELECT count(*) FROM forecasts').fetchone()[0] != 0:
            raise ValueError('source_only_oracle_required')
        for sample in packet['selections']:
            result = {'id': sample['id'], 'feature_hex': None, 'selected_raw_sha256': None}
            if sample['features'] is not None:
                if len(sample['features']) != 120:
                    raise ValueError('closed120_selection_required')
                raw_values = []; identities = []; previous = None
                for selected in sample['features']:
                    found = db.execute('SELECT raw,pair,open_ms FROM versions WHERE source_id=? AND version=?',
                        (selected['source_id'], selected['revision_sha256'])).fetchone()
                    if found is None:
                        raise ValueError('original_selected_version_missing')
                    raw = json.loads(found[0])
                    opened = stamp(selected['open_time'])
                    opened_ms = int(opened.timestamp())*1000
                    if (type(raw) is not list or len(raw) != 7 or any(type(value) is not str for value in raw)
                            or digest(raw) != selected['revision_sha256'] or int(raw[0]) != opened_ms
                            or found[2] != opened_ms or found[1].replace('/', '') != sample['symbol']
                            or selected['symbol'] != sample['symbol']
                            or opened.second != 0 or opened.microsecond != 0 or opened.minute % 5 != 0
                            or stamp(selected['known_at']) > stamp(sample['decision_time'])
                            or opened_ms+300000 > int(stamp(sample['decision_time']).timestamp())*1000
                            or previous is not None and opened_ms-previous != 300000):
                        raise ValueError('original_value_lineage_mismatch')
                    previous = opened_ms
                    raw_values.append(raw[1:6]); identities.append(digest(raw)); count += 1
                if previous+300000 != int(stamp(sample['decision_anchor']).timestamp())*1000:
                    raise ValueError('closed_window_anchor_mismatch')
                result.update(feature_hex=reference(raw_values), selected_raw_sha256=digest(identities))
            output.append(result)
    finally:
        db.close()
    check()
    return {'schema_version': 'research-feature-reference-values-v1',
        'reference_sha256': digest(source), 'selection_sha256': digest(packet['selections']),
        'samples': output, 'source_rows_read': count,
        'trainer_or_runtime_imported': False, 'model_prediction_performed': False,
        'fit_performed': False, 'source_modified': False, 'network_request_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 2*1024*1024:
        raise ValueError('bounded_oracle_packet_required')
    result = evaluate(json.loads(args.input.read_text()))
    # A local implementation may not replace this with a native calculation.
    import sys
    if any(name in sys.modules for name in ('cryptoforge.model_training', 'cryptoforge.supabase_executor')):
        raise ValueError('oracle_must_remain_independent')
    raw = canonical(result).encode()
    if len(raw) > 262144:
        raise ValueError('bounded_oracle_result_required')
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


if __name__ == '__main__':
    main()
