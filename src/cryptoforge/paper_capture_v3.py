"""New-namespace segmented capture adapter; no strategy or live admission.

Native wallet/worker archives and full economic/coverage replay remain separate
qualification steps. Never use this adapter to migrate a frozen v1/v2 study.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
from time import monotonic_ns

from cryptoforge.evidence_segments import (
    SegmentPolicy, SegmentedEventLog, _guard, _sync_directory, _verified_frame, require_sha,
)
from cryptoforge.paper_lifecycle import PaperLifecycle, measure_resources, resource_blocker, seconds
from cryptoforge.paper_wallet import PaperConfig, PaperWallet
from cryptoforge.paper_valuation_capture import (
    CapturedPaperWallet, MAX_BYTES, _inventory_after, _market_input, _read_db, _sources,
    _wallet_state, canonical, decimal_contract, digest, fingerprint, parse, replay_liquidation,
    runtime_hashes as valuation_runtime_hashes, stamp,
)

SCHEMA = 'segmented-paper-capture-v3'
ROLES = {'candidate', 'control', 'stress'}
METADATA_BYTES = 65536


@dataclass(frozen=True)
class SegmentedLifecycle(PaperLifecycle):
    """V3-only total storage extension; the original lifecycle stays unchanged."""
    def __post_init__(self):
        if type(self.maximum_storage_bytes) is not int or not 65536 <= self.maximum_storage_bytes <= 2**63-1:
            raise ValueError('explicit bounded v3 total storage required')
        # Reuse every cadence/cost/resource rule, extending ONLY the total cap in
        # this new schema. This does not alter the native wallet's 64MiB guard.
        fields = asdict(self)
        fields['maximum_storage_bytes'] = min(self.maximum_storage_bytes, MAX_BYTES)
        normalized = PaperLifecycle(**fields)
        if self.minimum_free_disk_bytes < self.maximum_storage_bytes:
            raise ValueError('free disk floor must cover the v3 total budget')
        object.__setattr__(self, 'minimum_known_time_fraction', normalized.minimum_known_time_fraction)

    def payload(self):
        return dict(schema_version='segmented-paper-lifecycle-v3', **asdict(self))

    @classmethod
    def from_payload(cls, payload):
        payload = dict(payload)
        if payload.pop('schema_version', None) != 'segmented-paper-lifecycle-v3':
            raise ValueError('original v3 lifecycle required')
        return cls(**payload)


def runtime_hashes():
    runner = Path(__file__).resolve().parents[2]/'scripts/audit_paper_capture_v3.py'
    return {**valuation_runtime_hashes(), 'segmented_capture': digest(Path(__file__).read_bytes()),
            'segmented_storage': digest(Path(__file__).with_name('evidence_segments.py').read_bytes()),
            'segmented_audit_runner': digest(runner.read_bytes())}


def capacity_plan(lifecycle, storage, start, end):
    if type(lifecycle) is not SegmentedLifecycle or type(storage) is not SegmentPolicy:
        raise ValueError('typed v3 lifecycle and segment policy required')
    plan = lifecycle.plan(start, end, max_events=storage.maximum_events)
    if (plan['estimated_storage_bytes'] > storage.maximum_total_bytes
            or storage.maximum_total_bytes+MAX_BYTES+1024*1024 > lifecycle.maximum_storage_bytes):
        raise ValueError('v3 total budget must cover event storage, native sources and metadata')
    return {**plan, 'native_database_limit_bytes': MAX_BYTES,
            'full_worker_or_host_qualified': False, 'native_source_archive_qualified': False}


def _write_new(path, value):
    raw = canonical(value)
    if len(raw) > METADATA_BYTES:
        raise ValueError('bounded capture metadata required')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        remaining = memoryview(raw)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError('metadata write did not advance')
            remaining = remaining[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync_directory(path.parent)
    return digest(raw)


def _metadata(path, pin):
    require_sha(pin)
    _guard(path, limit=METADATA_BYTES)
    raw = path.read_bytes()
    if digest(raw) != pin:
        raise ValueError('original capture metadata pin differs')
    value = parse(raw)
    if type(value) is not dict or raw != canonical(value):
        raise ValueError('canonical capture metadata required')
    return value


def _load(root, registration_pin):
    root = Path(root).absolute()
    registration = _metadata(root/'registration.json', registration_pin)
    if (registration.get('schema_version') != SCHEMA or registration.get('root') != str(root)
            or registration.get('live_eligible') is not False):
        raise ValueError('original v3 registration required')
    protocol = _metadata(root/'protocol.json', registration['protocol_sha256'])
    lifecycle = SegmentedLifecycle.from_payload(protocol['lifecycle'])
    storage = SegmentPolicy(**protocol['storage_policy'])
    if (protocol.get('schema_version') != SCHEMA or protocol.get('root') != str(root)
            or protocol.get('role') not in ROLES or protocol.get('research_only') is not True
            or protocol.get('live_eligible') is not False
            or not stamp(protocol['registered_at']) <= stamp(registration['registered_at'])
                < stamp(protocol['start']) < stamp(protocol['end'])
            or protocol['runtime_hashes'] != runtime_hashes()
            or protocol['decimal_contract'] != decimal_contract()
            or protocol['plan'] != capacity_plan(lifecycle, storage, protocol['start'], protocol['end'])
            or resource_blocker(lifecycle, protocol['registration_resources'])):
        raise ValueError('original prospective v3 identity/runtime/budget differs')
    for pin in (protocol['candidate_sha256'], protocol['study_protocol_sha256'], registration['storage_manifest_sha256']):
        require_sha(pin)
    PaperConfig(**protocol['config'])
    return root, registration, protocol, lifecycle


@contextmanager
def _lease(root, *, writer):
    path = root/'capture.lock'
    _guard(path, limit=0)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if writer else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def _state(path):
    value = _wallet_state(path)
    db = _read_db(path)
    try:
        value['segments'] = db.execute('SELECT count(*) FROM closed_segments').fetchone()[0]
        for table, count in (('marks', value['marks']), ('closed_segments', value['segments'])):
            if db.execute(f'SELECT coalesce(max(id),0) FROM {table}').fetchone()[0] != count:
                raise ValueError('native row IDs cannot be deleted or renumbered')
    finally:
        db.close()
    return value


def _schema_pin(path):
    db = _read_db(path)
    try:
        rows = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchmany(33)
        if len(rows) > 32:
            raise ValueError('bounded original native schema required')
        return digest(canonical(rows))
    finally:
        db.close()


def _check_native_schema(path, expected):
    require_sha(expected)
    if _schema_pin(path) != expected:
        raise ValueError('original v3 native schema differs; no repair or adoption')


def _root_inventory(root):
    allowed = {'protocol.json', 'registration.json', 'wallet.sqlite', 'capture.lock', 'storage', 'sealed.json'}
    if {path.name for path in root.iterdir()}-allowed:
        raise ValueError('unregistered v3 source file')


def _references(db, before, after, result):
    refs = dict(marks=[], fills=[], closed_segments=[])
    for table, key in (('marks', 'marks'), ('closed_segments', 'segments')):
        if after[key] < before[key] or after[key]-before[key] > 2000:
            raise ValueError('bounded monotonic native source rows required')
        for row_id, raw in db.execute(f'SELECT id,payload FROM {table} WHERE id>? AND id<=? ORDER BY id',
                                     (before[key], after[key])):
            refs[table].append(dict(id=row_id, payload_sha256=digest(raw.encode())))
        if len(refs[table]) != after[key]-before[key]:
            raise ValueError('original native source rows missing')
    if after['fills'] == before['fills']+1 and result.get('status') == 'filled' and not result.get('duplicate'):
        identity = result['fill']['intent_id']
        row = db.execute('SELECT payload FROM fills WHERE intent_id=?', (identity,)).fetchone()
        if not row or parse(row[0]) != result['fill']:
            raise ValueError('original native fill source differs')
        refs['fills'].append(dict(intent_id=identity, payload_sha256=digest(row[0].encode())))
    elif after['fills'] != before['fills']:
        raise ValueError('uncaptured native fill count')
    return refs


def _anchored_state(original, equity, at, latest_known_equity):
    state = dict(original)
    key = 'day_anchor:'+stamp(at).date().isoformat()
    if equity is not None and key not in state:
        prior = sorted(key for key in state if key.startswith('day_anchor:'))
        previous = Decimal(state[prior[-1]]) if prior else equity
        if latest_known_equity is not None:
            previous = latest_known_equity
        state[key] = str(max(equity, previous))
    return state


def _day_state(before, intent, result, at, latest_mark, latest_known_equity, config):
    """Replay native day-anchor creation without calling the native risk code."""
    if (not intent or intent['side'] != 'Buy' or result.get('duplicate')
            or result.get('status') not in {'filled', 'rejected'} or result.get('reason') == 'expired_signal'):
        return dict(before['state'])
    equity = None
    if latest_mark is None:
        if not any(Decimal(lot['qty']) > 0 for lot in before['lots']):
            equity = Decimal(before['state']['cash'])
    elif (latest_mark['equity'] is not None and timedelta(0) <= stamp(at)-stamp(latest_mark['observed_at'])
          <= timedelta(seconds=config.quote_max_age_seconds)):
        equity = Decimal(latest_mark['equity'])
    return _anchored_state(before['state'], equity, at, latest_known_equity)


class SegmentedCapturedPaperWallet(CapturedPaperWallet):
    """Existing worker API with a NEW v3 protocol and segmented event source."""
    @classmethod
    def create(cls, root, *, candidate_sha, study_protocol_sha256, role, config, lifecycle,
               storage_policy, start, end, clock=None):
        require_sha(candidate_sha)
        require_sha(study_protocol_sha256)
        if role not in ROLES or type(config) is not PaperConfig:
            raise ValueError('explicit frozen v3 role/config required')
        clock = clock or (lambda: datetime.now(UTC))
        now, start, end = stamp(clock()), stamp(start), stamp(end)
        if not now < start < end:
            raise ValueError('register v3 before its future window')
        root = Path(root).absolute()
        if root.resolve() != root or root.is_symlink():
            raise ValueError('new nonsymlink v3 namespace required')
        plan = capacity_plan(lifecycle, storage_policy, start, end)
        measured = measure_resources(root)
        if resource_blocker(lifecycle, measured):
            raise ValueError('v3 preregistration resource floor not satisfied')
        root.mkdir(parents=True, mode=0o700, exist_ok=False)
        wallet = PaperWallet(root/'wallet.sqlite', candidate_sha=candidate_sha, config=config, clock=clock)
        protocol = dict(schema_version=SCHEMA, root=str(root), candidate_sha256=candidate_sha,
            study_protocol_sha256=study_protocol_sha256, role=role, registered_at=now.isoformat(),
            start=start.isoformat(), end=end.isoformat(), config=parse(json.dumps(asdict(config), default=str)),
            lifecycle=lifecycle.payload(), storage_policy=asdict(storage_policy), plan=plan,
            registration_resources=measured, runtime_hashes=runtime_hashes(), decimal_contract=decimal_contract(),
            native_schema_sha256=_schema_pin(wallet.path),
            research_only=True, live_eligible=False)
        protocol_pin = _write_new(root/'protocol.json', protocol)
        log = SegmentedEventLog.create(root/'storage', source_protocol_sha256=protocol_pin, policy=storage_policy)
        (root/'capture.lock').touch(mode=0o600, exist_ok=False)
        log.append('genesis', dict(at=now.isoformat(), role=role, wallet=_state(wallet.path)), expected_sequence=1)
        registered = stamp(clock())
        if not now <= registered < start:
            raise ValueError('v3 setup missed preregistration window; namespace cannot be reused')
        registration_pin = _write_new(root/'registration.json', dict(schema_version=SCHEMA, root=str(root),
            registered_at=registered.isoformat(), protocol_sha256=protocol_pin,
            storage_manifest_sha256=log.manifest_sha256, live_eligible=False))
        return cls.resume(root, expected_registration_sha256=registration_pin, clock=clock)

    @classmethod
    def resume(cls, root, *, expected_registration_sha256, clock=None):
        root, registration, protocol, lifecycle = _load(root, expected_registration_sha256)
        obj = cls()
        obj.root, obj.registration, obj.registration_sha256 = root, registration, expected_registration_sha256
        obj.protocol, obj.protocol_sha256, obj.lifecycle = protocol, registration['protocol_sha256'], lifecycle
        obj.config, obj.candidate_sha = PaperConfig(**protocol['config']), protocol['candidate_sha256']
        obj.clock, obj.path = clock or (lambda: datetime.now(UTC)), root/'wallet.sqlite'
        with obj._lock():
            _root_inventory(root)
            _check_native_schema(obj.path, protocol['native_schema_sha256'])
            obj.log = SegmentedEventLog.open(root/'storage', expected_manifest_sha256=registration['storage_manifest_sha256'])
            if obj.log.manifest['source_protocol_sha256'] != obj.protocol_sha256:
                raise ValueError('storage source protocol differs')
            head = obj._head()
            if head[1] not in {'genesis', 'complete', 'terminated'}:
                raise ValueError('unfinished native operation requires review; no retry or backfill')
            event = parse(head[2])
            if _state(obj.path) != event['wallet' if head[1] == 'genesis' else 'after']:
                raise ValueError('uncaptured native wallet mutation')
            obj._wallet = PaperWallet(obj.path, candidate_sha=obj.candidate_sha, config=obj.config, clock=obj.clock)
        return obj

    def _lock(self):
        return _lease(self.root, writer=True)

    def _verify_identity(self):
        _, registration, protocol, lifecycle = _load(self.root, self.registration_sha256)
        if (registration != self.registration or protocol != self.protocol or lifecycle != self.lifecycle
                or self.protocol_sha256 != registration['protocol_sha256']
                or self.path != self.root/'wallet.sqlite' or self._wallet.path != self.path
                or self.config != PaperConfig(**protocol['config']) or self.candidate_sha != protocol['candidate_sha256']
                or self._wallet.config != self.config or self._wallet.candidate_sha != self.candidate_sha
                or self.log.root != self.root/'storage'
                or self.log.manifest_sha256 != registration['storage_manifest_sha256']):
            raise ValueError('in-memory v3 identity differs from original registration')
        _root_inventory(self.root)
        _check_native_schema(self.path, protocol['native_schema_sha256'])

    def _head(self):
        with self.log._lease(writer=False):
            db = self.log._db(writer=False)
            try:
                seq, sha, active, closed, pending = self.log._head(db)
                if not seq or pending is not None:
                    raise ValueError('pending storage append requires explicit resume')
                path = self.log._path(active)
                info = _guard(path, limit=self.log.policy.maximum_segment_bytes)
                with path.open('rb') as source:
                    source.seek(max(0, info.st_size-self.log.policy.maximum_record_bytes-1))
                    raw = source.read(self.log.policy.maximum_record_bytes+1).splitlines(keepends=True)[-1]
                record = parse(raw)
                _verified_frame(raw, seq, record['previous_sha256'])
                if record['sha256'] != sha:
                    raise ValueError('original v3 head differs')
                return seq, record['kind'], canonical(record['payload']).decode(), record['previous_sha256'], sha
            finally:
                db.close()

    def _append(self, kind, payload):
        sequence = self._head()[0]+1
        return self.log.append(kind, payload, expected_sequence=sequence)['sequence']

    def _resources(self):
        measured = measure_resources(self.root)
        _root_inventory(self.root)
        # Include nested event files, catalogue and manifest in the total budget.
        total, count = 0, 0
        for path in self.root.rglob('*'):
            if path.is_symlink():
                raise ValueError('v3 sources cannot use symlinks')
            count += 1
            if count > self.log.policy.maximum_segments+16:
                raise ValueError('bounded v3 source inventory required')
            if path.is_file():
                total += _guard(path, limit=max(MAX_BYTES, self.log.policy.maximum_segment_bytes)).st_size
        return {**measured, 'storage_bytes': total}

    def enqueue(self, intent_id, pair, side, *, created_at):
        with self._lock():
            self._verify_identity()
            now = stamp(self.clock())
            if (self._head()[1] not in {'genesis', 'complete'}
                    or not stamp(self.protocol['start']) <= now < stamp(self.protocol['end'])
                    or (side == 'Buy' and now >= stamp(self.protocol['plan']['entry_cutoff']))):
                raise ValueError('v3 entry window closed or native operation unfinished')
            return self._wallet.enqueue(intent_id, pair, side, created_at=created_at)

    def _operation(self, kind, inputs):
        inputs = _market_input(inputs)
        with self._lock():
            self._verify_identity()
            head = self._head()
            if head[1] not in {'genesis', 'complete'}:
                raise ValueError('unfinished or terminated native capture; no retry')
            if head[0]+3 > self.log.policy.maximum_events:
                raise ValueError('v3 global event budget exhausted before operation')
            previous, before = parse(head[2]), _state(self.path)
            if before != previous['wallet' if head[1] == 'genesis' else 'after']:
                raise ValueError('uncaptured native wallet mutation')
            now, end = stamp(self.clock()), stamp(self.protocol['end'])
            if (now < stamp(previous['at']) or not stamp(self.protocol['start']) <= now <= end
                    or (kind == 'execute' and now == end)):
                raise ValueError('operation outside prospective v3 window')
            slot = int(seconds(now-stamp(self.protocol['start']))//self.lifecycle.poll_seconds)
            if now == end:
                slot = self.protocol['plan']['poll_slots']
            count = previous.get('slot_operations', 0)+1 if previous.get('slot') == slot else 1
            reserve = 8*self.log.policy.maximum_record_bytes+METADATA_BYTES
            resources = self._resources()
            reason = resource_blocker(self.lifecycle, resources, reserve_bytes=reserve)
            with self.log._lease(writer=False):
                db = self.log._db(writer=False)
                try:
                    storage_exhausted = self.log._storage(db)+reserve > self.log.policy.maximum_total_bytes
                finally:
                    db.close()
            rate_exhausted = count > (1 if now == end else self.lifecycle.maximum_operations_per_poll)
            if (rate_exhausted or reason or storage_exhausted
                    or self.path.stat().st_size+reserve > MAX_BYTES):
                self._terminate_locked('operation_rate_budget' if rate_exhausted else 'resource_budget', resources=resources)
                raise ValueError('v3 resource/rate budget terminated capture')
            if kind == 'execute' and now >= stamp(self.protocol['plan']['entry_cutoff']):
                with self._db() as db:
                    row = db.execute('SELECT side FROM intents WHERE id=?', (inputs['intent_id'],)).fetchone()
                if row and row[0] == 'Buy':
                    raise ValueError('v3 cutoff forbids new Buy fills')
            intent = None
            if kind == 'execute':
                with self._db() as db:
                    row = db.execute('SELECT * FROM intents WHERE id=?', (inputs['intent_id'],)).fetchone()
                if not row:
                    raise ValueError('original native intent required before capture')
                intent = dict(zip(('id', 'pair', 'side', 'created_at', 'observed_at', 'status', 'reason'), row))
            fields = dict(slot=slot, slot_operations=count, resources=resources)
            prepared = self._append('prepared', dict(at=now.isoformat(), operation=kind, inputs=inputs,
                                                      before=before, intent_before=intent, **fields))
            self._wallet.clock = lambda: now
            started = monotonic_ns()
            try:
                result = (self._wallet.mark(inputs['quotes'], inputs['filters']) if kind == 'mark' else
                          self._wallet.execute(inputs['intent_id'], inputs['quote'], inputs['filters']))
            finally:
                self._wallet.clock = self.clock
            elapsed, completed, after = monotonic_ns()-started, stamp(self.clock()), _state(self.path)
            if not now <= completed <= end:
                raise ValueError('native completion outside capture window; review required')
            db = _read_db(self.path)
            try:
                references = _references(db, before, after, result)
            finally:
                db.close()
            self._append('complete', dict(at=completed.isoformat(), prepared_seq=prepared, result=result,
                after=after, source_rows=references, operation_wall_ns=elapsed, **fields))
            if elapsed > self.lifecycle.maximum_operation_wall_seconds*1000000000:
                self._terminate_locked('operation_wall_budget')
                raise ValueError('v3 native wall budget exceeded')
            return result

    def _terminate_locked(self, reason, *, resources=None):
        # The inherited timing contract is retained, using the enriched state.
        if reason not in {'completed', 'operator_abort', 'resource_budget', 'operation_rate_budget', 'operation_wall_budget'}:
            raise ValueError('explicit v3 termination reason required')
        head, now = self._head(), stamp(self.clock())
        if head[1] not in {'genesis', 'complete'}:
            raise ValueError('unfinished or terminated v3 capture cannot be finalized again')
        end, event = stamp(self.protocol['end']), parse(head[2])
        if (not max(stamp(event['at']), stamp(self.protocol['start'])) <= now <=
                end+timedelta(seconds=self.lifecycle.finalization_grace_seconds)
                or (reason == 'completed' and now < end)):
            raise ValueError('v3 termination outside original bounds')
        state = _state(self.path)
        if state != event['wallet' if head[1] == 'genesis' else 'after']:
            raise ValueError('uncaptured native mutation before v3 termination')
        sequence = self._append('terminated', dict(at=now.isoformat(), reason=reason, after=state, resources=resources))
        return dict(status='terminated', sequence=sequence, reason=reason, live_admission_granted=False)

    def finalize(self):
        """Seal storage after an ORIGINAL terminal; never synthesize completion."""
        with self._lock():
            self._verify_identity()
            if self._head()[1] != 'terminated':
                raise ValueError('original terminal required before v3 storage seal')
            receipt = dict(schema_version=SCHEMA, registration_sha256=self.registration_sha256,
                           protocol_sha256=self.protocol_sha256, **self.log.seal())
            pin = _write_new(self.root/'sealed.json', receipt)
            return {**receipt, 'seal_sha256': pin, 'live_admission_granted': False}


def audit_segmented_capture(root, *, expected_registration_sha256, expected_seal_sha256=None, clock=None):
    """Sealed source/operation audit. Full FIFO and coverage admission is pending."""
    root, registration, protocol, lifecycle = _load(root, expected_registration_sha256)
    output = dict(schema_version='segmented-paper-capture-audit-v3',
        registration_sha256=expected_registration_sha256, protocol_sha256=registration['protocol_sha256'],
        role=protocol['role'], paper_evidence_pass=False, economic_profitability_established=False,
        live_admission_granted=False, full_fifo_replay_pass=False, coverage_evidence_pass=False,
        full_worker_or_host_qualified=False)
    if stamp((clock or (lambda: datetime.now(UTC)))()) < stamp(protocol['end']):
        return {**output, 'status': 'sealed_until_capture_end', 'performance_hidden': True}
    seal = _metadata(root/'sealed.json', expected_seal_sha256)
    if (seal.get('schema_version') != SCHEMA or seal.get('registration_sha256') != expected_registration_sha256
            or seal.get('protocol_sha256') != registration['protocol_sha256']
            or seal.get('manifest_sha256') != registration['storage_manifest_sha256']):
        raise ValueError('original v3 sealed identity differs')
    with _lease(root, writer=False):
        _root_inventory(root)
        _check_native_schema(root/'wallet.sqlite', protocol['native_schema_sha256'])
        # Read-only construction: do not recover pending storage or native DBs.
        log = SegmentedEventLog._load(root/'storage', registration['storage_manifest_sha256'])
        if log.manifest['source_protocol_sha256'] != registration['protocol_sha256']:
            raise ValueError('original storage source protocol differs')
        sources = {name: fingerprint(root/name) for name in ('wallet.sqlite', 'protocol.json', 'registration.json', 'sealed.json')}
        db = _read_db(root/'wallet.sqlite')
        state, pending, terminal = None, None, None
        count, marks, fills, raw_marks, raw_fills = 0, 0, 0, 0, 0
        wall_budget_pass = True
        last_at, previous_slot, slot_count = stamp(protocol['registered_at']), None, 0
        latest_mark, latest_known_equity = None, None
        config = PaperConfig(**protocol['config'])
        try:
            db.execute('BEGIN')
            for record in log.iter_events(expected_head_sha256=seal['head_sha256'], expected_catalog_sha256=seal['catalog_sha256']):
                count += 1
                kind, event = record['kind'], record['payload']
                at, end = stamp(event['at']), stamp(protocol['end'])
                upper = end+timedelta(seconds=lifecycle.finalization_grace_seconds) if kind == 'terminated' else end
                if terminal is not None or not last_at <= at <= upper:
                    raise ValueError('v3 source event clock/terminal differs')
                if not wall_budget_pass and kind != 'terminated':
                    raise ValueError('v3 operation continued after wall budget failure')
                last_at = at
                if count == 1:
                    state = event['wallet']
                    policy = json.dumps(dict(candidate_sha=protocol['candidate_sha256'], config=asdict(config)), sort_keys=True, default=str)
                    if (kind != 'genesis' or event['role'] != protocol['role'] or at != stamp(protocol['registered_at'])
                            or state != dict(state={'cash': str(config.capital), 'policy': policy},
                                             lots=[], filters={}, fills=0, marks=0, segments=0)):
                        raise ValueError('original empty v3 genesis required')
                    continue
                if at < stamp(protocol['start']):
                    raise ValueError('v3 operation before original window')
                if kind == 'terminated':
                    if (pending is not None or event['after'] != state
                            or event['reason'] not in {'completed', 'operator_abort', 'resource_budget', 'operation_rate_budget', 'operation_wall_budget'}
                            or (not wall_budget_pass and event['reason'] != 'operation_wall_budget')
                            or (event['reason'] == 'completed' and at < end)):
                        raise ValueError('invalid original v3 terminal')
                    terminal = event
                    continue
                if kind == 'prepared':
                    if pending is not None or event['before'] != state:
                        raise ValueError('v3 prepared source state/order differs')
                    slot = int(seconds(at-stamp(protocol['start']))//lifecycle.poll_seconds)
                    if at == end:
                        slot = protocol['plan']['poll_slots']
                    slot_count = slot_count+1 if previous_slot == slot else 1
                    reserve = 8*log.policy.maximum_record_bytes+METADATA_BYTES
                    if (event['slot'] != slot or event['slot_operations'] != slot_count
                            or slot_count > (1 if at == end else lifecycle.maximum_operations_per_poll)
                            or resource_blocker(lifecycle, event['resources'], reserve_bytes=reserve)):
                        raise ValueError('v3 original slot/resource limits differ')
                    previous_slot, pending = slot, (count, event)
                    continue
                if (kind != 'complete' or pending is None or event['prepared_seq'] != pending[0]
                        or any(event[key] != pending[1][key] for key in ('slot', 'slot_operations', 'resources'))
                        or type(event['operation_wall_ns']) is not int or event['operation_wall_ns'] < 0):
                    raise ValueError('v3 completion lacks original preparation')
                prepared, after, result = pending[1], event['after'], event['result']
                wall_budget_pass &= event['operation_wall_ns'] <= lifecycle.maximum_operation_wall_seconds*1000000000
                inputs = _market_input(prepared['inputs'])
                if event['source_rows'] != _references(db, state, after, result):
                    raise ValueError('v3 original native source row/hash differs')
                expected = {**state}
                if prepared['operation'] == 'mark':
                    expected['filters'] = {**state['filters'], **inputs['filters']}
                    replayed, quality = replay_liquidation(state, inputs['quotes'], expected['filters'], config, prepared['at'])
                    row = db.execute('SELECT payload FROM marks WHERE id=?', (state['marks']+1,)).fetchone()
                    if result != replayed or not row or parse(row[0]) != result:
                        raise ValueError('v3 original mark differs from independent valuation')
                    if prepared['intent_before'] is not None:
                        raise ValueError('mark cannot consume an intent')
                    expected['marks'] += 1
                    marks += 1
                    raw_marks += int(quality['raw_sources_verified'])
                    equity = Decimal(result['equity']) if result['equity'] is not None else None
                    expected['state'] = _anchored_state(state['state'], equity, prepared['at'], latest_known_equity)
                    latest_mark = result
                    if result['equity'] is not None:
                        latest_known_equity = Decimal(result['equity'])
                elif prepared['operation'] == 'execute':
                    intent = prepared['intent_before']
                    if (type(intent) is not dict or intent.get('id') != inputs['intent_id']
                            or intent.get('pair') != inputs['quote']['pair'] or intent.get('side') not in {'Buy', 'Sell'}):
                        raise ValueError('original v3 intent identity differs')
                    expected['state'] = _day_state(state, intent, result, prepared['at'], latest_mark, latest_known_equity, config)
                    if (not result.get('duplicate') and result.get('status') in {'filled', 'rejected'}
                            and result.get('reason') != 'expired_signal'):
                        expected['filters'] = {**state['filters'], inputs['filters']['pair']: inputs['filters']}
                    if result.get('status') == 'filled' and not result.get('duplicate'):
                        fill = result['fill']
                        if (fill['intent_id'] != inputs['intent_id'] or fill['quote'] != inputs['quote']
                                or fill['filters'] != inputs['filters'] or stamp(fill['filled_at']) != stamp(prepared['at'])
                                or fill['side'] != intent['side'] or fill['pair'] != intent['pair']
                                or fill['signal_time'] != intent['created_at'] or intent['status'] != 'pending'
                                or fill['candidate_sha256'] != protocol['candidate_sha256']
                                or (fill['side'] == 'Buy' and stamp(prepared['at']) >= stamp(protocol['plan']['entry_cutoff']))):
                            raise ValueError('v3 fill source/clock/cutoff differs')
                        cash, lots = _inventory_after(state, fill)
                        expected['state'] = {**expected['state'], 'cash': cash}
                        expected['lots'], expected['fills'] = lots, state['fills']+1
                        expected['segments'] = after['segments']
                        fills += 1
                        raw_fills += int(_sources(fill['quote'], fill['filters']))
                else:
                    raise ValueError('unknown v3 source operation')
                if after != expected:
                    raise ValueError('v3 after-state differs from operation replay')
                state, pending = after, None
            if pending is not None or terminal is None or count != seal['sequence'] or _state(root/'wallet.sqlite') != state:
                raise ValueError('unfinished v3 capture or final native source drift')
        finally:
            db.close()
        if sources != {name: fingerprint(root/name) for name in sources}:
            raise ValueError('v3 source changed during read-only replay')
        _load(root, expected_registration_sha256)
    return {**output, 'status': 'segmented_capture_sources_replayed', 'performance_hidden': False,
        'operation_trace_pass': True, 'events_checked': count, 'marks_checked': marks, 'fills_checked': fills,
        'raw_source_marks': raw_marks, 'raw_source_fills': raw_fills, 'terminal_reason': terminal['reason'],
        'operation_wall_budget_pass': wall_budget_pass,
        'input_files': sources, 'scope': 'bounded_event_and_native_row_linkage_not_full_fifo_coverage_or_strategy_admission'}
