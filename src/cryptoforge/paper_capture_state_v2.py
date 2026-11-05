"""Fourteen-group source commitments for the separately pinned v2 capture.

This checks source linkage, not independent financial calculations or decisions.
"""
from dataclasses import asdict
import json
from pathlib import Path

from cryptoforge.evidence_segments import canonical, digest, parse, require_sha
from cryptoforge.native_paper_archive_v2 import SOURCES, AUXILIARY, _key
from cryptoforge.paper_capture_v3 import stamp
from cryptoforge.paper_valuation_capture import _market_input as _legacy_market_input, MAX_EVENT_BYTES
from cryptoforge.paper_worker_capture import _bounded
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_wallet_v2 import PaperWalletV2
from cryptoforge.paper_worker_v2 import PaperWorkerV2
from cryptoforge.paper_producer_v2 import runtime_hashes as kernel_runtime

SCHEMA = 'paper-worker-state-commitments-v2'
MODULUS = 2**256
GROUPS = tuple(SOURCES) + tuple(AUXILIARY)


def _market_input(value):
    """Retain legacy public field allowlists, treating pair-map keys as values."""
    if type(value) is not dict:raise ValueError('plain original market input required')
    if 'quotes' not in value:
        _bounded(value, MAX_EVENT_BYTES)
        return _legacy_market_input(value)
    if set(value) != {'quotes','filters'}:raise ValueError('original mark input fields required')
    size = 0
    for field in ('quotes','filters'):
        mapping = value[field]
        if type(mapping) is not dict or len(mapping) > MAX_EVENT_BYTES//16:
            raise ValueError('bounded original mark map required')
        for pair,row in mapping.items():
            if type(pair) is not str or not pair.endswith('/USDT'):
                raise ValueError('original mark pair identity required')
            size += len(_bounded([pair,row],MAX_EVENT_BYTES))
            if size > MAX_EVENT_BYTES:raise ValueError('bounded original mark bytes required')
            _legacy_market_input(dict(quote=row if field=='quotes' else {},filters=row if field=='filters' else {}))
    return parse(canonical(value))


def _inventory(root):
    names = {'protocol.json', 'registration.json', 'capture.lock', 'storage', 'native', 'sealed.json'}
    if root.resolve() != root or any(p.name not in names or p.is_symlink() for p in root.iterdir()):
        raise ValueError('original v2 capture namespace/inventory required')


def _empty():
    return {source: dict(count=0, sum_sha256='0'*64) for source in GROUPS}


def _initial(protocol, native_manifest_pin):
    summary, config = _empty(), PaperConfig(**protocol['config'])
    wallet = object.__new__(PaperWalletV2)
    wallet.path = Path(protocol['root'])/'native'/'wallet.sqlite'
    wallet.config, wallet.candidate_sha, wallet._runtime = config, protocol['candidate_sha256'], kernel_runtime()
    wallet._identity = wallet._identity_value()
    worker = object.__new__(PaperWorkerV2)
    worker.path, worker.wallet, worker.policy = Path(protocol['root'])/'native'/'worker.sqlite', wallet, protocol['worker_policy']
    rows = {'wallet.state': [['cash',str(config.capital)], ['policy',wallet._identity]],
            'worker.state': [['identity',worker._identity_value()]]}
    for source, values in rows.items():
        for row in values:_adjust(summary, source, row, 1)
    return dict(sources=summary, checkpoint=dict(generation=0, watermarks={},
        archive_heads=[[0, digest(canonical([native_manifest_pin, b]))] for b in range(protocol['native_policy']['shards'])]))


def _row_sha(source, row):
    return int(digest(canonical([SCHEMA, source, row])), 16)


def _adjust(summary, source, row, direction):
    value = summary[source]
    value['count'] += direction
    value['sum_sha256'] = f'{(int(value["sum_sha256"],16)+direction*_row_sha(source,row))%MODULUS:064x}'
    if value['count'] < 0:
        raise ValueError('negative native logical source count')


def _valid_row(source, row):
    if source not in GROUPS or type(row) not in (tuple, list):
        raise ValueError('known typed native capture row required')
    columns = SOURCES[source][2] if source in SOURCES else AUXILIARY[source][2]
    if len(row) != len(columns) or any(type(v) not in (str, int, type(None)) for v in row):
        raise ValueError('original native capture row columns/types required')
    if source in SOURCES and SOURCES[source][3]:
        if type(row[0]) is not int or not 0 < row[0] < 2**63:
            raise ValueError('original positive native capture row ID required')
    elif type(row[0]) is not str or not 0 < len(row[0].encode()) <= 1024:
        raise ValueError('bounded original native capture key required')
    if ((source == 'wallet.state' and row[0].startswith('day_anchor:'))
            or (source == 'wallet.day_anchors' and not row[0].startswith('day_anchor:'))):
        raise ValueError('native day-anchor source partition differs')
    return list(row)


