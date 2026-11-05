"""Prospective wallet capture over owned native archives and bounded projections.

This is a source/checkpoint trace, not FIFO, strategy, worker or live admission.
Every mutation is prepared durably; an unknown outcome is never retried.
"""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from time import monotonic_ns

from cryptoforge.evidence_segments import SegmentPolicy, SegmentedEventLog, _guard, canonical, digest, parse, require_sha
from cryptoforge.native_paper_archive import NativeArchivePolicy, NativePaperArchive, SOURCES, _key, _runtime as native_runtime
from cryptoforge.paper_capture_v3 import (
    METADATA_BYTES, ROLES, SegmentedLifecycle, SegmentedCapturedPaperWallet,
    _lease, _metadata, _write_new, stamp,
)
from cryptoforge.paper_lifecycle import measure_resources, resource_blocker, seconds
from cryptoforge.paper_valuation_capture import _market_input, decimal_contract
from cryptoforge.paper_wallet import PaperConfig

SCHEMA = 'archived-paper-capture-v4'
MODULUS = 2**256
# The immutable archive covers SOURCES. These three bounded control tables stay
# active; day anchors belong exclusively to wallet.day_anchors.
AUXILIARY = {
    'wallet.state': ('main', 'state', ('key', 'value')),
    'wallet.filters': ('main', 'market_cache', ('pair', 'filters')),
    'worker.state': ('worker', 'worker_state', ('key', 'value')),
}
GROUPS = tuple(SOURCES) + tuple(AUXILIARY)
OPERATIONS = {'mark', 'execute', 'enqueue', 'cancel_pending', 'compact'}


def runtime_hashes():
    runner = Path(__file__).resolve().parents[2]/'scripts/audit_paper_capture_v4.py'
    return {**native_runtime(), 'archived_capture': digest(Path(__file__).read_bytes()),
            'archived_audit_runner': digest(runner.read_bytes())}


def capacity_plan(lifecycle, storage, native, start, end):
    if (type(lifecycle) is not SegmentedLifecycle or type(storage) is not SegmentPolicy
            or type(native) is not NativeArchivePolicy):
        raise ValueError('typed v4 lifecycle, event and native archive policies required')
    plan = lifecycle.plan(start, end, max_events=storage.maximum_events)
    if (plan['estimated_storage_bytes'] > storage.maximum_total_bytes
            or storage.maximum_total_bytes+native.maximum_total_bytes+1024*1024 > lifecycle.maximum_storage_bytes
            or native.maximum_records < plan['poll_slots']+1):
        raise ValueError('v4 event/native/total capacity insufficient before registration')
    return {**plan, 'native_source_archive_integrated': True,
            'full_worker_or_host_qualified': False, 'full_streaming_economic_replay_qualified': False}


def _load(root, registration_pin):
    root = Path(root).absolute()
    registration = _metadata(root/'registration.json', registration_pin)
    if (registration.get('schema_version') != SCHEMA or registration.get('root') != str(root)
            or registration.get('live_eligible') is not False):
        raise ValueError('original v4 registration required')
    protocol = _metadata(root/'protocol.json', registration['protocol_sha256'])
    lifecycle = SegmentedLifecycle.from_payload(protocol['lifecycle'])
    storage, native = SegmentPolicy(**protocol['storage_policy']), NativeArchivePolicy(**protocol['native_policy'])
    if (protocol.get('schema_version') != SCHEMA or protocol.get('root') != str(root)
            or protocol.get('role') not in ROLES or protocol.get('research_only') is not True
            or protocol.get('live_eligible') is not False
            or not stamp(protocol['registered_at']) <= stamp(registration['registered_at'])
                < stamp(protocol['start']) < stamp(protocol['end'])
            or protocol['runtime_hashes'] != runtime_hashes() or protocol['decimal_contract'] != decimal_contract()
            or protocol['plan'] != capacity_plan(lifecycle, storage, native, protocol['start'], protocol['end'])
            or resource_blocker(lifecycle, protocol['registration_resources'])):
        raise ValueError('original prospective v4 identity/runtime/budget differs')
    for pin in (protocol['candidate_sha256'], protocol['study_protocol_sha256'],
                registration['storage_manifest_sha256'], registration['native_manifest_sha256']):
        require_sha(pin)
    PaperConfig(**protocol['config'])
    return root, registration, protocol, lifecycle


