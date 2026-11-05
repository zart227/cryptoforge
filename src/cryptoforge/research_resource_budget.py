"""Admission allocations and nullable observations in the common transaction.

Allocations are not hard bounds on provider consumption. No quota is refunded.
Legacy actions retain their history and get conservative, unmeasured allocations.
"""
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields

DEFAULT_RESOURCES = {
    'schema_version': 'coordinated-research-resources-v1',
    'total_input_tokens': 160000, 'total_output_tokens': 10240, 'total_wall_ms': 600000,
    'proposal_input_tokens': 32000, 'proposal_output_tokens': 2048,
    'wall_ms_by_kind': {'proposal': 65000, 'fit': 25000, 'semantic_fixture': 35000},
}
RESOURCE_TABLES = {'coordinated_resource_policy', 'coordinated_resources'}
TOKEN_FIELDS = {'input_tokens', 'output_tokens', 'total_tokens'}
ZERO_TOKENS = {name: 0 for name in sorted(TOKEN_FIELDS)}
UNKNOWN_TOKENS = {name: None for name in sorted(TOKEN_FIELDS)}


def validate_resources(policy):
    exact_fields(policy, set(DEFAULT_RESOURCES))
    exact_fields(policy['wall_ms_by_kind'], set(DEFAULT_RESOURCES['wall_ms_by_kind']))
    if policy['schema_version'] != DEFAULT_RESOURCES['schema_version']:
        raise ValueError('supported resource policy required')
    for name in ('total_input_tokens', 'total_output_tokens', 'total_wall_ms', 'proposal_input_tokens', 'proposal_output_tokens'):
        if type(policy[name]) is not int or not 1 <= policy[name] <= 100_000_000:
            raise ValueError('bounded positive resource allocations required')
    if policy['proposal_output_tokens'] != 2048:
        raise ValueError('output allocation must match the fixed generation limit')
    if any(type(v) is not int or not 1 <= v <= 600_000 for v in policy['wall_ms_by_kind'].values()):
        raise ValueError('bounded wall allocations required')
    return {**policy, 'wall_ms_by_kind': dict(policy['wall_ms_by_kind'])}


def validate_tokens(tokens):
    exact_fields(tokens, TOKEN_FIELDS)
    if any(v is not None and (type(v) is not int or not 0 <= v <= 10**12) for v in tokens.values()):
        raise ValueError('nullable nonnegative token observations required')
    total = tokens['total_tokens']
    parts = [tokens['input_tokens'], tokens['output_tokens']]
    if total is not None and (sum(v for v in parts if v is not None) > total or
            all(v is not None for v in parts) and sum(parts) != total):
        raise ValueError('inconsistent provider token observations')
    return dict(tokens)


def provider_tokens(usage):
    usage = usage if isinstance(usage, dict) else {}
    values = {}
    for target, source in (('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'), ('total_tokens', 'total_tokens')):
        value = usage.get(source)
        values[target] = value if type(value) is int and 0 <= value <= 10**12 else None
    try:
        return validate_tokens(values)
    except ValueError:
        return dict(UNKNOWN_TOKENS)


def allocation(policy, kind, semantic_policy=None, code_policy=None):
    if kind == 'code_check':
        if code_policy is None:
            raise ValueError('explicit code resource extension required')
        return {name: code_policy[name] for name in ('input_tokens', 'output_tokens', 'wall_ms')}
    if kind == 'semantic_live':
        if semantic_policy is None:
            raise ValueError('semantic resource extension required')
        return {name: semantic_policy[name] for name in ('input_tokens', 'output_tokens', 'wall_ms')}
    return {'input_tokens': policy['proposal_input_tokens'] if kind == 'proposal' else 0,
            'output_tokens': policy['proposal_output_tokens'] if kind == 'proposal' else 0,
            'wall_ms': policy['wall_ms_by_kind'][kind]}


def measurement(kind, elapsed_ms, envelope=None):
    if type(elapsed_ms) is not int or elapsed_ms < 0:
        raise ValueError('nonnegative monotonic handler time required')
    external = kind in ('proposal', 'semantic_live') and (envelope is None or
        envelope['observed']['remote_completions'] + envelope['observed']['local_llm_completions'] > 0)
    tokens = validate_tokens(envelope.get('tokens', UNKNOWN_TOKENS)) if external and envelope else dict(UNKNOWN_TOKENS if external else ZERO_TOKENS)
    if not external and envelope and envelope.get('tokens', ZERO_TOKENS) != ZERO_TOKENS:
        raise ValueError('tokens require a newly observed provider completion')
    return {'origin': 'handler_measurement', 'handler_wall_ms': elapsed_ms, 'tokens': tokens,
            'token_origin': 'provider_reported_or_unknown' if external else 'no_new_completion'}


def _legacy_measurement(kind):
    return {'origin': 'legacy_unmeasured', 'handler_wall_ms': None,
            'tokens': dict(UNKNOWN_TOKENS if kind == 'proposal' else ZERO_TOKENS),
            'token_origin': 'legacy_unknown' if kind == 'proposal' else 'no_provider_operation'}


def _checked(raw, checksum):
    value = strict_json(raw)
    if digest(value) != checksum:
        raise ValueError('resource checksum mismatch')
    return value


def check_resource_policy(db, policy):
    if db.execute('SELECT payload,sha FROM coordinated_resource_policy WHERE id=1').fetchone() != (canonical(policy), digest(policy)):
        raise ValueError('persisted resource policy changed')