def _active(source):
    """Read only the hard-bounded active projection, never the full history."""
    maps, size = {s: {} for s in GROUPS}, 0
    db = source._native(writer=False)
    try:
        for name in GROUPS:
            if name in SOURCES:
                rows = source._rows(db, name, archive_only=False)
            else:
                alias, table, columns, _ = AUXILIARY[name]
                rows = db.execute(f'SELECT {",".join(columns)} FROM {alias}.{table} ORDER BY {columns[0]}')
            for row in rows:
                if name == 'wallet.state' and row[0].startswith('day_anchor:'):
                    continue
                row = _valid_row(name, row)
                raw = canonical(row)
                size += len(raw)
                if (len(raw) > source.policy.maximum_row_bytes
                        or size > source.policy.maximum_batch_bytes
                        or len(maps[name]) >= source.policy.maximum_active_rows):
                    raise ValueError('v2 bounded active scan exhausted; no native operation attempted')
                maps[name][row[0]] = row
    finally:
        db.close()
    return maps


def _checkpoint(source):
    heads = []
    for bucket in range(source.policy.shards):
        db = source._shard(bucket)
        try:
            heads.append(list(db.execute('SELECT seq,sha FROM head WHERE id=1').fetchone()))
        finally:
            db.close()
    db = source._native(writer=False)
    try:
        generation, watermarks = db.execute('SELECT generation,watermarks FROM meta.checkpoint WHERE id=1').fetchone()
    finally:
        db.close()
    if type(generation) is not int or generation < 0:
        raise ValueError('original native generation required')
    return dict(generation=generation, watermarks=parse(watermarks), archive_heads=heads)


def _logical(source, active, cache):
    # Cache only fourteen accumulators and one tip per fixed shard. On restart
    # stream each archive once; thereafter consume only newly appended records.
    if not cache:
        cache.update(summary=_empty(), heads=[[0, digest(canonical([source.manifest_sha256, b]))]
                                              for b in range(source.policy.shards)])
    connections = []
    try:
        for bucket in range(source.policy.shards):
            db = source._shard(bucket);connections.append(db)
            seq, sha = db.execute('SELECT seq,sha FROM head WHERE id=1').fetchone()
            old_seq, old_sha = cache['heads'][bucket]
            if seq < old_seq:
                raise ValueError('native archive tip moved backwards')
            for n, name, raw, previous, current in db.execute(
                    'SELECT seq,source,raw,previous,sha FROM records WHERE seq>? ORDER BY seq', (old_seq,)):
                if n != old_seq+1 or previous != old_sha:
                    raise ValueError('original incremental native archive chain differs')
                _adjust(cache['summary'], name, _valid_row(name, parse(raw)), 1)
                old_seq, old_sha = n, current
            if (old_seq, old_sha) != (seq, sha):
                raise ValueError('original incremental native archive tip differs')
            cache['heads'][bucket] = [seq, sha]
        summary = parse(canonical(cache['summary']))
        for name in GROUPS:
            for row in active[name].values():
                archived = None
                if name in SOURCES:
                    key = _key(name, row[0])
                    db = connections[source._bucket(name, key)]
                    archived = db.execute('SELECT raw FROM records WHERE source=? AND key=?', (name, key)).fetchone()
                if archived:
                    if parse(archived[0]) != row:
                        raise ValueError('native active/archive original row differs')
                else:
                    _adjust(summary, name, row, 1)
        return dict(sources=summary, checkpoint=_checkpoint(source))
    except Exception:
        cache.clear()
        raise
    finally:
        for db in connections:
            db.close()


def _delta(source, before, after):
    changes = []
    for name in GROUPS:
        for identity in sorted(before[name].keys() | after[name].keys()):
            old, new = before[name].get(identity), after[name].get(identity)
            if name in SOURCES and (old is None or new is None):
                archived = source.lookup(name, identity)
                if archived:
                    if old is None:old = list(archived)
                    if new is None:new = list(archived)
            if old != new:
                changes.append(dict(source=name, key=identity, before=old, after=new))
    return changes


def _apply(before, changes, *, maximum_bytes):
    if type(changes) is not list or len(canonical(changes)) > maximum_bytes:
        raise ValueError('bounded original native delta required')
    summary, seen = parse(canonical(before)), set()
    for change in changes:
        name, identity = change['source'], change['key']
        if name not in GROUPS or (name, identity) in seen:
            raise ValueError('unique original native delta keys required')
        seen.add((name, identity))
        old, new = change['before'], change['after']
        if old == new:
            raise ValueError('native delta must change an original row')
        for row, direction in ((old, -1), (new, 1)):
            if row is not None:
                if _valid_row(name, row)[0] != identity:
                    raise ValueError('native delta original row ID differs')
                _adjust(summary, name, row, direction)
    return summary