def _inventory(root):
    names = {'protocol.json', 'registration.json', 'capture.lock', 'storage', 'native', 'sealed.json'}
    if root.resolve() != root or any(p.name not in names or p.is_symlink() for p in root.iterdir()):
        raise ValueError('original v4 namespace/inventory required')


def _empty():
    return {source: dict(count=0, sum_sha256='0'*64) for source in GROUPS}


def _initial(protocol, native_manifest_pin):
    summary, config = _empty(), PaperConfig(**protocol['config'])
    rows = {
        'wallet.state': [
            ['cash', str(config.capital)],
            ['policy', json.dumps(dict(candidate_sha=protocol['candidate_sha256'], config=asdict(config)), sort_keys=True, default=str)],
        ],
        'worker.state': [['identity', json.dumps(dict(candidate=protocol['candidate_sha256'], policy=protocol['worker_policy']), sort_keys=True, default=str)]],
    }
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
                alias, table, columns = AUXILIARY[name]
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
                    raise ValueError('v4 bounded active scan exhausted; no native operation attempted')
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
    # Cache only twelve accumulators and one tip per fixed shard. On restart
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
            or manifest['worker_policy'] != protocol['worker_policy'] or manifest['policy'] != protocol['native_policy']):
        raise ValueError('original v4 native source identity differs')