def ensure_resources(db, policy, existing_tables, semantic_policy=None, code_policy=None):
    present = existing_tables & RESOURCE_TABLES
    if present and present != RESOURCE_TABLES:
        raise ValueError('incomplete resource journal')
    if not present:
        db.execute('CREATE TABLE coordinated_resource_policy (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, sha TEXT)')
        db.execute('''CREATE TABLE coordinated_resources (key TEXT PRIMARY KEY,
            allocation TEXT NOT NULL, allocation_sha TEXT NOT NULL, measurement TEXT, measurement_sha TEXT) WITHOUT ROWID''')
        db.execute('INSERT INTO coordinated_resource_policy VALUES (1,?,?)', (canonical(policy), digest(policy)))
        for key, kind in db.execute('SELECT key,kind FROM coordinated_actions').fetchall():
            reserved, measured = allocation(policy, kind), _legacy_measurement(kind)
            db.execute('INSERT INTO coordinated_resources VALUES (?,?,?,?,?)',
                       (key, canonical(reserved), digest(reserved), canonical(measured), digest(measured)))
    check_resource_policy(db, policy)
    resource_snapshot(db, policy, semantic_policy, code_policy)


def resource_snapshot(db, policy, semantic_policy=None, code_policy=None):
    check_resource_policy(db, policy)
    rows = db.execute('''SELECT a.kind,a.status,r.key,r.allocation,r.allocation_sha,r.measurement,r.measurement_sha
        FROM coordinated_actions a LEFT JOIN coordinated_resources r ON a.key=r.key''').fetchall()
    if len(rows) != db.execute('SELECT count(*) FROM coordinated_resources').fetchone()[0]:
        raise ValueError('resource/action coverage mismatch')
    reserved = {'input_tokens': 0, 'output_tokens': 0, 'wall_ms': 0}
    known = dict(ZERO_TOKENS); unknown = dict(ZERO_TOKENS)
    wall_ms = measured_actions = legacy = overruns = 0
    for kind, status, key, raw, checksum, measured_raw, measured_checksum in rows:
        if key is None:
            raise ValueError('resource/action coverage mismatch')
        alloc = _checked(raw, checksum)
        if alloc != allocation(policy, kind, semantic_policy, code_policy):
            raise ValueError('resource allocation differs from frozen policy')
        for name, value in alloc.items(): reserved[name] += value
        measured = _checked(measured_raw, measured_checksum) if measured_raw is not None else None
        if measured is None:
            if status != 'reserved' or measured_checksum is not None:
                raise ValueError('finished resource observation missing')
            tokens, elapsed = (UNKNOWN_TOKENS if kind in ('proposal', 'semantic_live') else ZERO_TOKENS), None
        else:
            exact_fields(measured, {'origin', 'handler_wall_ms', 'tokens', 'token_origin'})
            tokens = validate_tokens(measured['tokens']); elapsed = measured['handler_wall_ms']
            if elapsed is not None and (type(elapsed) is not int or elapsed < 0):
                raise ValueError('invalid measured handler time')
            legacy += measured['origin'] == 'legacy_unmeasured'
        if kind not in ('proposal', 'semantic_live') and tokens != ZERO_TOKENS:
            raise ValueError('offline operations cannot consume provider tokens')
        for name, value in tokens.items():
            if value is None: unknown[name] += 1
            else: known[name] += value
        if elapsed is not None: wall_ms += elapsed; measured_actions += 1
        overruns += (any(value is not None and value > alloc[name] for name, value in
                        (('input_tokens', tokens['input_tokens']), ('output_tokens', tokens['output_tokens']), ('wall_ms', elapsed)))
                     or tokens['total_tokens'] is not None and tokens['total_tokens'] > alloc['input_tokens'] + alloc['output_tokens'])
    return {'schema_version': 'coordinated-resource-snapshot-v1', 'policy': strict_json(canonical(policy)),
        'reserved_allocations': reserved, 'provider_tokens_known_subtotal': known,
        'unknown_token_actions_by_field': unknown, 'measured_handler_wall_ms_subtotal': wall_ms,
        'unmeasured_wall_actions': len(rows)-measured_actions, 'legacy_unmeasured_actions': legacy,
        'overrun_actions': overruns, 'hard_consumption_cap': False, 'billing_audited': False}


def reserve_resources(db, policy, key, kind, semantic_policy=None, code_policy=None):
    snapshot = resource_snapshot(db, policy, semantic_policy, code_policy); alloc = allocation(policy, kind, semantic_policy, code_policy)
    if snapshot['overrun_actions']:
        raise ValueError('prior resource allocation overrun; fresh work blocked')
    for name in alloc:
        if snapshot['reserved_allocations'][name] + alloc[name] > policy['total_'+name]:
            raise ValueError('common resource allocation budget exhausted')
    db.execute('INSERT INTO coordinated_resources VALUES (?,?,?,NULL,NULL)', (key, canonical(alloc), digest(alloc)))


def finish_resources(db, key, measured):
    if db.execute('UPDATE coordinated_resources SET measurement=?,measurement_sha=? WHERE key=? AND measurement IS NULL',
                  (canonical(measured), digest(measured), key)).rowcount != 1:
        raise ValueError('resource measurement is immutable')


def read_measurement(db, key):
    row = db.execute('SELECT measurement,measurement_sha FROM coordinated_resources WHERE key=?', (key,)).fetchone()
    return _checked(*row) if row and row[0] is not None else None