def _source_identity(source, registration, protocol):
    manifest = source.manifest
    if (manifest['source_protocol_sha256'] != registration['protocol_sha256']
            or manifest['candidate_sha256'] != protocol['candidate_sha256']
            or manifest['role'] != protocol['role'] or manifest['config'] != protocol['config']
            or manifest['worker_policy'] != protocol['worker_policy'] or manifest['policy'] != protocol['native_policy']
            or source.ready_sha256 != registration['native_ready_sha256']
            or any(manifest[k] != protocol[k] for k in ('kernel_root','kernel_contract_sha256','kernel_registration_sha256','kernel_contract'))):
        raise ValueError('original v2 native source identity differs')


def _transition(before, after):
    if set(before) != {'sources', 'checkpoint'} or set(after) != {'sources', 'checkpoint'}:
        raise ValueError('original v2 source checkpoint fields required')
    for state in (before, after):
        if set(state['sources']) != set(GROUPS):
            raise ValueError('original v2 source groups required')
        for value in state['sources'].values():
            if set(value) != {'count', 'sum_sha256'} or type(value['count']) is not int or not 0 <= value['count'] < 2**63:
                raise ValueError('original v2 logical source count required')
            require_sha(value['sum_sha256'])
        point = state['checkpoint']
        if (set(point) != {'generation', 'watermarks', 'archive_heads'} or type(point['generation']) is not int
                or not 0 <= point['generation'] < 2**63 or type(point['archive_heads']) is not list
                or not 1 <= len(point['archive_heads']) <= 64 or type(point['watermarks']) is not dict
                or any(k not in SOURCES or not SOURCES[k][3] or type(v) is not int or not 0 <= v < 2**63
                       for k,v in point['watermarks'].items())):
            raise ValueError('original v2 source checkpoint required')
        for head in point['archive_heads']:
            if type(head) is not list or len(head) != 2 or type(head[0]) is not int or head[0] < 0:
                raise ValueError('original v2 native archive head required')
            require_sha(head[1])
    a, b = before['checkpoint'], after['checkpoint']
    if b['generation'] < a['generation'] or len(a['archive_heads']) != len(b['archive_heads']):
        raise ValueError('original v2 native checkpoint cannot move backwards')
    for old, new in zip(a['archive_heads'], b['archive_heads']):
        if new[0] < old[0] or (new[0] == old[0] and new[1] != old[1]):
            raise ValueError('original v2 archive tip cannot change or move backwards')
    if (any(b['watermarks'].get(k, 0) < v for k,v in a['watermarks'].items())
            or (a['generation'] == b['generation'] and a != b)):
        raise ValueError('native checkpoint changed without committed compaction')


def _checkpoint_refs(source, state, cache):
    """Verify each changed tip against its actual indexed archive prefix."""
    for bucket, (sequence, pin) in enumerate(state['checkpoint']['archive_heads']):
        if cache.get(bucket) == (sequence, pin):
            continue
        if sequence == 0:
            expected = digest(canonical([source.manifest_sha256, bucket]))
        else:
            db = source._shard(bucket)
            try:
                row = db.execute('SELECT sha FROM records WHERE seq=?', (sequence,)).fetchone()
            finally:
                db.close()
            expected = row[0] if row else None
        if pin != expected:
            raise ValueError('original intermediate native archive prefix differs')
        cache[bucket] = sequence, pin


def _compaction_watermarks(state):
    return {name: state['sources'][name]['count'] for name in SOURCES if SOURCES[name][3]}