class ArchivedCapturedPaperWallet:
    @classmethod
    def create(cls, root, *, candidate_sha, study_protocol_sha256, role, config, worker_policy,
               lifecycle, storage_policy, native_policy, start, end, clock=None):
        require_sha(candidate_sha);require_sha(study_protocol_sha256)
        if type(config) is not PaperConfig or role not in ROLES:
            raise ValueError('explicit v4 candidate/control/stress identity required')
        root = Path(root).absolute()
        if root.resolve() != root:
            raise ValueError('new nonsymlink v4 namespace required')
        clock = clock or (lambda: datetime.now(UTC))
        now, start, end = stamp(clock()), stamp(start), stamp(end)
        plan = capacity_plan(lifecycle, storage_policy, native_policy, start, end)
        resources = measure_resources(root)
        resources['storage_bytes'] = 0
        if not now < start or resource_blocker(lifecycle, resources):
            raise ValueError('v4 prospective preregistration/resource floor required')
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        protocol = dict(schema_version=SCHEMA, root=str(root), candidate_sha256=candidate_sha,
            study_protocol_sha256=study_protocol_sha256, role=role, registered_at=now.isoformat(),
            start=start.isoformat(), end=end.isoformat(), config=parse(json.dumps(asdict(config), default=str)),
            worker_policy=parse(canonical(worker_policy)), lifecycle=lifecycle.payload(),
            storage_policy=asdict(storage_policy), native_policy=asdict(native_policy), plan=plan,
            registration_resources=resources, runtime_hashes=runtime_hashes(), decimal_contract=decimal_contract(),
            research_only=True, live_eligible=False)
        protocol_pin = _write_new(root/'protocol.json', protocol)
        source = NativePaperArchive.create(root/'native', source_protocol_sha256=protocol_pin,
            candidate_sha=candidate_sha, role=role, config=config, worker_policy=worker_policy,
            policy=native_policy, market=None, clock=clock)
        log = SegmentedEventLog.create(root/'storage', source_protocol_sha256=protocol_pin, policy=storage_policy)
        (root/'capture.lock').touch(mode=0o600, exist_ok=False)
        with source._lease(writer=True):
            state = _logical(source, _active(source), {})
        log.append('genesis', dict(at=now.isoformat(), role=role, after=state), expected_sequence=1)
        registered = stamp(clock())
        if not now <= registered < start:
            raise ValueError('v4 setup missed original preregistration window; no namespace reuse')
        pin = _write_new(root/'registration.json', dict(schema_version=SCHEMA, root=str(root),
            registered_at=registered.isoformat(), protocol_sha256=protocol_pin,
            storage_manifest_sha256=log.manifest_sha256, native_manifest_sha256=source.manifest_sha256,
            live_eligible=False))
        return cls.resume(root, expected_registration_sha256=pin, clock=clock)

    @classmethod
    def resume(cls, root, *, expected_registration_sha256, clock=None):
        root, registration, protocol, lifecycle = _load(root, expected_registration_sha256)
        obj = cls()
        obj.root, obj.registration, obj.registration_sha256 = root, registration, expected_registration_sha256
        obj.protocol, obj.protocol_sha256, obj.lifecycle = protocol, registration['protocol_sha256'], lifecycle
        obj.clock, obj._cache = clock or (lambda: datetime.now(UTC)), {}
        obj.config, obj.candidate_sha = PaperConfig(**protocol['config']), protocol['candidate_sha256']
        with obj._lock():
            _inventory(root)
            if (root/'sealed.json').exists():
                raise ValueError('sealed v4 capture cannot resume native writers')
            obj.log = SegmentedEventLog.open(root/'storage', expected_manifest_sha256=registration['storage_manifest_sha256'])
            if (obj.log.manifest['source_protocol_sha256'] != obj.protocol_sha256
                    or obj.log.policy != SegmentPolicy(**protocol['storage_policy'])):
                raise ValueError('original v4 event source identity differs')
            head = obj._head()
            if head[1] not in {'genesis', 'complete', 'terminated'}:
                raise ValueError('unfinished native v4 operation requires review; no retry or backfill')
            obj._source = NativePaperArchive.resume(root/'native', expected_manifest_sha256=registration['native_manifest_sha256'],
                market=None, clock=obj.clock)
            _source_identity(obj._source, registration, protocol)
            with obj._source._lease(writer=True):
                obj._source._check_native()
                if _logical(obj._source, _active(obj._source), obj._cache) != parse(head[2])['after']:
                    raise ValueError('uncaptured native v4 state/checkpoint change')
        return obj

    def _lock(self):return _lease(self.root, writer=True)
    _head = SegmentedCapturedPaperWallet._head
    _append = SegmentedCapturedPaperWallet._append

    def _verify(self):
        root, registration, protocol, lifecycle = _load(self.root, self.registration_sha256)
        if (root != self.root or registration != self.registration or protocol != self.protocol or lifecycle != self.lifecycle
                or self.protocol_sha256 != registration['protocol_sha256']
                or self.config != PaperConfig(**protocol['config']) or self.candidate_sha != protocol['candidate_sha256']
                or self.log.root != root/'storage' or self.log.manifest_sha256 != registration['storage_manifest_sha256']
                or self.log.policy != SegmentPolicy(**protocol['storage_policy'])
                or self._source.root != root/'native' or self._source.manifest_sha256 != registration['native_manifest_sha256']):
            raise ValueError('original v4 in-memory identity differs')
        _inventory(root)
        _source_identity(self._source, registration, protocol)
        self._source._identity()

    def _resources(self):
        measured, total, count = measure_resources(self.root), 0, 0
        for path in self.root.rglob('*'):
            count += 1
            if path.is_symlink() or count > self.log.policy.maximum_segments+self._source.policy.shards+32:
                raise ValueError('bounded v4 source inventory required')
            if path.is_file():
                total += _guard(path, limit=max(64*1024*1024, self.log.policy.maximum_segment_bytes)).st_size
        return {**measured, 'storage_bytes': total}

    def _operation(self, operation, inputs):
        if operation not in OPERATIONS:
            raise ValueError('known v4 native operation required')
        inputs = parse(canonical(inputs))
        with self._lock(), self._source._lease(writer=True):
            self._verify()
            head = self._head()
            if head[1] not in {'genesis', 'complete'}:
                raise ValueError('unfinished or terminated v4 operation; no retry')
            if head[0]+3 > self.log.policy.maximum_events:
                raise ValueError('v4 global event budget exhausted before operation')
            previous = parse(head[2])
            active_before = _active(self._source)
            before = _logical(self._source, active_before, self._cache)
            if before != previous['after']:
                raise ValueError('uncaptured native v4 state/checkpoint change')
            now, end = stamp(self.clock()), stamp(self.protocol['end'])
            if (now < stamp(previous['at']) or not stamp(self.protocol['start']) <= now <= end
                    or (now == end and operation != 'mark')):
                raise ValueError('v4 operation outside original prospective window')
            if now >= stamp(self.protocol['plan']['entry_cutoff']):
                intent = active_before['wallet.intents'].get(inputs.get('intent_id'))
                if (operation == 'enqueue' and inputs['side'] == 'Buy') or (operation == 'execute' and intent and intent[2] == 'Buy'):
                    raise ValueError('v4 cutoff forbids new Buy intents/fills')
            slot = (self.protocol['plan']['poll_slots'] if now == end else
                    int(seconds(now-stamp(self.protocol['start']))//self.lifecycle.poll_seconds))
            count = previous.get('slot_operations', 0)+1 if previous.get('slot') == slot else 1
            resources = self._resources()
            reserve = (8*self.log.policy.maximum_record_bytes+METADATA_BYTES
                       +3*self._source.policy.maximum_active_bytes+2*self._source.policy.maximum_batch_bytes)
            with self.log._lease(writer=False):
                db = self.log._db(writer=False)
                try:storage_full = self.log._storage(db)+8*self.log.policy.maximum_record_bytes+METADATA_BYTES > self.log.policy.maximum_total_bytes
                finally:db.close()
            rate_full = count > (1 if now == end else self.lifecycle.maximum_operations_per_poll)
            if rate_full or storage_full or resource_blocker(self.lifecycle, resources, reserve_bytes=reserve):
                self._terminate_locked('operation_rate_budget' if rate_full else 'resource_budget', resources=resources)
                raise ValueError('v4 resource/rate budget terminated capture')
            fields = dict(slot=slot, slot_operations=count, resources=resources)
            prepared = self._append('prepared', dict(at=now.isoformat(), operation=operation, inputs=inputs, before=before, **fields))
            wallet = self._source.wallet
            wallet.clock = lambda: now
            started = monotonic_ns()
            try:
                if operation == 'mark':result = wallet.mark(inputs['quotes'], inputs['filters'])
                elif operation == 'execute':result = wallet.execute(inputs['intent_id'], inputs['quote'], inputs['filters'])
                elif operation == 'enqueue':result = wallet.enqueue(inputs['intent_id'], inputs['pair'], inputs['side'], created_at=stamp(inputs['created_at']))
                elif operation == 'cancel_pending':result = wallet.cancel_pending(inputs['intent_id'], inputs['reason'])
                else:result = self._source.compact()
            finally:
                wallet.clock = self.clock
            elapsed, completed = monotonic_ns()-started, stamp(self.clock())
            if not now <= completed <= end:
                raise ValueError('native v4 completion outside window; review required')
            active_after = _active(self._source)
            after = _logical(self._source, active_after, self._cache)
            changes = _delta(self._source, active_before, active_after)
            if _apply(before['sources'], changes, maximum_bytes=self.log.policy.maximum_record_bytes) != after['sources']:
                raise ValueError('native v4 delta/checkpoint linkage differs; review required')
            self._append('complete', dict(at=completed.isoformat(), prepared_seq=prepared, after=after,
                changes=changes, result=result, operation_wall_ns=elapsed, **fields))
            if elapsed > self.lifecycle.maximum_operation_wall_seconds*1000000000:
                self._terminate_locked('operation_wall_budget')
                raise ValueError('v4 native wall budget exceeded')
            return result

    def mark(self, quotes, filters_by_pair=None):
        return self._operation('mark', _market_input(dict(quotes=quotes, filters=filters_by_pair or {})))

    def execute(self, intent_id, quote, filters):
        return self._operation('execute', _market_input(dict(intent_id=intent_id, quote=quote, filters=filters)))

    def enqueue(self, intent_id, pair, side, *, created_at):
        return self._operation('enqueue', dict(intent_id=intent_id, pair=pair, side=side, created_at=stamp(created_at).isoformat()))

    def cancel_pending(self, intent_id, reason):
        return self._operation('cancel_pending', dict(intent_id=intent_id, reason=reason))

    def compact(self):return self._operation('compact', {})

    def _terminate_locked(self, reason, *, resources=None):
        if reason not in {'completed', 'operator_abort', 'resource_budget', 'operation_rate_budget', 'operation_wall_budget'}:
            raise ValueError('explicit v4 terminal reason required')
        head, now = self._head(), stamp(self.clock())
        if head[1] not in {'genesis', 'complete'}:
            raise ValueError('unfinished or terminated v4 capture cannot terminate again')
        event, end = parse(head[2]), stamp(self.protocol['end'])
        if (not max(stamp(event['at']), stamp(self.protocol['start'])) <= now <= end+timedelta(seconds=self.lifecycle.finalization_grace_seconds)
                or (reason == 'completed' and now < end)):
            raise ValueError('v4 terminal outside original bounds')
        after = _logical(self._source, _active(self._source), self._cache)
        if after != event['after']:
            raise ValueError('uncaptured v4 native change before terminal')
        seq = self._append('terminated', dict(at=now.isoformat(), reason=reason, after=after, resources=resources))
        return dict(status='terminated', sequence=seq, reason=reason, live_admission_granted=False)

    def terminate(self, reason):
        with self._lock(), self._source._lease(writer=True):
            self._verify()
            return self._terminate_locked(reason)

    def finalize(self):
        with self._lock(), self._source._lease(writer=True):
            self._verify()
            head = self._head()
            now, end = stamp(self.clock()), stamp(self.protocol['end'])
            if head[1] != 'terminated' or not end <= now <= end+timedelta(seconds=self.lifecycle.finalization_grace_seconds):
                raise ValueError('original v4 terminal/end window required before seal')
            terminal = parse(head[2])['after']
            if _logical(self._source, _active(self._source), self._cache) != terminal:
                raise ValueError('uncaptured native change before source seal')
            native_seal = self._source.seal()
            after = _logical(self._source, _active(self._source), self._cache)
            if (after['sources'] != terminal['sources']
                    or after['checkpoint']['generation'] != terminal['checkpoint']['generation']+1):
                raise ValueError('final source compaction changed logical history')
            receipt = dict(schema_version=SCHEMA, registration_sha256=self.registration_sha256,
                protocol_sha256=self.protocol_sha256, native_seal_sha256=native_seal['seal_sha256'],
                native_after=after, **self.log.seal())
            pin = _write_new(self.root/'sealed.json', receipt)
            return {**receipt, 'seal_sha256': pin, 'live_admission_granted': False}


def _transition(before, after):
    if set(before) != {'sources', 'checkpoint'} or set(after) != {'sources', 'checkpoint'}:
        raise ValueError('original v4 source checkpoint fields required')
    for state in (before, after):
        if set(state['sources']) != set(GROUPS):
            raise ValueError('original v4 source groups required')
        for value in state['sources'].values():
            if set(value) != {'count', 'sum_sha256'} or type(value['count']) is not int or not 0 <= value['count'] < 2**63:
                raise ValueError('original v4 logical source count required')
            require_sha(value['sum_sha256'])
        point = state['checkpoint']
        if (set(point) != {'generation', 'watermarks', 'archive_heads'} or type(point['generation']) is not int
                or not 0 <= point['generation'] < 2**63 or type(point['archive_heads']) is not list
                or not 1 <= len(point['archive_heads']) <= 64 or type(point['watermarks']) is not dict
                or any(k not in SOURCES or not SOURCES[k][3] or type(v) is not int or not 0 <= v < 2**63
                       for k,v in point['watermarks'].items())):
            raise ValueError('original v4 source checkpoint required')
        for head in point['archive_heads']:
            if type(head) is not list or len(head) != 2 or type(head[0]) is not int or head[0] < 0:
                raise ValueError('original v4 native archive head required')
            require_sha(head[1])
    a, b = before['checkpoint'], after['checkpoint']
    if b['generation'] < a['generation'] or len(a['archive_heads']) != len(b['archive_heads']):
        raise ValueError('original v4 native checkpoint cannot move backwards')
    for old, new in zip(a['archive_heads'], b['archive_heads']):
        if new[0] < old[0] or (new[0] == old[0] and new[1] != old[1]):
            raise ValueError('original v4 archive tip cannot change or move backwards')
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
    names = {c['source'] for c in changes}
    allowed = {
        'compact': set(), 'enqueue': {'wallet.intents'}, 'cancel_pending': {'wallet.intents'},
        'mark': {'wallet.marks', 'wallet.day_anchors', 'wallet.filters'},
        'execute': {'wallet.intents', 'wallet.fills', 'wallet.lots', 'wallet.closed_segments',
                    'wallet.day_anchors', 'wallet.filters', 'wallet.state'},
    }
    if operation not in allowed or names-allowed[operation]:
        raise ValueError('native delta outside captured operation scope')
    for change in changes:
        name, old, new = change['source'], change['before'], change['after']
        if new is None:
            raise ValueError('logical native source rows cannot be deleted by compaction')
        if name in {'wallet.marks','wallet.fills','wallet.closed_segments','wallet.day_anchors'} and old is not None:
            raise ValueError('original immutable native row cannot change')
        if name == 'wallet.state' and change['key'] != 'cash':
            raise ValueError('original native policy cannot change')
    intents = [c for c in changes if c['source'] == 'wallet.intents']
    if operation == 'enqueue':
        if type(result) is not bool or len(intents) != int(result):
            raise ValueError('original v4 enqueue/result linkage differs')
        if result and (intents[0]['before'] is not None or intents[0]['after'] != [inputs['intent_id'], inputs['pair'],
                inputs['side'], inputs['created_at'], prepared['at'], 'pending', None]):
            raise ValueError('original v4 enqueue source identity differs')
        if inputs['side'] == 'Buy' and stamp(prepared['at']) >= stamp(protocol['plan']['entry_cutoff']):
            raise ValueError('v4 Buy intent after original entry cutoff')
    if operation == 'cancel_pending':
        if result is not None or len(intents) > 1:
            raise ValueError('original v4 cancellation result differs')
        if intents:
            old = intents[0]['before']
            if (old is None or old[0] != inputs['intent_id'] or old[5] != 'pending'
                    or intents[0]['after'] != old[:4]+[prepared['at'], 'rejected', inputs['reason']]):
                raise ValueError('original v4 cancellation source differs')
    if operation in {'mark', 'execute'}:
        _market_input(inputs)
    if operation == 'mark':
        marks = [c for c in changes if c['source'] == 'wallet.marks']
        before_count = prepared['before']['sources']['wallet.marks']['count']
        if (len(marks) != 1 or marks[0]['before'] is not None or marks[0]['key'] != before_count+1
                or stamp(marks[0]['after'][1]) != stamp(prepared['at']) or parse(marks[0]['after'][2]) != result):
            raise ValueError('original v4 mark/result/clock linkage differs')
    if operation == 'execute':
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
                raise ValueError('original v4 fill/input/result/clock linkage differs')
        elif fills:
            raise ValueError('unexpected native v4 fill')


def audit_archived_capture(root, *, expected_registration_sha256, expected_seal_sha256=None, clock=None):
    """Sealed read-only trace audit. No economic or worker admission is granted."""
    root, registration, protocol, lifecycle = _load(root, expected_registration_sha256)
    output = dict(schema_version='archived-paper-capture-audit-v4', registration_sha256=expected_registration_sha256,
        protocol_sha256=registration['protocol_sha256'], role=protocol['role'], source_checkpoint_trace_pass=False,
        paper_evidence_pass=False, economic_profitability_established=False, live_admission_granted=False,
        full_fifo_replay_pass=False, coverage_evidence_pass=False, full_worker_or_host_qualified=False)
    if stamp((clock or (lambda: datetime.now(UTC)))()) < stamp(protocol['end']):
        return {**output, 'status': 'sealed_until_capture_end', 'performance_hidden': True}
    with _lease(root, writer=False):
        _inventory(root)
        seal = _metadata(root/'sealed.json', expected_seal_sha256)
        if (seal.get('schema_version') != SCHEMA or seal.get('registration_sha256') != expected_registration_sha256
                or seal.get('protocol_sha256') != registration['protocol_sha256']):
            raise ValueError('original v4 final seal identity required')
        log = SegmentedEventLog._load(root/'storage', registration['storage_manifest_sha256'])
        if (log.manifest['source_protocol_sha256'] != registration['protocol_sha256']
                or log.policy != SegmentPolicy(**protocol['storage_policy'])):
            raise ValueError('original v4 event source differs')
        source = NativePaperArchive.reader(root/'native', expected_manifest_sha256=registration['native_manifest_sha256'],
            expected_seal_sha256=seal['native_seal_sha256'])
        _source_identity(source, registration, protocol)
        state, pending, terminal, last_at = None, None, None, stamp(protocol['registered_at'])
        count, operations, previous_slot, slot_count, wall_pass = 0, 0, None, 0, True
        prefix_cache = {}
        for record in log.iter_events(expected_head_sha256=seal['head_sha256'], expected_catalog_sha256=seal['catalog_sha256']):
            count += 1
            kind, event = record['kind'], record['payload']
            at = stamp(event['at'])
            if at < last_at or terminal is not None:
                raise ValueError('original v4 causal order differs')
            last_at = at
            if count == 1:
                if kind != 'genesis' or at != stamp(protocol['registered_at']) or event['role'] != protocol['role']:
                    raise ValueError('original v4 genesis required')
                state = event['after'];_transition(state, state)
                if state != _initial(protocol, registration['native_manifest_sha256']):
                    raise ValueError('original empty v4 genesis/config state differs')
                _checkpoint_refs(source, state, prefix_cache)
                continue
            if kind == 'terminated':
                if (pending is not None or event['after'] != state
                        or event['reason'] not in {'completed','operator_abort','resource_budget','operation_rate_budget','operation_wall_budget'}
                        or not stamp(protocol['start']) <= at <= stamp(protocol['end'])+timedelta(seconds=lifecycle.finalization_grace_seconds)
                        or (event['reason'] == 'completed' and at < stamp(protocol['end']))):
                    raise ValueError('original v4 terminal bounds/state differ')
                terminal = event
                continue
            if kind == 'prepared':
                if (pending is not None or event['before'] != state or event['operation'] not in OPERATIONS
                        or not stamp(protocol['start']) <= at <= stamp(protocol['end'])
                        or (at == stamp(protocol['end']) and event['operation'] != 'mark')):
                    raise ValueError('original v4 preparation/state/window differs')
                slot = (protocol['plan']['poll_slots'] if at == stamp(protocol['end']) else
                        int(seconds(at-stamp(protocol['start']))//lifecycle.poll_seconds))
                slot_count = slot_count+1 if previous_slot == slot else 1
                reserve = (8*log.policy.maximum_record_bytes+METADATA_BYTES
                           +3*source.policy.maximum_active_bytes+2*source.policy.maximum_batch_bytes)
                if (event['slot'] != slot or event['slot_operations'] != slot_count
                        or slot_count > (1 if at == stamp(protocol['end']) else lifecycle.maximum_operations_per_poll)
                        or resource_blocker(lifecycle, event['resources'], reserve_bytes=reserve)):
                    raise ValueError('original v4 slot/resource bounds differ')
                previous_slot, pending = slot, (count, event)
                continue
            if (kind != 'complete' or pending is None or event['prepared_seq'] != pending[0]
                    or any(event[k] != pending[1][k] for k in ('slot','slot_operations','resources'))
                    or not stamp(pending[1]['at']) <= at <= stamp(protocol['end'])
                    or type(event['operation_wall_ns']) is not int or event['operation_wall_ns'] < 0):
                raise ValueError('original v4 completion/preparation differs')
            _transition(state, event['after'])
            if (event['after']['checkpoint']['generation'] > state['checkpoint']['generation']
                    and event['after']['checkpoint']['watermarks'] != _compaction_watermarks(state)):
                raise ValueError('original native compaction watermark differs from pre-operation rows')
            _checkpoint_refs(source, event['after'], prefix_cache)
            if _apply(state['sources'], event['changes'], maximum_bytes=log.policy.maximum_record_bytes) != event['after']['sources']:
                raise ValueError('original v4 native delta/commitment differs')
            _operation_rows(pending[1], event, protocol)
            wall_pass &= event['operation_wall_ns'] <= lifecycle.maximum_operation_wall_seconds*1000000000
            state, pending, operations = event['after'], None, operations+1
        if pending is not None or terminal is None or count != seal['sequence']:
            raise ValueError('original completed v4 trace required')
        _transition(state, seal['native_after'])
        if (seal['native_after']['sources'] != state['sources']
                or seal['native_after']['checkpoint']['generation'] != state['checkpoint']['generation']+1):
            raise ValueError('final native source compaction changed logical history')
        if seal['native_after']['checkpoint']['watermarks'] != _compaction_watermarks(state):
            raise ValueError('final native compaction watermark differs from original rows')
        _checkpoint_refs(source, seal['native_after'], prefix_cache)
        # Full source union is streamed once, independently of the writer cache.
        summary = _empty()
        for name in SOURCES:
            for row in source.iter_rows(name):_adjust(summary, name, _valid_row(name, row), 1)
        with source._lease(writer=False):
            active = _active(source)
            for name in AUXILIARY:
                for row in active[name].values():_adjust(summary, name, row, 1)
            if dict(sources=summary, checkpoint=_checkpoint(source)) != seal['native_after']:
                raise ValueError('final native sources/checkpoint differ from original capture')
            source._check_seal();source._check_native()
        _load(root, expected_registration_sha256)
        if _metadata(root/'sealed.json', expected_seal_sha256) != seal:
            raise ValueError('v4 seal changed during audit')
    return {**output, 'status': 'archived_source_checkpoint_trace_replayed', 'performance_hidden': False,
        'source_checkpoint_trace_pass': True, 'events_checked': count, 'operations_checked': operations,
        'source_counts': {name: value['count'] for name, value in summary.items()},
        'terminal_reason': terminal['reason'], 'operation_wall_budget_pass': wall_pass,
        'scope': 'wallet_source_delta_and_archive_checkpoint_only_not_full_economic_coverage_or_worker_admission'}
