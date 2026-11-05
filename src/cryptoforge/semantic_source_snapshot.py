"""Bounded development source revisions and causal, exact-content views.

Caller-supplied capture hashes/times are declarations, not verified collector
receipts. This module never fetches, classifies, labels, fits or calls an LLM.
"""
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptoforge import llm_research_contracts, training_diagnostics
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp


MAX_EXPORT_BYTES = 8_000_000
MAX_SNAPSHOT_BYTES = 16_000_000
MAX_VIEW_BYTES = 32_000_000
ROW_FIELDS = {'source_id', 'source_item_id', 'source_url', 'title', 'original_text',
              'published_at', 'source_revision', 'revised_at', 'first_seen_at',
              'received_at', 'recorded_at', 'capture_sha256'}
DERIVED_FIELDS = {'document_id', 'content_sha256', 'revision_id', 'observation_id',
                  'available_at', 'availability_status'}


def _text(value, maximum, *, nullable=False, identifier=False):
    if value is None and nullable:
        return value
    if (not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > maximum
            or (identifier and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', value))):
        raise ValueError('bounded nonempty text or identifier required')
    return value


def validate_policy(policy):
    exact_fields(policy, {'schema_version', 'policy_version', 'sources'})
    if policy['schema_version'] != 'semantic-source-policy-v1':
        raise ValueError('unsupported source policy')
    _text(policy['policy_version'], 100, identifier=True)
    sources = policy['sources']
    if not isinstance(sources, dict) or not 1 <= len(sources) <= 16:
        raise ValueError('bounded explicit source registry required')
    for source_id, source in sources.items():
        _text(source_id, 80, identifier=True)
        exact_fields(source, {'allowed_hosts'})
        hosts = source['allowed_hosts']
        if (not isinstance(hosts, list) or not 1 <= len(hosts) <= 8
                or any(not isinstance(h, str) or len(h) > 253 or not re.fullmatch(
                    r'[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}', h) for h in hosts)
                or len(set(hosts)) != len(hosts)):
            raise ValueError('explicit lowercase source hosts required')
    return policy


def _source_url(value, allowed):
    _text(value, 2048)
    if (not value.isascii() or any(c.isspace() or ord(c) < 32 for c in value)
            or '\\' in value):
        raise ValueError('source URL refused')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname not in allowed or parsed.username is not None
            or parsed.password is not None or parsed.port is not None or parsed.query or parsed.fragment
            or not parsed.path.startswith('/')):
        raise ValueError('allowlisted HTTPS source URL without credentials/query required')


def _time(value):
    if value is None:
        return None
    _text(value, 64)
    return timestamp(value).isoformat()


def _normalize(row, policy):
    exact_fields(row, ROW_FIELDS)
    row = deepcopy(row)
    _text(row['source_id'], 80, identifier=True)
    if row['source_id'] not in policy['sources']:
        raise ValueError('registered source required')
    _text(row['source_item_id'], 200)
    _source_url(row['source_url'], policy['sources'][row['source_id']]['allowed_hosts'])
    _text(row['title'], 1024); _text(row['original_text'], 32000)
    _text(row['source_revision'], 200, nullable=True)
    if not isinstance(row['capture_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', row['capture_sha256']):
        raise ValueError('declared capture SHA256 required')
    for key in ('published_at', 'revised_at', 'first_seen_at', 'received_at', 'recorded_at'):
        row[key] = _time(row[key])
    local = [row[k] for k in ('first_seen_at', 'received_at', 'recorded_at')]
    # Check even partial known pairs; missing times are never filled from dates.
    known_local = [timestamp(v) for v in local if v is not None]
    if known_local != sorted(known_local):
        raise ValueError('capture clock order must be first_seen <= received <= recorded')
    if row['published_at'] is not None and row['revised_at'] is not None:
        if timestamp(row['revised_at']) < timestamp(row['published_at']):
            raise ValueError('source revision precedes publication')
    available = None
    if all(v is not None for v in local):
        available = max(timestamp(row[k]) for k in ('published_at', 'revised_at',
            'first_seen_at', 'received_at', 'recorded_at') if row[k] is not None).isoformat()
    if len(canonical(row).encode()) > 64000:
        raise ValueError('capture metadata/text byte limit exceeded; no truncation')
    document_id = digest({'source_id': row['source_id'], 'source_item_id': row['source_item_id']})
    content = digest({'title': row['title'], 'original_text': row['original_text']})
    return {**row, 'document_id': document_id, 'content_sha256': content,
        'revision_id': digest({'document_id': document_id, 'content_sha256': content}),
        'observation_id': digest(row), 'available_at': available,
        'availability_status': 'known' if available is not None else 'unknown_local_capture_time'}


def _implementation():
    return {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name, path in {
        'source_snapshot': __file__, 'json': llm_research_contracts.__file__,
        'time_and_canonical': training_diagnostics.__file__}.items()}


def build_snapshot(export, policy):
    policy = deepcopy(validate_policy(policy))
    exact_fields(export, {'schema_version', 'origin', 'partition', 'observations'})
    if (export['schema_version'] != 'semantic-source-export-v1'
            or not isinstance(export['origin'], str)
            or export['origin'] not in {'synthetic', 'collector_export'}
            or export['partition'] != 'development'):
        raise ValueError('explicit development source export and origin required')
    rows = export['observations']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError('one to 1000 source observations required')
    if len(canonical(export).encode()) > MAX_EXPORT_BYTES:
        raise ValueError('bounded source export required')
    observations = sorted((_normalize(row, policy) for row in rows), key=lambda r: r['observation_id'])
    # Keep original provenance observations. Deduplication happens only in the view.
    normalized = {**export, 'observations': [{k: row[k] for k in ROW_FIELDS} for row in observations]}
    core = {'schema_version': 'semantic-source-snapshot-v1', 'origin': export['origin'],
        'partition': 'development', 'source_policy': policy, 'source_policy_sha256': digest(policy),
        'normalized_export_sha256': digest(normalized), 'observations': observations,
        'timestamp_assurance': 'caller_declarations_not_clock_attestation',
        'capture_hash_assurance': 'declared_upstream_hash_not_raw_artifact_verification',
        'upstream_development_lineage_verified': False,
        'implementation': _implementation(), 'api_calls': 0, 'training_executed': False}
    result = {**core, 'snapshot_sha256': digest(core)}
    if len(canonical(result).encode()) > MAX_SNAPSHOT_BYTES:
        raise ValueError('bounded source snapshot required')
    return result


def validate_snapshot(snapshot):
    exact_fields(snapshot, {'schema_version', 'origin', 'partition', 'source_policy',
        'source_policy_sha256', 'normalized_export_sha256', 'observations', 'timestamp_assurance',
        'capture_hash_assurance', 'upstream_development_lineage_verified', 'implementation',
        'api_calls', 'training_executed', 'snapshot_sha256'})
    rows = snapshot['observations']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError('bounded snapshot observations required')
    for row in rows:
        exact_fields(row, ROW_FIELDS | DERIVED_FIELDS)
    rebuilt = build_snapshot({'schema_version': 'semantic-source-export-v1', 'origin': snapshot['origin'],
        'partition': snapshot['partition'], 'observations': [{k: row[k] for k in ROW_FIELDS} for row in rows]},
        snapshot['source_policy'])
    if canonical(rebuilt) != canonical(snapshot):
        raise ValueError('source snapshot, derived times or implementation changed')
    return snapshot


def as_of(snapshot, *, decision_time, ttl_seconds):
    validate_snapshot(snapshot)
    decision = timestamp(_time(decision_time))
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 604800:
        raise ValueError('integer TTL from 1 second to 7 days required')
    # No future/unknown texts, counts or revision identities enter model_state.
    visible = {r['observation_id']: r for r in snapshot['observations']
        if r['available_at'] is not None and timestamp(r['available_at']) <= decision}
    by_document, first_content = {}, {}
    for row in visible.values():
        by_document.setdefault(row['document_id'], []).append(row)
        content = row['content_sha256']
        time = timestamp(row['available_at'])
        first_content[content] = min(first_content.get(content, time), time)
    documents, abstentions = [], []
    for document, observations in sorted(by_document.items()):
        latest = max(timestamp(r['available_at']) for r in observations)
        current = sorted((r for r in observations if timestamp(r['available_at']) == latest),
                         key=lambda r: r['observation_id'])
        if len({r['content_sha256'] for r in current}) != 1:
            abstentions.append({'document_id': document, 'reason': 'ambiguous_revision',
                               'observation_ids': [r['observation_id'] for r in current]})
            continue
        row = current[0]
        first = first_content[row['content_sha256']]
        age = (decision - first).total_seconds()
        if age > ttl_seconds:
            abstentions.append({'document_id': document, 'reason': 'expired_exact_content',
                               'observation_ids': [r['observation_id'] for r in current]})
            continue
        documents.append({**deepcopy(row), 'content_first_available_at': first.isoformat(), 'age_seconds': age})
    groups = {}
    for row in documents:
        group = groups.setdefault(row['content_sha256'], {'content_sha256': row['content_sha256'],
            'title': row['title'], 'original_text': row['original_text'],
            'content_first_available_at': row['content_first_available_at'],
            'document_ids': [], 'observation_ids': []})
        group['document_ids'].append(row['document_id'])
        group['observation_ids'].append(row['observation_id'])
    texts = []
    for _, group in sorted(groups.items()):
        group['document_ids'].sort(); group['observation_ids'].sort(); texts.append(group)
    state = {'texts': texts}
    core = {'schema_version': 'semantic-source-view-v1', 'origin': snapshot['origin'],
        'partition': 'development', 'snapshot_sha256': snapshot['snapshot_sha256'],
        'decision_time': decision.isoformat(), 'ttl_seconds': ttl_seconds,
        'ttl_policy': 'global_exact_content_first_known_availability',
        'revision_policy': 'latest_known_timed_capture_not_source_version_order',
        'documents': documents, 'abstentions': abstentions,
        'model_state': state, 'model_state_sha256': digest(state),
        'semantic_event_clusters_verified': False, 'asset_mapping_performed': False,
        'source_coverage_verified': False, 'empty_view_is_negative_label': False,
        'upstream_development_lineage_verified': False, 'api_calls': 0, 'training_executed': False}
    result = {**core, 'view_sha256': digest(core)}
    if len(canonical(result).encode()) > MAX_VIEW_BYTES:
        raise ValueError('bounded source view required; no truncation')
    return result


def _read(path, limit):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    return strict_json(raw.decode('utf-8'), max_bytes=limit)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('snapshot')
    build.add_argument('--export', type=Path, required=True)
    build.add_argument('--policy', type=Path, required=True)
    view = commands.add_parser('as-of')
    view.add_argument('--snapshot', type=Path, required=True)
    view.add_argument('--decision-time', required=True)
    view.add_argument('--ttl-seconds', type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == 'snapshot':
        result = build_snapshot(_read(args.export, MAX_EXPORT_BYTES), _read(args.policy, 32000))
    else:
        result = as_of(_read(args.snapshot, MAX_SNAPSHOT_BYTES),
                       decision_time=args.decision_time, ttl_seconds=args.ttl_seconds)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(canonical(result) + '\n'); stream.flush(); os.fsync(stream.fileno())
    print('Development source artifact saved; no fetch, LLM, fit or trading changes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