def _operation_rows(prepared, complete, protocol):
    """Narrow row linkage only; full cash/FIFO/valuation replay is separate."""
    operation, inputs, result = prepared['operation'], prepared['inputs'], complete['result']
    changes = complete['changes']
    clocks = complete['native_clocks']
    maximum = 2 if operation == 'execute' else 0 if operation == 'compact' else 1
    if len(clocks) > maximum or any(not stamp(prepared['at']) <= stamp(at) <= stamp(complete['at']) for at in clocks):
        raise ValueError('bounded causal native action clocks required')
    if clocks:prepared = dict(prepared, at=clocks[0])
    if changes and not clocks:raise ValueError('native mutation requires its actual clock')
    names = {c['source'] for c in changes}
    allowed = {
        'compact': set(), 'enqueue': {'wallet.intents'}, 'cancel_pending': {'wallet.intents'},
        'mark': {'wallet.marks', 'wallet.day_anchors', 'wallet.filters'},
        'execute': {'wallet.intents', 'wallet.fills', 'wallet.lots', 'wallet.closed_segments',
                    'wallet.day_anchors', 'wallet.filters', 'wallet.state', 'wallet.fill_order', 'wallet.fill_counter'},
    }
    if operation not in allowed or names-allowed[operation]:
        raise ValueError('native delta outside captured operation scope')
    for change in changes:
        name, old, new = change['source'], change['before'], change['after']
        if new is None:
            raise ValueError('logical native source rows cannot be deleted by compaction')
        if name in {'wallet.marks','wallet.fills','wallet.closed_segments','wallet.day_anchors','wallet.fill_order'} and old is not None:
            raise ValueError('original immutable native row cannot change')
        if name == 'wallet.state' and change['key'] != 'cash':
            raise ValueError('original native policy cannot change')
    intents = [c for c in changes if c['source'] == 'wallet.intents']
    if operation == 'enqueue':
        if type(result) is not bool or len(intents) != int(result):
            raise ValueError('original v2 enqueue/result linkage differs')
        if result and (intents[0]['before'] is not None or intents[0]['after'] != [inputs['intent_id'], inputs['pair'],
                inputs['side'], inputs['created_at'], prepared['at'], 'pending', None]):
            raise ValueError('original v2 enqueue source identity differs')
        if inputs['side'] == 'Buy' and stamp(prepared['at']) >= stamp(protocol['plan']['entry_cutoff']):
            raise ValueError('v2 Buy intent after original entry cutoff')
    if operation == 'cancel_pending':
        if result is not None or len(intents) > 1:
            raise ValueError('original v2 cancellation result differs')
        if intents:
            old = intents[0]['before']
            if (old is None or old[0] != inputs['intent_id'] or old[5] != 'pending'
                    or intents[0]['after'] != old[:4]+[prepared['at'], 'rejected', inputs['reason']]):
                raise ValueError('original v2 cancellation source differs')
    if operation in {'mark', 'execute'}:
        _market_input(inputs)
    if operation == 'mark':
        marks = [c for c in changes if c['source'] == 'wallet.marks']
        before_count = prepared['before']['sources']['wallet.marks']['count']
        if (len(marks) != 1 or marks[0]['before'] is not None or marks[0]['key'] != before_count+1
                or stamp(marks[0]['after'][1]) != stamp(prepared['at']) or parse(marks[0]['after'][2]) != result):
            raise ValueError('original v2 mark/result/clock linkage differs')
    if operation == 'execute':
        if inputs.get('entry_cutoff') != protocol['plan']['entry_cutoff']:
            raise ValueError('original execution cutoff required')
        fills = [c for c in changes if c['source'] == 'wallet.fills']
        if type(result) is not dict:
            raise ValueError('original native execution result required')
        if result.get('status') == 'filled' and not result.get('duplicate'):
            fill = result['fill']
            if (len(fills) != 1 or fills[0]['before'] is not None or fills[0]['key'] != inputs['intent_id']
                    or parse(fills[0]['after'][1]) != fill or fill['quote'] != inputs['quote']
                    or fill['filters'] != inputs['filters'] or stamp(fill['filled_at']) != stamp(prepared['at'])
                    or len(intents) != 1 or intents[0]['before'] is None
                    or intents[0]['before'][0] != inputs['intent_id'] or intents[0]['before'][5] != 'pending'
                    or fill['side'] != intents[0]['before'][2] or fill['pair'] != intents[0]['before'][1]
                    or fill['signal_time'] != intents[0]['before'][3]
                    or fill['candidate_sha256'] != protocol['candidate_sha256']
                    or (fill['side'] == 'Buy' and stamp(prepared['at']) >= stamp(protocol['plan']['entry_cutoff']))):
                raise ValueError('original v2 fill/input/result/clock linkage differs')
        elif fills:
            raise ValueError('unexpected native v2 fill')

        orders = [c for c in changes if c['source'] == 'wallet.fill_order']
        counters = [c for c in changes if c['source'] == 'wallet.fill_counter']
        if fills:
            sequence = result['fill']['fill_sequence']
            if (type(sequence) is not int or sequence != prepared['before']['sources']['wallet.fill_order']['count']+1
                    or len(orders) != 1 or orders[0]['before'] is not None
                    or orders[0]['after'] != [sequence, inputs['intent_id']]
                    or len(counters) != 1 or counters[0]['after'] != ['fill_order', sequence]
                    or counters[0]['before'] != (['fill_order',sequence-1] if sequence > 1 else None)):
                raise ValueError('original causal fill order/counter linkage differs')
        elif orders or counters:raise ValueError('fill counter changed without new fill')
        if intents:
            old, new = intents[0]['before'], intents[0]['after']
            observed = clocks[-1] if len(clocks) == 2 else clocks[0]
            if (len(intents) != 1 or old is None or old[0] != inputs['intent_id'] or old[5] != 'pending'
                    or new[:4] != old[:4] or new[4] != observed or new[5] != result['status']
                    or new[6] != result.get('reason')):
                raise ValueError('execution intent/result/actual observation linkage differs')
