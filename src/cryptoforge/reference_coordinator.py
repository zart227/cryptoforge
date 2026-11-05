"""Bounded, restartable source-to-delivery coordination in a NEW namespace.

Diagnostic consumers acknowledge persisted input reads only. No price forecast is
converted to a cash decision; prospective source-only mode never acknowledges a
worker. An interrupted operation is explicit and blocks further mutation.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
from time import monotonic

from cryptoforge.local_source_provenance import canonical, digest, parse, read_file, sha, stamp, _new_root, _sync
from cryptoforge.reference_source_ledger import (FLAGS, ReferenceLedger, ReferencePolicy,
    audit_reference_ledger, _environment, _sources_ready)
from cryptoforge.reference_sources import INTERVAL_MS
from cryptoforge.reference_delivery import ReferenceDelivery, DeliveryPolicy, ROLES, _paths as delivery_paths
from cryptoforge.reference_delivery_source import SourceReplay

SCHEMA = 'reference-coordinator-v1'
GATES = dict(worker_execution_qualified=False, strategy_opportunity_completeness_verified=False,
             cash_entry_contract_available=False, **FLAGS)
OPERATIONS = {'poll', 'forecast', 'ingest', 'offer', 'read', 'ack'}
REF_KEYS = {'root', 'manifest_sha256', 'registration_sha256', 'database_sha256', 'head_sha256'}


@dataclass(frozen=True)
class CoordinatorPolicy:
    maximum_events: int = 2048
    maximum_journal_bytes: int = 16 * 1024**2
    maximum_packet_files: int = 192
    maximum_packet_bytes: int = 8 * 1024**2
    maximum_total_packet_bytes: int = 64 * 1024**2
    maximum_ingests_per_step: int = 2
    maximum_batches_per_role_per_step: int = 1
    maximum_steps: int = 360
    maximum_run_seconds: int = 1800
    minimum_step_seconds: int = 5
    minimum_free_disk_mb: int = 2048

    def __post_init__(self):
        limits = dict(maximum_events=(16, 10000), maximum_journal_bytes=(4096, 64*1024**2),
            maximum_packet_files=(3, 1024), maximum_packet_bytes=(4096, 16*1024**2),
            maximum_total_packet_bytes=(4096, 256*1024**2), maximum_ingests_per_step=(1, 8),
            maximum_batches_per_role_per_step=(1, 4), maximum_steps=(1, 360),
            maximum_run_seconds=(1, 1800), minimum_step_seconds=(5, 300), minimum_free_disk_mb=(2048, 1048576))
        if any(type(v) is not int or not limits[k][0] <= v <= limits[k][1] for k, v in asdict(self).items()):
            raise ValueError('explicit bounded coordinator policy required')
        if self.maximum_packet_bytes > self.maximum_total_packet_bytes:
            raise ValueError('packet reserve must fit total packet budget')


def _paths():
    return dict(delivery_paths(), **{'reference_coordinator.py': Path(__file__),
        'coordinate_reference_sources.py': Path(__file__).resolve().parents[2]/'scripts/coordinate_reference_sources.py'})


def runtime_hashes():
    value = {n: digest(p.read_bytes()) for n, p in _paths().items()}
    if value != _LOADED_RUNTIME:
        raise ValueError('coordinator runtime changed; new process/namespace required')
    return value


def _descriptor(value, initial):
    if type(value) is not dict or set(value) != REF_KEYS:
        raise ValueError('exact original component descriptor required')
    if any(value[k] != initial[k] for k in ('root', 'manifest_sha256', 'registration_sha256')):
        raise ValueError('coordinator component identity changed')
    for k in REF_KEYS-{'root'}:
        sha(value[k])


def _atomic_new(path, value):
    """Same-directory durable rename. Leftover temporary files block restart."""
    raw = canonical(value)
    temporary = path.with_name('.'+path.name+'.tmp')
    if path.exists():
        raise ValueError('immutable coordinator record already exists')
    fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.rename(temporary, path)
    _sync(path.parent)
    return digest(raw)


def _input_receipt(packet, raw, at):
    return dict(schema_version='diagnostic-reference-input-read-v1', read_at=at,
        delivery=packet['delivery'], input_sha256=digest(raw), input_bytes=len(raw),
        source_event_sha256=digest(canonical(packet['source_events'])),
        source_sequence=packet['source_view']['source_sequence'],
        forecast_ids=[r['payload']['forecast_id'] for r in packet['source_events'] if r['kind']=='forecast'],
        closed_candles_ready=packet['closed_candles_ready'], **GATES)


class ReferenceCoordinator:
    @classmethod
    def create(cls, root, *, pairs=(), artifact_raw=None, start=None, end=None,
               diagnostic_consumers=False, policy=None, source_policy=None, delivery_policy=None, clock=None):
        now = stamp((clock or (lambda: datetime.now(UTC)))())
        if type(diagnostic_consumers) is not bool or diagnostic_consumers and start is not None:
            raise ValueError('input consumers require an explicit diagnostic namespace')
        policy = policy or CoordinatorPolicy()
        root = Path(root).absolute()
        parent = root.parent
        while not parent.exists():
            parent = parent.parent
        if shutil.disk_usage(parent).free < policy.minimum_free_disk_mb*1024**2 + policy.maximum_packet_bytes*3:
            raise ValueError('coordinator disk reserve preserved')
        runtime = runtime_hashes()
        root = _new_root(root)
        (root/'journal').mkdir(mode=0o700)
        (root/'packets').mkdir(mode=0o700)
        (root/'writer.lock').touch(mode=0o600)
        source = ReferenceLedger.create(root/'source', pairs=pairs, artifact_raw=artifact_raw,
            start=start, end=end, policy=source_policy, clock=clock)
        source_ref = source.receipt()['reference']
        queue = ReferenceDelivery.create(root/'delivery', source_ref, policy=delivery_policy,
            diagnostic=start is None, clock=clock)
        queue_ref = queue.receipt()['reference']
        forecast_pairs = [] if artifact_raw is None else [p for p in source.manifest['pairs'] if p in parse(artifact_raw)['pairs']]
        value = dict(schema_version=SCHEMA, root=str(root), registered_at=now.isoformat(),
            mode='diagnostic' if start is None else 'prospective_source_only',
            start=source.manifest['start'], end=source.manifest['end'],
            diagnostic_consumers=diagnostic_consumers, policy=asdict(policy),
            source_reference=source_ref, delivery_reference=queue_ref,
            forecast_pairs=forecast_pairs, runtime=runtime, environment=_environment(), **GATES)
        pin = _atomic_new(root/'manifest.json', value)
        completed = stamp((clock or (lambda: datetime.now(UTC)))())
        if completed < now or start is not None and completed >= stamp(start):
            raise ValueError('coordinator setup missed original prospective start')
        registration = _atomic_new(root/'registered.json', dict(manifest_sha256=pin, registered_at=completed.isoformat()))
        final = stamp((clock or (lambda: datetime.now(UTC)))())
        if final < completed or start is not None and final >= stamp(start):
            (root/'registered.json').unlink()
            _sync(root)
            raise ValueError('coordinator registration missed original prospective start')
        return cls.open(dict(root=str(root), manifest_sha256=pin, registration_sha256=registration,
            sequence=0, head_sha256=pin), clock=clock)

    @classmethod
    def open(cls, reference, *, clock=None, _recover=False):
        if type(reference) is not dict or set(reference) != {'root', 'manifest_sha256', 'registration_sha256', 'sequence', 'head_sha256'}:
            raise ValueError('exact external coordinator checkpoint required')
        if type(reference['sequence']) is not int or reference['sequence'] < 0:
            raise ValueError('typed coordinator sequence required')
        root = Path(reference['root']).absolute()
        raw = read_file(root/'manifest.json', maximum=65536)
        ready = read_file(root/'registered.json', maximum=4096)
        if digest(raw) != sha(reference['manifest_sha256']) or digest(ready) != sha(reference['registration_sha256']):
            raise ValueError('original coordinator manifest/registration changed')
        value, registered = parse(raw), parse(ready)
        if (root.resolve() != root or value['root'] != str(root) or value['schema_version'] != SCHEMA
                or value['runtime'] != runtime_hashes() or value['environment'] != _environment()
                or registered['manifest_sha256'] != reference['manifest_sha256']
                or any(value.get(k) is not False for k in GATES)
                or type(value['diagnostic_consumers']) is not bool
                or value['mode'] not in ('diagnostic', 'prospective_source_only')
                or value['mode'] != 'diagnostic' and value['diagnostic_consumers']
                or not stamp(value['registered_at']) <= stamp(registered['registered_at'])
                or not stamp(value['start']) < stamp(value['end'])
                or value['mode'] != 'diagnostic' and not stamp(registered['registered_at']) < stamp(value['start'])):
            raise ValueError('original coordinator contract differs')
        obj = cls()
        obj.root, obj.manifest, obj.reference = root, value, dict(reference)
        obj.policy, obj.clock = CoordinatorPolicy(**value['policy']), clock or (lambda: datetime.now(UTC))
        for key, child in (('source_reference', 'source'), ('delivery_reference', 'delivery')):
            _descriptor(value[key], value[key])
            if value[key]['root'] != str(root/child):
                raise ValueError('owned coordinator component root required')
        with obj._lease():
            obj._scan()
            if _recover:
                if reference['sequence'] not in obj.heads or obj.heads[reference['sequence']] != reference['head_sha256']:
                    raise ValueError('unknown coordinator ancestor')
            elif obj.sequence != reference['sequence'] or obj.head != reference['head_sha256']:
                raise ValueError('stale coordinator checkpoint; explicit recover required')
            obj._components()
        return obj

    @classmethod
    def recover(cls, known_reference, *, clock=None):
        obj = cls.open(known_reference, clock=clock, _recover=True)
        verified = obj.audit() if obj.pending is None else obj.receipt()
        return dict(**verified, recovery=dict(known_ancestor_head_sha256=known_reference['head_sha256'],
            recovered_head_sha256=obj.head, new_checkpoint_required=True,
            incomplete_operation=obj.pending is not None, component_pins_reproduced=True))

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock', maximum=0)
        fd = os.open(self.root/'writer.lock', os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def _scan(self):
        if {p.name for p in self.root.iterdir()} != {'manifest.json', 'registered.json', 'writer.lock', 'journal', 'packets', 'source', 'delivery'}:
            raise ValueError('coordinator inventory differs or temporary file remains')
        for name in ('journal', 'packets', 'source', 'delivery'):
            path = self.root/name
            if path.is_symlink() or not path.is_dir():
                raise ValueError('canonical owned coordinator directory required')
        names = sorted(p.name for p in (self.root/'journal').iterdir())
        if len(names) > self.policy.maximum_events or names != [f'{i:08d}.json' for i in range(1, len(names)+1)]:
            raise ValueError('coordinator journal gap/inventory/event budget differs')
        self.sequence, self.head, self.pending = 0, self.reference['manifest_sha256'], None
        self.source_ref = self.manifest['source_reference']
        self.queue_ref = self.manifest['delivery_reference']
        self.heads = {0: self.head}
        self.completed = []
        self.forecast_slots = set()
        self.last_at = stamp(parse(read_file(self.root/'registered.json'))['registered_at'])
        total, packet_bytes, expected_packets = 0, 0, set()
        started = monotonic()
        for name in names:
            if monotonic()-started > 60:
                raise ValueError('coordinator journal replay wall budget exhausted')
            raw = read_file(self.root/'journal'/name, maximum=65536)
            total += len(raw)
            if total > self.policy.maximum_journal_bytes:
                raise ValueError('coordinator journal byte budget exhausted')
            event = parse(raw)
            if set(event) != {'sequence', 'previous_sha256', 'kind', 'payload', 'sha256'}:
                raise ValueError('exact coordinator event schema required')
            value = {k: v for k, v in event.items() if k != 'sha256'}
            if (raw != canonical(event) or type(event['sequence']) is not int or event['sequence'] != self.sequence+1
                    or event['previous_sha256'] != self.head or digest(canonical(value)) != event['sha256']):
                raise ValueError('coordinator original journal chain differs')
            p = event['payload']
            at = stamp(p['at'])
            if not self.last_at <= at <= stamp(self.clock()):
                raise ValueError('coordinator journal clock differs')
            if event['kind'] == 'prepared':
                if (self.pending is not None or set(p) != {'at', 'operation', 'arguments', 'source_reference', 'delivery_reference'}
                        or p['operation'] not in OPERATIONS or p['source_reference'] != self.source_ref or p['delivery_reference'] != self.queue_ref):
                    raise ValueError('coordinator operation order differs')
                self.pending = event
            elif event['kind'] == 'completed':
                if (self.pending is None or set(p) != {'at', 'prepared_sha256', 'result', 'source_reference', 'delivery_reference'}
                        or p['prepared_sha256'] != self.pending['sha256']):
                    raise ValueError('coordinator completion lacks original prepared operation')
                for field in ('source_reference', 'delivery_reference'):
                    _descriptor(p[field], self.manifest[field])
                op = self.pending['payload']['operation']
                args = self.pending['payload']['arguments']
                if op not in ('poll', 'forecast') and p['source_reference'] != self.source_ref:
                    raise ValueError('unexpected coordinator source change')
                if op not in ('ingest', 'offer', 'ack') and p['delivery_reference'] != self.queue_ref:
                    raise ValueError('unexpected coordinator delivery change')
                if op == 'forecast':
                    self.forecast_slots.add((args['anchor_ms'], args['pair']))
                if op == 'read':
                    result = p['result']
                    identity = sha(args['delivery_id'])
                    path = self.root/'packets'/(identity+'.json')
                    packet_raw = read_file(path, maximum=self.policy.maximum_packet_bytes)
                    packet = parse(packet_raw)
                    receipt = _input_receipt(packet, packet_raw, result['receipt']['read_at'])
                    if (packet_raw != canonical(packet) or result != dict(receipt=receipt, receipt_sha256=digest(canonical(receipt)))
                            or packet['delivery']['role'] != args['role'] or packet['delivery']['delivery_id'] != identity
                            or not stamp(self.pending['payload']['at']) <= stamp(receipt['read_at']) <= at):
                        raise ValueError('original diagnostic input receipt differs')
                    expected_packets.add(path.name)
                    packet_bytes += len(packet_raw)
                self.source_ref, self.queue_ref = p['source_reference'], p['delivery_reference']
                self.completed.append((self.pending['payload'], p))
                self.pending = None
            else:
                raise ValueError('unknown coordinator event kind')
            self.sequence, self.head, self.last_at = event['sequence'], event['sha256'], at
            self.heads[self.sequence] = self.head
        if (len(expected_packets) > self.policy.maximum_packet_files or packet_bytes > self.policy.maximum_total_packet_bytes
                or {p.name for p in (self.root/'packets').iterdir()} != expected_packets):
            raise ValueError('diagnostic packet inventory/byte budget differs')
        self.journal_bytes, self.packet_bytes = total, packet_bytes
        self.packet_count = len(expected_packets)

    def _components(self):
        self.source = ReferenceLedger.open(self.source_ref, clock=self.clock)
        self.queue = ReferenceDelivery.open(self.queue_ref, clock=self.clock)
        if (self.source.manifest['start'] != self.manifest['start'] or self.source.manifest['end'] != self.manifest['end']
                or self.queue.manifest['source_identity'] != self.manifest['source_reference']
                or self.manifest['forecast_pairs'] != ([] if self.source.manifest['artifact_sha256'] is None else
                    [p for p in self.source.manifest['pairs'] if p in parse(read_file(self.source.root/'artifact.json', maximum=65536))['pairs']])):
            raise ValueError('coordinator source window/forecast contract differs')

    def _check(self, *, active=False):
        if self.manifest['runtime'] != runtime_hashes():
            raise ValueError('coordinator runtime changed')
        for name, pin in (('manifest.json', self.reference['manifest_sha256']), ('registered.json', self.reference['registration_sha256'])):
            if digest(read_file(self.root/name, maximum=65536)) != pin:
                raise ValueError('coordinator original static contract changed')
        if len(list((self.root/'journal').iterdir())) != self.sequence:
            raise ValueError('stale coordinator writer; reopen/recover required')
        now = stamp(self.clock())
        if now < self.last_at or now < getattr(self, '_last_clock', now):
            raise ValueError('coordinator clock moved backwards')
        self._last_clock = now
        if active and not stamp(self.manifest['start']) <= now < stamp(self.manifest['end']):
            raise ValueError('coordinator source window is not open')
        reserve = self.policy.minimum_free_disk_mb*1024**2 + 3*self.policy.maximum_packet_bytes + 2*65536
        if shutil.disk_usage(self.root).free < reserve:
            raise ValueError('coordinator disk reserve preserved')
        return now

    def _append(self, kind, payload):
        self._check()
        value = dict(sequence=self.sequence+1, previous_sha256=self.head, kind=kind, payload=payload)
        event = dict(value, sha256=digest(canonical(value)))
        raw = canonical(event)
        if (len(raw) > 65536 or self.sequence >= self.policy.maximum_events
                or self.journal_bytes+len(raw) > self.policy.maximum_journal_bytes):
            raise ValueError('coordinator journal budget exhausted')
        _atomic_new(self.root/'journal'/f'{self.sequence+1:08d}.json', event)
        self.sequence, self.head, self.last_at = event['sequence'], event['sha256'], stamp(payload['at'])
        self.journal_bytes += len(raw)
        if kind == 'prepared':
            self.pending = event
        else:
            self.completed.append((self.pending['payload'], payload))
            self.pending = None
        return event

    def _operation(self, name, arguments, invoke):
        if self.pending is not None:
            raise ValueError('incomplete coordinator operation requires explicit investigation')
        # Reserve TWO maximum records before any component mutation.
        if self.sequence+2 > self.policy.maximum_events or self.journal_bytes+2*65536 > self.policy.maximum_journal_bytes:
            raise ValueError('coordinator operation journal reserve exhausted')
        prepared = self._append('prepared', dict(at=self._check().isoformat(), operation=name, arguments=arguments,
            source_reference=self.source_ref, delivery_reference=self.queue_ref))
        result = invoke()
        source_ref = self.source.receipt()['reference']
        queue_ref = self.queue.receipt()['reference']
        self._append('completed', dict(at=self._check().isoformat(), prepared_sha256=prepared['sha256'],
            result=result, source_reference=source_ref, delivery_reference=queue_ref))
        self.source_ref, self.queue_ref = source_ref, queue_ref
        return result

    def _source_view(self):
        with self.source._lease():
            self.source._check(active=False)
            db = sqlite3.connect(f'{self.source.path.as_uri()}?mode=ro', uri=True)
            try:
                return self.source._windows(db)
            finally:
                db.close()

    def _read(self, role, identity):
        if self.packet_count >= self.policy.maximum_packet_files or self.packet_bytes+self.policy.maximum_packet_bytes > self.policy.maximum_total_packet_bytes:
            raise ValueError('diagnostic packet reserve exhausted')
        packet = self.queue.read(role, identity)
        raw = canonical(packet)
        if len(raw) > self.policy.maximum_packet_bytes:
            raise ValueError('diagnostic packet byte budget exhausted')
        _atomic_new(self.root/'packets'/(identity+'.json'), packet)
        self.packet_count += 1
        self.packet_bytes += len(raw)
        receipt = _input_receipt(packet, raw, self._check().isoformat())
        return dict(receipt=receipt, receipt_sha256=digest(canonical(receipt)))

    def step(self, *, client=None):
        """One bounded pass; never sleeps, retries a failed poll, or catches a write failure."""
        with self._lease():
            now = self._check(active=True)
            if self.pending is not None:
                raise ValueError('incomplete coordinator operation requires explicit investigation')
            complete, windows = self._source_view()
            anchor = int(now.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
            poll_due = complete is None or (complete['anchor_ms'] < anchor and stamp(complete['cooldown_until']) <= now)
            if poll_due:
                self._operation('poll', dict(anchor_ms=anchor), lambda: self.source.poll(client))
                complete, windows = self._source_view()
            if complete:
                for pair in self.manifest['forecast_pairs']:
                    slot = (complete['anchor_ms'], pair)
                    if slot in self.forecast_slots:
                        continue
                    def forecast(pair=pair):
                        if not _sources_ready(windows, self._check()):
                            return dict(status='skipped_missing_stale_or_failed_inputs', pair=pair, **GATES)
                        return dict(status='original_price_forecast', forecast=self.source.forecast(pair), **GATES)
                    self._operation('forecast', dict(anchor_ms=complete['anchor_ms'], pair=pair), forecast)
                    self.forecast_slots.add(slot)
            ingests = 0
            for _ in range(self.policy.maximum_ingests_per_step):
                if self.queue.receipt()['source_head_sha256'] == self.source_ref['head_sha256']:
                    break
                self._operation('ingest', {}, lambda: self.queue.ingest(self.source_ref))
                ingests += 1
            if self.manifest['diagnostic_consumers']:
                for role in ROLES:
                    for _ in range(self.policy.maximum_batches_per_role_per_step):
                        state = self.queue.receipt()
                        if state['role_cursors'][role]['cursor'] == state['batches']:
                            break
                        offer = self._operation('offer', dict(role=role), lambda role=role: self.queue.next(role))
                        if offer['delivery'] is None:
                            break
                        identity = offer['delivery']['delivery_id']
                        receipt = self._operation('read', dict(role=role, delivery_id=identity),
                            lambda role=role, identity=identity: self._read(role, identity))
                        self._operation('ack', dict(role=role, delivery_id=identity, receipt_sha256=receipt['receipt_sha256']),
                            lambda role=role, identity=identity, receipt=receipt: self.queue.acknowledge(role, identity,
                                worker_receipt_sha256=receipt['receipt_sha256']))
            return dict(**self._receipt(), poll_performed=poll_due, ingests_performed=ingests,
                health=self._health(complete, windows))

    def _health(self, complete, windows):
        now = self._check()
        anchor = int(now.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
        last_anchor = complete['anchor_ms'] if complete else None
        age = (now-stamp(complete['completed_at'])).total_seconds() if complete else None
        cooldown = complete is not None and now < stamp(complete['cooldown_until'])
        return dict(checked_at=now.isoformat(), last_completed_poll_anchor_ms=last_anchor,
            poll_age_seconds=age, missing_completed_tail_slots=0 if last_anchor is None else max(0, (anchor-last_anchor)//INTERVAL_MS),
            initial_poll_missing=complete is None, venue_cooldown_active=cooldown,
            closed_candles_ready=bool(complete and _sources_ready(windows, now)),
            source_head_caught_up=self.queue.receipt()['source_head_sha256'] == self.source_ref['head_sha256'],
            next_poll_not_before=(max(datetime.fromtimestamp((last_anchor+INTERVAL_MS)/1000, UTC), stamp(complete['cooldown_until'])).isoformat() if complete else now.isoformat()),
            scope='observed_source_tail_only_not_proof_of_all_strategy_opportunities', **GATES)

    def _receipt(self):
        return dict(reference=dict(self.reference, sequence=self.sequence, head_sha256=self.head),
            source_reference=self.source_ref, delivery_reference=self.queue_ref,
            journal_events=self.sequence, journal_bytes=self.journal_bytes,
            diagnostic_packets=self.packet_count, diagnostic_packet_bytes=self.packet_bytes,
            pending_operation=self.pending['payload']['operation'] if self.pending else None,
            diagnostic_input_consumers=self.manifest['diagnostic_consumers'], **GATES)

    def receipt(self):
        with self._lease():
            self._check()
            return self._receipt()

    def audit(self):
        with self._lease():
            self._check()
            self._scan()
            self._components()
            if self.pending is not None:
                raise ValueError('incomplete coordinator operation requires explicit investigation')
            source = audit_reference_ledger(self.source_ref, clock=self.clock)
            queue = self.queue.audit()
            reads = {}
            started = monotonic()
            with sqlite3.connect(f'{self.queue.path.as_uri()}?mode=ro', uri=True) as db:
                offers = {}
                for raw, in db.execute("SELECT payload FROM events WHERE kind='offer' ORDER BY seq"):
                    d = parse(raw)['delivery']
                    offers[d['delivery_id']] = d
                for prepared, completed in self.completed:
                    if monotonic()-started > 120:
                        raise ValueError('coordinator receipt replay wall budget exhausted')
                    if prepared['operation'] == 'read':
                        result = completed['result']
                        receipt = result['receipt']
                        d = receipt['delivery']
                        identity = d['delivery_id']
                        if offers.get(identity) != d:
                            raise ValueError('diagnostic receipt original role offer differs')
                        packet = parse(read_file(self.root/'packets'/(identity+'.json'), maximum=self.policy.maximum_packet_bytes))
                        row = db.execute('SELECT payload,sha FROM batches WHERE seq=?', (d['batch_sequence'],)).fetchone()
                        if row is None or parse(row[0]) != packet['batch'] or row[1] != d['batch_sha256']:
                            raise ValueError('diagnostic receipt original batch differs')
                        events = [dict(sequence=s, kind=k, payload=parse(p), previous_sha256=prior, sha256=h)
                            for s,k,p,prior,h in db.execute('SELECT * FROM source_events WHERE seq BETWEEN ? AND ? ORDER BY seq',
                                (packet['batch']['source_from'], packet['batch']['source_to']))]
                        with SourceReplay(self.queue.source_manifest, self.queue.artifact, parent=self.root,
                                maximum_database_bytes=self.queue.policy.maximum_scratch_database_bytes) as replay:
                            for row in db.execute('SELECT * FROM source_events WHERE seq<=? ORDER BY seq', (packet['batch']['source_to'],)):
                                replay.feed(row)
                            view = replay.view()
                        if canonical(events) != canonical(packet['source_events']) or canonical(view) != canonical(packet['source_view']):
                            raise ValueError('diagnostic receipt original source replay differs')
                        # Preserve freshness as observed at read time, never at
                        # replay time. Allow the exact threshold to pass during
                        # the bounded read; both endpoint values are causal.
                        readiness = {stamp(self.manifest['start']) <= stamp(t) <= stamp(self.manifest['end'])
                            and _sources_ready(view['windows'], stamp(t))
                            for t in (prepared['at'], receipt['read_at'])}
                        if (type(packet['closed_candles_ready']) is not bool
                                or packet['closed_candles_ready'] not in readiness
                                or any(packet.get(k) is not False for k in FLAGS)
                                or packet['worker_prediction_batch_available'] is not False):
                            raise ValueError('diagnostic packet cannot grant worker or economic admission')
                        reads[identity] = result['receipt_sha256']
                    elif prepared['operation'] == 'ack':
                        args = prepared['arguments']
                        if reads.get(args['delivery_id']) != args['receipt_sha256']:
                            raise ValueError('ack lacks durable original diagnostic input receipt')
                        ack = db.execute('SELECT payload FROM acks WHERE delivery_id=?', (args['delivery_id'],)).fetchone()
                        if ack is None or parse(ack[0]) != completed['result']['acknowledgement'] or parse(ack[0])['worker_receipt_sha256'] != args['receipt_sha256']:
                            raise ValueError('diagnostic acknowledgement binding differs')
            complete, windows = self._source_view()
            return dict(**self._receipt(), journal_integrity_pass=True,
                diagnostic_input_receipt_integrity_pass=True, source_audit=source, delivery_audit=queue,
                health=self._health(complete, windows), scope='bounded_source_delivery_coordination_only')


_LOADED_RUNTIME = {n: digest(p.read_bytes()) for n, p in _paths().items()}
