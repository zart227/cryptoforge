"""Trusted source-only projection of the main reference ledger; no collection or forecast."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

from cryptoforge import reference_source_ledger as source


def project(packet, directory):
    reference = packet['reference']
    ledger = source.ReferenceLedger.open(reference)
    if ledger.manifest['artifact_sha256'] is not None:
        raise ValueError('source_only_ledger_without_model_required')
    with ledger._lease():
        db = source._database(ledger.path, ledger.policy, readonly=True)
        try:
            counts = {name: db.execute('SELECT count(*) FROM '+name).fetchone()[0]
                      for name in ('events', 'versions', 'forecasts')}
            if counts['events'] > 128 or counts['versions'] > 1024 or counts['forecasts']:
                raise ValueError('bounded_source_only_history_required')
            for raw, in db.execute("SELECT payload FROM events WHERE kind='poll_prepared'"):
                anchor = source.parse(raw)['anchor_ms']
                if anchor > packet['maximum_close_ms'] or anchor >= packet['holdout_start_ms']:
                    raise ValueError('development_source_anchors_only')
        finally:
            db.close()
    # The native audit's scratch location is redirected, not its schema/math/checks.
    # Parent owns this private temporary directory and removes it even after SIGKILL.
    original_tempfile = source.tempfile
    def scratch(*args, **kwargs):
        if kwargs.get('prefix') != 'reference-audit-' or Path(kwargs.get('dir')) != ledger.root.parent:
            raise ValueError('fixed_native_audit_scratch_required')
        return tempfile.NamedTemporaryFile(*args, **{**kwargs, 'dir': directory})
    source.tempfile = SimpleNamespace(NamedTemporaryFile=scratch)
    try:
        audit = source.audit_reference_ledger(reference)
    finally:
        source.tempfile = original_tempfile
    rows, polls, responses = [], [], []
    with ledger._lease():
        ledger._check(active=False)
        db = source._database(ledger.path, ledger.policy, readonly=True)
        try:
            first = {(sid, version): known for sid, version, known in
                     db.execute('SELECT source_id,version,known_at FROM versions')}
            for seq, kind, raw, sha in db.execute('SELECT seq,kind,payload,sha FROM events ORDER BY seq'):
                value = source.parse(raw)
                if kind == 'poll_prepared':
                    responses = []
                elif kind == 'source_response':
                    derived = source.evaluate(value['observation'], started=value['request_started_at'],
                                              recorded=value['recorded_at'])
                    responses.append({'pair': value['observation']['pair'], 'event_seq': seq, 'sha256': sha,
                        'status': derived['status'], 'known_at': derived['known_at'],
                        'recorded_at': value['recorded_at'], 'latest_close_ms': derived.get('latest_close_ms'),
                        'rows': len(derived['rows'])})
                    for row in derived['rows']:
                        rows.append({'source_id': row['source_id'], 'version_sha256': row['version_sha256'],
                            'pair': row['pair'], 'open_ms': row['open_ms'], 'observed_at': row['known_at'],
                            'first_seen_at': first[(row['source_id'], row['version_sha256'])],
                            'event_seq': seq, 'response_sha256': sha})
                    if len(rows) > 2048:
                        raise ValueError('delivered_row_budget_exhausted')
                elif kind == 'poll_complete':
                    polls.append({'anchor_ms': value['anchor_ms'], 'completed_at': value['completed_at'],
                                  'responses': responses})
                else:
                    raise ValueError('no_forecast_projection_permitted')
        finally:
            db.close()
    if source.file_sha(ledger.path, 8*1024*1024) != reference['database_sha256']:
        raise ValueError('original_ledger_changed_during_projection')
    return {'schema_version': 'research-reference-projection-v1', 'reference': reference,
        'source_manifest': {k: ledger.manifest[k] for k in ('mode', 'registered_at', 'start', 'end', 'pairs', 'mandatory_pairs')},
        'native_audit': audit, 'rows': rows, 'polls': polls, 'loaded_source_hashes': source.runtime_hashes(),
        'source_database_modified': False, 'network_request_performed': False,
        'forecast_or_inference_performed': False, 'native_scratch_redirected_to_private_worker_directory': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.input.read_bytes()
    if len(raw) > 64000:
        raise ValueError('bounded_projection_packet_required')
    result = project(json.loads(raw), args.output.parent)
    raw = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()+b'\n'
    if len(raw) > 1024*1024:
        raise ValueError('bounded_projection_output_required')
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


if __name__ == '__main__':
    main()
