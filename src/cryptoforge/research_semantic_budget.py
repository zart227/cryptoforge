"""Explicit additive semantic-live budget extension; no transport or model calls."""
import hashlib
from pathlib import Path

from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


EXTENSION_TABLE = 'coordinated_semantic_extension'
DEFAULT_SEMANTIC_POLICY = {'schema_version': 'coordinated-semantic-live-budget-v2',
    'maximum_actions': 5, 'input_tokens': 32000, 'output_tokens': 2048, 'wall_ms': 35000,
    'free_only': True, 'transport': 'ollama_local_decision_only'}


def validate_semantic_policy(policy):
    exact_fields(policy, set(DEFAULT_SEMANTIC_POLICY))
    if (policy['schema_version'] != DEFAULT_SEMANTIC_POLICY['schema_version']
            or policy['free_only'] is not True or policy['transport'] != 'ollama_local_decision_only'):
        raise ValueError('explicit free local semantic budget required')
    for name, low, high in (('maximum_actions', 0, 1000), ('input_tokens', 1, 100_000_000),
                           ('output_tokens', 1, 100_000_000), ('wall_ms', 1, 600_000)):
        if type(policy[name]) is not int or not low <= policy[name] <= high:
            raise ValueError('bounded semantic budget allocations required')
    return dict(policy)


def extension_configuration(policy, ledger, base_manifest, resources):
    return {'schema_version': 'coordinated-semantic-configuration-v2',
        'policy': validate_semantic_policy(policy), 'journal_path_sha256': digest(str(Path(ledger).resolve())),
        'base_manifest_sha256': digest(base_manifest), 'base_resource_policy_sha256': digest(resources)}


def check_extension(db, configuration, *, present):
    if configuration is None:
        if present:
            raise ValueError('explicit semantic-live policy and ledger required for migrated journal')
        return None
    if not present:
        raise ValueError('explicit semantic budget migration required')
    row = db.execute('SELECT payload,sha FROM coordinated_semantic_extension WHERE id=1').fetchone()
    if row is None or db.execute('SELECT count(*) FROM coordinated_semantic_extension').fetchone()[0] != 1:
        raise ValueError('semantic extension record missing')
    payload = strict_json(row[0], max_bytes=64000)
    if digest(payload) != row[1]:
        raise ValueError('semantic extension checksum mismatch')
    exact_fields(payload, {'schema_version', 'configuration', 'migration'})
    if (payload['schema_version'] != 'coordinated-semantic-extension-v2'
            or canonical(payload['configuration']) != canonical(configuration)):
        raise ValueError('persisted semantic policy or journal binding changed')
    audit = payload['migration']
    exact_fields(audit, {'migrated_at', 'legacy_action_count', 'legacy_tables_sha256', 'resource_backfilled'})
    timestamp(audit['migrated_at'])
    if (type(audit['legacy_action_count']) is not int or audit['legacy_action_count'] < 0
            or type(audit['resource_backfilled']) is not bool):
        raise ValueError('invalid semantic migration audit')
    exact_fields(audit['legacy_tables_sha256'], {'coordinated_policy', 'coordinated_actions',
        'coordinated_resource_policy', 'coordinated_resources'})
    for value in audit['legacy_tables_sha256'].values():
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('invalid migration table digest')
    return payload


def table_digest(db, table):
    ordering = {'coordinated_policy': 'id', 'coordinated_actions': 'key',
                'coordinated_resource_policy': 'id', 'coordinated_resources': 'key'}
    if table not in ordering:
        raise ValueError('fixed migration tables only')
    checksum = hashlib.sha256()
    for row in db.execute(f'SELECT * FROM {table} ORDER BY {ordering[table]}'):
        raw = canonical(list(row)).encode()
        checksum.update(len(raw).to_bytes(8, 'big')); checksum.update(raw)
    return checksum.hexdigest()


def check_legacy_actions(db, validate_usage):
    for kind, questions, status, raw, checksum, observed, observed_sha in db.execute(
            'SELECT kind,questions,status,payload,payload_sha,observed,observed_sha FROM coordinated_actions'):
        if (kind not in ('proposal', 'semantic_fixture', 'fit') or type(questions) is not int
                or (not 1 <= questions <= 16 if kind == 'semantic_fixture' else questions != 0)):
            raise ValueError('invalid legacy action kind or questions')
        if status in ('failed', 'cancelled', 'timed_out'):
            if any(value is not None for value in (raw, checksum, observed, observed_sha)):
                raise ValueError('unexpected result on failed legacy action')
        elif status == 'completed':
            envelope = strict_json(raw, max_bytes=2_000_000)
            exact_fields(envelope, {'result', 'observed', 'tokens'} if isinstance(envelope, dict) and 'tokens' in envelope else {'result', 'observed'})
            validate_usage(envelope['observed'], kind)
            if (digest(envelope) != checksum or canonical(envelope['observed']) != observed
                    or digest(envelope['observed']) != observed_sha):
                raise ValueError('legacy action result or observed checksum mismatch')
        else:
            raise ValueError('unresolved or invalid legacy action status')


def create_extension(db, configuration, migrated_at, *, resource_backfilled):
    audit = {'migrated_at': migrated_at, 'legacy_action_count': db.execute('SELECT count(*) FROM coordinated_actions').fetchone()[0],
        'legacy_tables_sha256': {name: table_digest(db, name) for name in
            ('coordinated_policy', 'coordinated_actions', 'coordinated_resource_policy', 'coordinated_resources')},
        'resource_backfilled': resource_backfilled}
    payload = {'schema_version': 'coordinated-semantic-extension-v2', 'configuration': configuration, 'migration': audit}
    db.execute('CREATE TABLE coordinated_semantic_extension (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, sha TEXT NOT NULL)')
    db.execute('INSERT INTO coordinated_semantic_extension VALUES (1,?,?)', (canonical(payload), digest(payload)))
    return check_extension(db, configuration, present=True)
