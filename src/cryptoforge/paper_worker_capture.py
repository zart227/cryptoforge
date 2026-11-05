"""Prospective, bounded source journal around the frozen paper worker.

Tick inputs, real clock observations, public providers and atomic native actions
are retained. An interrupted tick cannot be adopted, retried or backfilled.
This is capture/source linkage, not independent worker or economic qualification.
"""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import re
from time import monotonic, monotonic_ns
from types import FunctionType, SimpleNamespace

from cryptoforge.evidence_segments import SegmentPolicy, SegmentedEventLog, canonical, digest, parse, require_sha
from cryptoforge.native_paper_archive import NativePaperArchive, NativeArchivePolicy, SOURCES
from cryptoforge.paper_capture_v3 import SegmentedCapturedPaperWallet, SegmentedLifecycle, _lease, _metadata, _write_new, stamp
from cryptoforge.paper_capture_v4 import (
    AUXILIARY, _active, _adjust, _apply, _checkpoint, _checkpoint_refs, _compaction_watermarks,
    _delta, _empty, _initial, _inventory, _logical, _operation_rows, _source_identity,
    _transition, _valid_row, runtime_hashes as wallet_runtime,
)
from cryptoforge.paper_lifecycle import measure_resources, resource_blocker, seconds
from cryptoforge.paper_valuation_capture import _market_input, _sources, decimal_contract
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_worker import PaperWorker

SCHEMA = 'paper-worker-source-capture-v1'
TERMINALS = {'completed', 'operator_abort', 'resource_budget', 'operation_wall_budget'}


@dataclass(frozen=True)
class WorkerCapturePolicy:
    maximum_predictions_per_tick: int
    maximum_actions_per_tick: int
    maximum_clock_calls_per_tick: int
    maximum_market_requests_per_tick: int
    maximum_exit_requests_per_tick: int

    def __post_init__(self):
        if (any(type(v) is not int or not 1 <= v <= 4096 for v in asdict(self).values())
                or self.maximum_actions_per_tick < 4):
            raise ValueError('explicit bounded worker source/action/clock/request budgets required')

    @property
    def events_per_tick(self):
        return 2+self.maximum_clock_calls_per_tick+2*(self.maximum_actions_per_tick
            +self.maximum_market_requests_per_tick+self.maximum_exit_requests_per_tick)


def runtime_hashes():
    runner = Path(__file__).resolve().parents[2]/'scripts/audit_paper_worker_capture.py'
    return {**wallet_runtime(), 'worker_capture': digest(Path(__file__).read_bytes()),
            'worker_capture_runner': digest(runner.read_bytes())}


def _bounded(value, limit):
    """Reject large/deep/provider-owned objects before copying or JSON encoding."""
    remaining = limit
    def visit(item, depth):
        nonlocal remaining
        remaining -= 8
        if remaining < 0 or depth > 24:raise ValueError('bounded worker value bytes/depth required')
        if type(item) is str:
            remaining -= len(item)*6  # worst-case JSON escaping, no large temporary bytes
            if remaining < 0:raise ValueError('bounded worker string required')
        elif type(item) in (dict, list, tuple):
            if len(item) > remaining//8:raise ValueError('bounded worker collection required')
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str or re.search(r'(?i)secret|api.?key|authorization|password|token|cookie|service.?role|private.?key', key):
                        raise ValueError('credentials/unknown keys cannot enter worker capture')
                    visit(key, depth+1);visit(child, depth+1)
            else:
                for child in item:visit(child, depth+1)
        elif type(item) not in (int, float, bool, type(None)):
            raise ValueError('plain bounded JSON worker values required')
    visit(value, 0)
    raw = canonical(value)
    if len(raw) > limit:raise ValueError('bounded worker JSON required')
    return raw


def capacity_plan(lifecycle, storage, native, capture, start, end):
    if (type(lifecycle) is not SegmentedLifecycle or type(storage) is not SegmentPolicy
            or type(native) is not NativeArchivePolicy or type(capture) is not WorkerCapturePolicy
            or lifecycle.maximum_operations_per_poll != 1
            or storage.maximum_record_bytes < 8192
            or capture.maximum_predictions_per_tick > native.maximum_active_rows):
        raise ValueError('typed worker policies and one whole tick per original poll slot required')
    plan = lifecycle.plan(start, end, max_events=storage.maximum_events)
    events = plan['poll_slots']*capture.events_per_tick+6  # genesis, endpoint tick/action, terminal
    reserve = (capture.events_per_tick+4)*storage.maximum_record_bytes+65536
    if (events > storage.maximum_events or native.maximum_records < plan['poll_slots']+1
            or storage.maximum_total_bytes < max(reserve, plan['estimated_storage_bytes'])
            or storage.maximum_total_bytes+native.maximum_total_bytes+1024*1024 > lifecycle.maximum_storage_bytes):
        raise ValueError('whole worker event/native/storage capacity insufficient before registration')
    return {**plan, 'required_worker_events': events, 'events_per_tick': capture.events_per_tick,
            'tick_storage_reserve_bytes': reserve,
            'tick_resource_reserve_bytes':reserve+3*native.maximum_active_bytes+2*native.maximum_batch_bytes,
            'full_worker_or_host_qualified': False}


def _worker_policy(policy):
    value = parse(canonical(policy))
    if (value.get('enabled') is not True or value.get('status') != 'frozen'
            or type(value['runtime']['maximum_new_signals_per_tick']) is not int
            or not 1 <= value['runtime']['maximum_new_signals_per_tick'] <= 4096
            or type(value['runtime']['wall_budget_seconds']) is not int
            or not 1 <= value['runtime']['wall_budget_seconds'] <= 3600):
        raise ValueError('original enabled frozen worker policy required')
    return value


def _load(root, pin):
    root = Path(root).absolute()
    registration = _metadata(root/'registration.json', pin)
    protocol = _metadata(root/'protocol.json', registration['protocol_sha256'])
    lifecycle = SegmentedLifecycle.from_payload(protocol['lifecycle'])
    storage, native, capture = (SegmentPolicy(**protocol['storage_policy']),
        NativeArchivePolicy(**protocol['native_policy']), WorkerCapturePolicy(**protocol['capture_policy']))
    if (registration.get('schema_version') != SCHEMA or protocol.get('schema_version') != SCHEMA
            or registration.get('root') != str(root) or protocol.get('root') != str(root)
            or registration.get('live_eligible') is not False or protocol.get('live_eligible') is not False
            or protocol.get('research_only') is not True or protocol.get('role') not in {'candidate','control','stress'}
            or not stamp(protocol['registered_at']) <= stamp(registration['registered_at'])
                < stamp(protocol['start']) < stamp(protocol['end'])
            or protocol['runtime_hashes'] != runtime_hashes() or protocol['decimal_contract'] != decimal_contract()
            or protocol['plan'] != capacity_plan(lifecycle, storage, native, capture, protocol['start'], protocol['end'])
            or resource_blocker(lifecycle, protocol['registration_resources'])):
        raise ValueError('original prospective worker identity/runtime/capacity required')
    for value in (protocol['candidate_sha256'], protocol['study_protocol_sha256'],
                  registration['native_manifest_sha256'], registration['storage_manifest_sha256']):
        require_sha(value)
    PaperConfig(**protocol['config']);_worker_policy(protocol['worker_policy'])
    return root, registration, protocol, lifecycle, capture


def _batch(predictions, source_id, observed_at, pin, *, policy, config, now, maximum_bytes=256*1024):
    if (type(predictions) is not list or len(predictions) > policy.maximum_predictions_per_tick
            or type(source_id) is not str or not 0 < len(source_id.encode()) <= 256
            or not stamp(observed_at) <= now
            or (now-stamp(observed_at)).total_seconds() > config.signal_expiry_seconds):
        raise ValueError('bounded original prediction batch and causal source observation required')
    require_sha(pin)
    if digest(_bounded(predictions, maximum_bytes)) != pin:
        raise ValueError('original prediction batch SHA differs')
    identities = {}
    for row in predictions:
        require_sha(row['candidate_sha256'])
        if (type(row['opportunity']) is not str or not 0 < len(row['opportunity'].encode()) <= 256
                or type(row['pair']) is not str or not row['pair'].endswith('/USDT')
                or type(row['would_enter']) is not bool):
            raise ValueError('typed original opportunity/pair/decision required')
        stamp(row['predicted_at'])
        if row.get('observed_at'):stamp(row['observed_at'])
        key = row['candidate_sha256'], row['opportunity']
        if key in identities and identities[key] != canonical(row):
            raise ValueError('conflicting duplicate opportunity in original batch')
        identities[key] = canonical(row)
    return dict(predictions=predictions, source_id=source_id, source_observed_at=stamp(observed_at).isoformat(),
                source_sha256=pin)


class _WalletProxy:
    def __init__(self, journal):self.journal = journal
    def __getattr__(self, name):return getattr(self.journal._source.wallet, name)
    def mark(self, quotes, filters=None):
        inputs = _market_input(dict(quotes=quotes, filters=filters or {}))
        return self.journal._action('mark', inputs, lambda: self.journal._source.wallet.mark(quotes, filters))
    def execute(self, identity, quote, filters):
        inputs = _market_input(dict(intent_id=identity, quote=quote, filters=filters))
        return self.journal._action('execute', inputs, lambda: self.journal._source.wallet.execute(identity, quote, filters))
    def cancel_pending(self, identity, reason):
        return self.journal._action('cancel_pending', dict(intent_id=identity, reason=reason),
            lambda: self.journal._source.wallet.cancel_pending(identity, reason))


class CapturedPaperWorker:
    """Only whole captured ticks and the original endpoint mark mutate this root."""
    _head = SegmentedCapturedPaperWallet._head
    _append = SegmentedCapturedPaperWallet._append

    @classmethod
    def create(cls, root, *, candidate_sha, study_protocol_sha256, role, config, worker_policy,
               lifecycle, storage_policy, native_policy, capture_policy, start, end,
               market, exit_indicator=None, clock=None):
        require_sha(candidate_sha);require_sha(study_protocol_sha256)
        if type(config) is not PaperConfig or role not in {'candidate','control','stress'} or not callable(market):
            raise ValueError('explicit worker role/config and public market provider required')
        policy = _worker_policy(worker_policy)
        plan = capacity_plan(lifecycle, storage_policy, native_policy, capture_policy, start, end)
        root, clock = Path(root).absolute(), clock or (lambda:datetime.now(UTC))
        now, start, end = stamp(clock()), stamp(start), stamp(end)
        measured = measure_resources(root);measured['storage_bytes'] = 0
        if root.resolve() != root or not now < start or resource_blocker(lifecycle, measured):
            raise ValueError('new prospective worker namespace and resource floor required')
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        protocol = dict(schema_version=SCHEMA, root=str(root), registered_at=now.isoformat(),
            start=start.isoformat(), end=end.isoformat(), candidate_sha256=candidate_sha,
            study_protocol_sha256=study_protocol_sha256, role=role,
            config=parse(json.dumps(asdict(config), default=str)), worker_policy=policy,
            lifecycle=lifecycle.payload(), storage_policy=asdict(storage_policy), native_policy=asdict(native_policy),
            capture_policy=asdict(capture_policy), plan=plan, registration_resources=measured,
            runtime_hashes=runtime_hashes(), decimal_contract=decimal_contract(), research_only=True, live_eligible=False)
        protocol_pin = _write_new(root/'protocol.json', protocol)
        source = NativePaperArchive.create(root/'native', source_protocol_sha256=protocol_pin,
            candidate_sha=candidate_sha, role=role, config=config, worker_policy=policy,
            policy=native_policy, market=None, clock=clock)
        log = SegmentedEventLog.create(root/'storage', source_protocol_sha256=protocol_pin, policy=storage_policy)
        (root/'capture.lock').touch(mode=0o600, exist_ok=False)
        with source._lease(writer=True):state = _logical(source, _active(source), {})
        log.append('genesis', dict(at=now.isoformat(), role=role, after=state), expected_sequence=1)
        registered = stamp(clock())
        if not now <= registered < start:
            raise ValueError('worker setup missed original registration window; no adoption')
        pin = _write_new(root/'registration.json', dict(schema_version=SCHEMA, root=str(root),
            protocol_sha256=protocol_pin, registered_at=registered.isoformat(),
            native_manifest_sha256=source.manifest_sha256, storage_manifest_sha256=log.manifest_sha256, live_eligible=False))
        return cls.resume(root, expected_registration_sha256=pin, market=market, exit_indicator=exit_indicator, clock=clock)

    @classmethod
    def resume(cls, root, *, expected_registration_sha256, market, exit_indicator=None, clock=None):
        obj = cls()
        obj.root, obj.registration, obj.protocol, obj.lifecycle, obj.capture_policy = _load(root, expected_registration_sha256)
        obj.registration_sha256 = expected_registration_sha256
        obj.protocol_sha256 = obj.registration['protocol_sha256']
        obj.clock = clock or (lambda:datetime.now(UTC))
        obj.config, obj.candidate_sha = PaperConfig(**obj.protocol['config']), obj.protocol['candidate_sha256']
        obj._market, obj._exit = market, exit_indicator or (lambda pair:(False, []))
        if not callable(obj._market) or not callable(obj._exit):raise ValueError('original public providers required')
        obj._cache, obj._tick, obj._fixed, obj._fault = {}, None, None, False
        with _lease(obj.root, writer=True):
            _inventory(obj.root)
            if (obj.root/'sealed.json').exists():raise ValueError('sealed worker cannot resume')
            obj.log = SegmentedEventLog.open(obj.root/'storage', expected_manifest_sha256=obj.registration['storage_manifest_sha256'])
            head = obj._head();event = parse(head[2])
            if head[1] != 'genesis' and not (head[1] == 'complete' and event.get('phase') == 'tick') and head[1] != 'terminated':
                raise ValueError('unfinished worker tick requires review; no retry or backfill')
            obj._source = NativePaperArchive.resume(obj.root/'native',
                expected_manifest_sha256=obj.registration['native_manifest_sha256'], market=None, clock=obj._clock)
            obj._verify()
            with obj._source._lease(writer=True):
                if _logical(obj._source, _active(obj._source), obj._cache) != event['after']:
                    raise ValueError('uncaptured worker native state/checkpoint change')
            obj._state = event['after']
        # Preserve the frozen worker implementation. Wrap only its I/O and native
        # mutators; worker decisions remain unqualified until independent replay.
        worker = obj._source.worker
        worker.wallet, worker.clock = _WalletProxy(obj), obj._clock
        worker.market = lambda pair:obj._provider('market', pair, obj._market)
        worker.exit_indicator = lambda pair:obj._provider('exit', pair, obj._exit)
        for name in ('_enqueue', '_seen', '_event'):
            original = getattr(worker, name)
            setattr(worker, name, obj._wrap_worker_action(name, original))
        obj._worker = worker
        # Execute the identical frozen function with one private I/O binding.
        # Never monkeypatch the time module shared with other workers/threads.
        original = PaperWorker.tick
        obj._run_tick = FunctionType(original.__code__, {**original.__globals__,
            'monotonic_time':SimpleNamespace(monotonic=obj._monotonic)}, original.__name__, original.__defaults__)
        obj._run_tick.__kwdefaults__ = original.__kwdefaults__
        return obj

    def _verify(self):
        root, registration, protocol, lifecycle, capture = _load(self.root, self.registration_sha256)
        if (root != self.root or registration != self.registration or protocol != self.protocol
                or lifecycle != self.lifecycle or capture != self.capture_policy
                or self.protocol_sha256 != registration['protocol_sha256']
                or self.config != PaperConfig(**protocol['config']) or self.candidate_sha != protocol['candidate_sha256']
                or self.log.root != root/'storage' or self.log.manifest_sha256 != registration['storage_manifest_sha256']
                or self.log.manifest['source_protocol_sha256'] != registration['protocol_sha256']
                or self.log.policy != SegmentPolicy(**protocol['storage_policy'])
                or self._source.root != root/'native' or self._source.manifest_sha256 != registration['native_manifest_sha256']
                or self._source.wallet.clock != self._clock or self._source.worker.clock != self._clock):
            raise ValueError('original worker in-memory identity differs')
        _inventory(root);_source_identity(self._source, registration, protocol);self._source._identity()

    def _wrap_worker_action(self, name, original):
        def call(*args, **kwargs):
            if name == '_enqueue':
                identity, pair, side, created, payload = args
                inputs = dict(intent_id=identity, pair=pair, side=side, created_at=stamp(created).isoformat(),
                    payload=payload, source_key=kwargs.get('source_key'))
            elif name == '_seen':inputs = dict(identity=args[0], status=args[1])
            else:inputs = dict(payload=args[0])
            return self._action('worker'+name, inputs, lambda:original(*args, **kwargs))
        return call

    def _now(self):
        now = stamp(self.clock())
        if self._tick is not None:
            if not self._tick['last_at'] <= now <= stamp(self.protocol['end']):
                self._fault = True
                raise ValueError('worker observation clock outside causal window')
            self._tick['last_at'] = now
        return now

    def _record(self, kind, payload):
        if self._fault:raise ValueError('worker capture fault requires review; no subsequent effects')
        try:
            # Leave bounded space for the canonical segment frame envelope.
            if len(canonical(payload))+1024 > self.log.policy.maximum_record_bytes:
                raise ValueError('worker frame budget exceeded')
            if self._tick is not None:
                self._tick['events'] += 1
                if self._tick['events'] > self.capture_policy.events_per_tick:
                    raise ValueError('worker tick event budget exceeded')
                payload = dict(payload, tick_sequence=self._tick['sequence'])
            return self._append(kind, payload)
        except BaseException:
            self._fault = True
            raise

    def _clock(self):
        if self._fixed is not None:return self._fixed
        now = self._now()
        if self._tick is not None:
            self._count('clocks', self.capture_policy.maximum_clock_calls_per_tick)
            self._record('complete', dict(phase='clock', at=now.isoformat()))
        return now

    def _monotonic(self):
        value = monotonic()
        self._count('clocks', self.capture_policy.maximum_clock_calls_per_tick)
        if type(value) is not float or value < self._tick.get('last_monotonic', 0):
            self._fault = True
            raise ValueError('original finite monotonic worker clock required')
        self._tick['last_monotonic'] = value
        self._record('complete', dict(phase='monotonic', at=self._now().isoformat(), value=value))
        return value

    def _count(self, name, maximum):
        if self._fault:raise ValueError('worker capture fault requires review')
        self._tick[name] = self._tick.get(name, 0)+1
        if self._tick[name] > maximum:
            self._fault = True
            raise ValueError('worker '+name+' budget exceeded')

    def _provider(self, name, pair, provider):
        self._count(name, getattr(self.capture_policy, 'maximum_'+('market' if name == 'market' else 'exit')+'_requests_per_tick'))
        now = self._now()
        seq = self._record('prepared', dict(phase=name, at=now.isoformat(), pair=pair))
        started = monotonic_ns()
        try:result = provider(pair)
        except Exception as exc:
            self._record('complete', dict(phase=name, at=self._now().isoformat(), prepared_seq=seq,
                error=type(exc).__name__, result=None, operation_wall_ns=monotonic_ns()-started))
            raise
        try:
            completed = self._now()
            _bounded(result, self.log.policy.maximum_record_bytes)
            if name == 'market':
                quote, rules = result
                result = _market_input(dict(quote=quote, filters=rules))
                _provider_source(pair, result, now, completed)
            else:
                exits, reasons = result
                if type(exits) is not bool or type(reasons) is not list or any(type(r) is not str for r in reasons):
                    raise ValueError('typed exit indicator result required')
                result = dict(exits=exits, reasons=reasons)
            self._record('complete', dict(phase=name, at=completed.isoformat(), prepared_seq=seq,
                result=result, error=None, operation_wall_ns=monotonic_ns()-started))
        except BaseException:
            self._fault = True
            raise
        return (parse(canonical(result['quote'])), parse(canonical(result['filters']))) if name == 'market' else (result['exits'], result['reasons'])

    def _action(self, operation, inputs, invoke):
        self._count('actions', self.capture_policy.maximum_actions_per_tick)
        before_active = _active(self._source)
        before = _logical(self._source, before_active, self._cache)
        if before != self._state:
            self._fault = True
            raise ValueError('uncaptured worker state before action')
        now = self._now();inputs = parse(canonical(inputs))
        if now >= stamp(self.protocol['plan']['entry_cutoff']):
            intent = before_active['wallet.intents'].get(inputs.get('intent_id'))
            if ((operation == 'worker_enqueue' and inputs['side'] == 'Buy')
                    or (operation == 'execute' and intent and intent[2] == 'Buy')):
                self._fault = True
                raise ValueError('worker cutoff forbids new Buy intents/fills')
        prepared = dict(phase='action', at=now.isoformat(), operation=operation, inputs=inputs, before=before)
        seq = self._record('prepared', prepared)
        started = monotonic_ns();self._fixed = now
        try:result = invoke()
        except BaseException:
            self._fault = True
            raise
        finally:self._fixed = None
        try:
            completed = self._now()
            after_active = _active(self._source)
            after = _logical(self._source, after_active, self._cache)
            changes = _delta(self._source, before_active, after_active)
            event = dict(phase='action', at=completed.isoformat(), prepared_seq=seq, after=after,
                changes=changes, result=result, operation_wall_ns=monotonic_ns()-started)
            _action_rows(prepared, event, self.protocol)
            if _apply(before['sources'], changes, maximum_bytes=self.log.policy.maximum_record_bytes) != after['sources']:
                raise ValueError('worker native delta linkage differs')
            self._record('complete', event);self._state = after
        except BaseException:
            self._fault = True
            raise
        return result

    def _resources(self):
        measured = measure_resources(self.root);total = count = 0
        from cryptoforge.evidence_segments import _guard
        for path in self.root.rglob('*'):
            count += 1
            if path.is_symlink() or count > self.log.policy.maximum_segments+self._source.policy.shards+32:
                raise ValueError('bounded original worker inventory required')
            if path.is_file():total += _guard(path, limit=max(64*1024*1024, self.log.policy.maximum_segment_bytes)).st_size
        return {**measured, 'storage_bytes':total}

    def _begin(self, mode, inputs):
        self._verify()
        head = self._head();previous = parse(head[2])
        if (self._fault or self._tick is not None or not (head[1] == 'genesis'
                or head[1] == 'complete' and previous.get('phase') == 'tick')):
            raise ValueError('unfinished or terminated worker tick; no retry')
        before = _logical(self._source, _active(self._source), self._cache)
        if before != previous['after']:raise ValueError('uncaptured worker state before tick')
        now, start, end = self._now(), stamp(self.protocol['start']), stamp(self.protocol['end'])
        if (now < stamp(previous['at']) or (mode == 'tick' and not start <= now < end)
                or (mode == 'endpoint' and now != end)):
            raise ValueError('whole worker tick/endpoint outside original window')
        slot = self.protocol['plan']['poll_slots'] if now == end else int(seconds(now-start)//self.lifecycle.poll_seconds)
        if slot <= previous.get('slot', -1):raise ValueError('one worker tick per original poll slot')
        if mode == 'tick':
            _batch(inputs['predictions'], inputs['source_id'], inputs['source_observed_at'], inputs['source_sha256'],
                policy=self.capture_policy, config=self.config, now=now, maximum_bytes=self.log.policy.maximum_record_bytes-4096)
        measured = self._resources()
        needed_events = self.capture_policy.events_per_tick if mode == 'tick' else 4
        reserve = (needed_events+4)*self.log.policy.maximum_record_bytes+65536
        resource_reserve = reserve+3*self._source.policy.maximum_active_bytes+2*self._source.policy.maximum_batch_bytes
        with self.log._lease(writer=False):
            db = self.log._db(writer=False)
            try:storage_full = self.log._storage(db)+reserve > self.log.policy.maximum_total_bytes
            finally:db.close()
        if (head[0]+needed_events+1 > self.log.policy.maximum_events or storage_full
                or resource_blocker(self.lifecycle, measured, reserve_bytes=resource_reserve)):
            self._terminate('resource_budget', now)
            raise ValueError('worker resource/event budget terminated before tick')
        seq = self._record('prepared', dict(phase='tick', at=now.isoformat(), mode=mode,
            inputs=inputs, before=before, slot=slot, resources=measured))
        self._tick = dict(sequence=seq, events=1, last_at=now, slot=slot)
        self._state = before

    def _end(self, result, started):
        if self._fault:raise ValueError('unfinished worker action; no successful tick receipt')
        now = self._now();elapsed = monotonic_ns()-started
        if _logical(self._source, _active(self._source), self._cache) != self._state:
            self._fault = True
            raise ValueError('uncaptured worker change after tick')
        self._record('complete', dict(phase='tick', at=now.isoformat(), prepared_seq=self._tick['sequence'],
            slot=self._tick['slot'], after=self._state, result=result, operation_wall_ns=elapsed))
        self._tick = None
        if elapsed > self.lifecycle.maximum_operation_wall_seconds*1000000000:
            self._terminate('operation_wall_budget', now)
            raise ValueError('whole worker wall budget exceeded')
        return result

    def tick(self, predictions, *, source_id, source_observed_at, expected_source_sha256):
        # Materialize neither an unbounded iterable nor unbounded candidate history.
        inputs = _batch(predictions, source_id, source_observed_at, expected_source_sha256,
            policy=self.capture_policy, config=self.config, now=stamp(self.clock()),
            maximum_bytes=self.log.policy.maximum_record_bytes-4096)
        inputs = parse(canonical(inputs))
        with _lease(self.root, writer=True), self._source._lease(writer=True):
            self._begin('tick', inputs);started = monotonic_ns()
            self._action('compact', {}, self._source.compact)
            # Original archive filtering, retaining ALL supplied predictions above.
            selected = [row for row in inputs['predictions'] if not self._source.lookup('worker.seen_predictions',
                digest((row['candidate_sha256']+'|'+row['opportunity']).encode()))]
            try:
                result = self._run_tick(self._worker, selected, window_start=stamp(self.protocol['start']),
                    window_end=stamp(self.protocol['end']), entry_cutoff=stamp(self.protocol['plan']['entry_cutoff']))
                if result.get('status') != 'paper_tick_complete':raise ValueError('original worker tick did not complete inside window')
                return self._end(result, started)
            except BaseException:
                self._fault = True
                raise

    def mark_endpoint(self, quotes, filters):
        _bounded(dict(quotes=quotes,filters=filters), self.log.policy.maximum_record_bytes-4096)
        inputs = _market_input(dict(quotes=quotes, filters=filters))
        _endpoint_sources(inputs, stamp(self.clock()))
        with _lease(self.root, writer=True), self._source._lease(writer=True):
            self._begin('endpoint', inputs);started = monotonic_ns()
            result = self._action('mark', inputs, lambda:self._source.wallet.mark(quotes, filters))
            return self._end(result, started)

    def _terminate(self, reason, now):
        head = self._head();previous = parse(head[2]);end = stamp(self.protocol['end'])
        if (reason not in TERMINALS or self._fault or self._tick is not None
                or not (head[1] == 'genesis' or head[1] == 'complete' and previous.get('phase') == 'tick')
                or not max(stamp(previous['at']), stamp(self.protocol['start'])) <= now
                    <= end+timedelta(seconds=self.lifecycle.finalization_grace_seconds)
                or reason == 'completed' and now < end):
            raise ValueError('original completed worker tick and terminal bounds required')
        after = _logical(self._source, _active(self._source), self._cache)
        if after != previous['after']:raise ValueError('uncaptured worker change before terminal')
        self._record('terminated', dict(at=now.isoformat(), reason=reason, after=after))

    def terminate(self, reason):
        with _lease(self.root, writer=True), self._source._lease(writer=True):
            self._verify();self._terminate(reason, stamp(self.clock()))

    def finalize(self):
        with _lease(self.root, writer=True), self._source._lease(writer=True):
            self._verify();head = self._head();now, end = stamp(self.clock()), stamp(self.protocol['end'])
            if head[1] != 'terminated' or not end <= now <= end+timedelta(seconds=self.lifecycle.finalization_grace_seconds):
                raise ValueError('original worker terminal/end window required before seal')
            before = parse(head[2])['after']
            if _logical(self._source, _active(self._source), self._cache) != before:
                raise ValueError('uncaptured worker change before seal')
            native = self._source.seal()
            after = _logical(self._source, _active(self._source), self._cache)
            if after['sources'] != before['sources'] or after['checkpoint']['generation'] != before['checkpoint']['generation']+1:
                raise ValueError('worker seal compaction changed logical history')
            receipt = dict(schema_version=SCHEMA, registration_sha256=self.registration_sha256,
                protocol_sha256=self.protocol_sha256, native_seal_sha256=native['seal_sha256'], native_after=after, **self.log.seal())
            pin = _write_new(self.root/'sealed.json', receipt)
            return {**receipt, 'seal_sha256':pin, 'live_admission_granted':False}


def _provider_source(pair, result, requested, completed):
    quote, rules = result['quote'], result['filters']
    if (quote['pair'] != pair or rules['pair'] != pair or not _sources(quote, rules)
            or not requested <= stamp(quote['observed_at']) <= completed
            or not requested <= stamp(rules['observed_at']) <= completed):
        raise ValueError('original full raw public request sources and causal availability required')


def _endpoint_sources(inputs, at):
    if set(inputs['quotes']) != set(inputs['filters']):raise ValueError('original endpoint quote/rule pairs required')
    for pair, quote in inputs['quotes'].items():
        rule = inputs['filters'][pair]
        if (quote['pair'] != pair or rule['pair'] != pair or not _sources(quote,rule)
                or stamp(quote['observed_at']) > at or stamp(rule['observed_at']) > at):
            raise ValueError('original raw endpoint sources required')


def _action_rows(prepared, complete, protocol):
    operation, inputs, result, changes = prepared['operation'], prepared['inputs'], complete['result'], complete['changes']
    if operation in {'mark','execute','cancel_pending','compact'}:
        return _operation_rows(prepared, complete, protocol)
    allowed = {
        'worker_enqueue': {'wallet.intents','worker.intent_links','worker.seen_predictions'},
        'worker_seen': {'worker.seen_predictions'}, 'worker_event': {'worker.worker_events'},
    }
    if operation not in allowed or any(c['source'] not in allowed[operation] or c['before'] is not None or c['after'] is None for c in changes):
        raise ValueError('original worker atomic action scope differs')
    at = prepared['at']
    if operation == 'worker_enqueue':
        if type(result) is not bool:raise ValueError('original worker enqueue result required')
        if inputs['side'] == 'Buy' and stamp(at) >= stamp(protocol['plan']['entry_cutoff']):
            raise ValueError('worker Buy after original entry cutoff')
        expected = [('wallet.intents', [inputs['intent_id'],inputs['pair'],inputs['side'],inputs['created_at'],at,'pending',None]),
                    ('worker.intent_links', [inputs['intent_id'],json.dumps(inputs['payload'],sort_keys=True,default=str)])]
        if inputs['source_key']:expected.append(('worker.seen_predictions',[inputs['source_key'],'queued',at]))
        if not 0 <= (stamp(at)-stamp(inputs['created_at'])).total_seconds() <= 5:
            raise ValueError('worker enqueue causal observation differs')
        if not result:expected = []
    elif operation == 'worker_seen':
        if result is not None or len(changes) > 1:raise ValueError('original worker seen result differs')
        expected = [('worker.seen_predictions',[inputs['identity'],inputs['status'],at])] if changes else []
    else:
        key = prepared['before']['sources']['worker.worker_events']['count']+1
        expected = [('worker.worker_events',[key,at,json.dumps(inputs['payload'],sort_keys=True,default=str)])]
        if result is not None:raise ValueError('original worker event result differs')
    actual = sorted((c['source'],c['after']) for c in changes)
    if actual != sorted(expected):raise ValueError('original worker atomic rows/input/result linkage differs')


def _prediction_link(prepared, tick, protocol):
    """Source identity and negative-status linkage, not a complete decision replay."""
    operation, inputs = prepared['operation'], prepared['inputs']
    if operation != 'worker_seen' and not (operation == 'worker_enqueue' and inputs['side'] == 'Buy'):return
    identity = inputs['identity'] if operation == 'worker_seen' else inputs['source_key']
    rows = tick['event']['inputs']['predictions']
    row = next((r for r in rows if digest((r['candidate_sha256']+'|'+r['opportunity']).encode()) == identity), None)
    if row is None or row['candidate_sha256'] != protocol['candidate_sha256']:
        raise ValueError('worker decision has no original source prediction')
    now, predicted = tick['decision_at'], stamp(row['predicted_at'])
    if now is None or not stamp(protocol['start']) <= predicted < stamp(protocol['end']):
        raise ValueError('original worker decision clock/source window differs')
    status = ('outside_window_or_future' if predicted > now else
        'unverified_prediction_observation' if not row.get('observed_at') or not predicted <= stamp(row['observed_at']) <= now else
        'candidate_rejected' if not row['would_enter'] else
        'source_prediction_expired' if now >= predicted+timedelta(seconds=PaperConfig(**protocol['config']).signal_expiry_seconds) else
        'paper_entry_window_finished' if now >= stamp(protocol['plan']['entry_cutoff']) else 'queued')
    if operation == 'worker_seen':
        if inputs['status'] != status or status == 'queued':raise ValueError('original negative prediction status differs')
    else:
        expected_payload = dict(source_prediction=row, source_deadline=(predicted+
            timedelta(seconds=PaperConfig(**protocol['config']).signal_expiry_seconds)).isoformat())
        if (status != 'queued' or inputs['intent_id'] != 'paper-buy:'+identity or inputs['pair'] != row['pair']
                or stamp(inputs['created_at']) != now or inputs['payload'] != expected_payload):
            raise ValueError('original worker Buy/source/deadline linkage differs')


def audit_worker_capture(root, *, expected_registration_sha256, expected_seal_sha256=None, clock=None):
    """Read-only bounded source trace, sealed before end, never an income gate."""
    root, registration, protocol, lifecycle, policy = _load(root, expected_registration_sha256)
    output = dict(schema_version='paper-worker-source-audit-v1', registration_sha256=expected_registration_sha256,
        protocol_sha256=registration['protocol_sha256'], role=protocol['role'], worker_source_trace_pass=False,
        source_poll_completeness_verified=False,
        full_worker_decision_replay_pass=False, full_fifo_replay_pass=False, coverage_evidence_pass=False,
        full_worker_or_host_qualified=False, paper_evidence_pass=False,
        economic_profitability_established=False, live_admission_granted=False)
    if stamp((clock or (lambda:datetime.now(UTC)))()) < stamp(protocol['end']):
        return {**output, 'status':'sealed_until_capture_end', 'performance_hidden':True}
    with _lease(root, writer=False):
        _inventory(root);seal = _metadata(root/'sealed.json', expected_seal_sha256)
        if (seal.get('schema_version') != SCHEMA or seal.get('registration_sha256') != expected_registration_sha256
                or seal.get('protocol_sha256') != registration['protocol_sha256']):
            raise ValueError('original worker seal identity required')
        log = SegmentedEventLog._load(root/'storage', registration['storage_manifest_sha256'])
        if log.manifest['source_protocol_sha256'] != registration['protocol_sha256'] or log.policy != SegmentPolicy(**protocol['storage_policy']):
            raise ValueError('original worker event identity required')
        source = NativePaperArchive.reader(root/'native', expected_manifest_sha256=registration['native_manifest_sha256'],
            expected_seal_sha256=seal['native_seal_sha256'])
        _source_identity(source, registration, protocol)
        state = terminal = tick = pending = None
        prefix, markets = {}, {}
        counts = dict(ticks=0, endpoint_marks=0, actions=0, market_requests=0, exit_requests=0,
                      failed_market_requests=0, failed_exit_requests=0, supplied_predictions=0)
        last_at, last_slot, n = stamp(protocol['registered_at']), -1, 0
        wall_pass = True
        for record in log.iter_events(expected_head_sha256=seal['head_sha256'], expected_catalog_sha256=seal['catalog_sha256']):
            n += 1;kind, event = record['kind'], record['payload'];at = stamp(event['at']);phase = event.get('phase')
            if at < last_at or terminal is not None:raise ValueError('original worker causal order differs')
            last_at = at
            if n == 1:
                if kind != 'genesis' or at != stamp(protocol['registered_at']) or event['role'] != protocol['role']:
                    raise ValueError('original worker genesis required')
                state = event['after'];_transition(state, state)
                if state != _initial(protocol, registration['native_manifest_sha256']):raise ValueError('original worker empty genesis differs')
                _checkpoint_refs(source, state, prefix);continue
            if kind == 'terminated':
                if (tick is not None or pending is not None or event['after'] != state or event['reason'] not in TERMINALS
                        or not stamp(protocol['start']) <= at <= stamp(protocol['end'])+timedelta(seconds=lifecycle.finalization_grace_seconds)
                        or event['reason'] == 'completed' and at < stamp(protocol['end'])):
                    raise ValueError('original worker terminal state/window differs')
                terminal = event;continue
            if phase == 'tick' and kind == 'prepared':
                if tick is not None or pending is not None or event['before'] != state:
                    raise ValueError('original whole tick preparation differs')
                mode = event['mode'];start, end = stamp(protocol['start']), stamp(protocol['end'])
                if mode not in {'tick','endpoint'} or (mode == 'tick' and not start <= at < end) or (mode == 'endpoint' and at != end):
                    raise ValueError('original worker tick window differs')
                slot = protocol['plan']['poll_slots'] if mode == 'endpoint' else int(seconds(at-start)//lifecycle.poll_seconds)
                reserve = ((policy.events_per_tick if mode == 'tick' else 4)+4)*log.policy.maximum_record_bytes+65536
                reserve += 3*source.policy.maximum_active_bytes+2*source.policy.maximum_batch_bytes
                if (event['slot'] != slot or slot <= last_slot or resource_blocker(lifecycle, event['resources'],
                        reserve_bytes=reserve)):
                    raise ValueError('original worker slot/resource bounds differ')
                if mode == 'tick':
                    data = event['inputs']
                    _batch(data['predictions'], data['source_id'], data['source_observed_at'], data['source_sha256'],
                        policy=policy, config=PaperConfig(**protocol['config']), now=at,
                        maximum_bytes=log.policy.maximum_record_bytes-4096)
                    counts['supplied_predictions'] += len(data['predictions'])
                else:_market_input(event['inputs']);_endpoint_sources(event['inputs'], at)
                tick = dict(seq=n, event=event, clocks=0, actions=0, market=0, exit=0, events=1, report=None,
                    decision_at=None, provider_successes=0, leaf_wall_ns=0)
                last_slot, markets = slot, {};continue
            if tick is None or event.get('tick_sequence') != tick['seq'] or at > stamp(protocol['end']):
                raise ValueError('original worker tick parent/window differs')
            tick['events'] += 1
            if tick['events'] > policy.events_per_tick:raise ValueError('original tick event bound differs')
            if phase in {'clock','monotonic'}:
                tick['clocks'] += 1
                if kind != 'complete' or pending is not None or tick['clocks'] > policy.maximum_clock_calls_per_tick:
                    raise ValueError('original worker clock trace differs')
                if phase == 'clock' and tick['decision_at'] is None:tick['decision_at'] = at
                if phase == 'monotonic':
                    value = event['value']
                    if type(value) is not float or not 0 <= value or value < tick.get('last_monotonic',0):
                        raise ValueError('original worker monotonic observation differs')
                    tick['last_monotonic'] = value
                continue
            if phase == 'tick' and kind == 'complete':
                if (pending is not None or event['prepared_seq'] != tick['seq'] or event['slot'] != last_slot
                        or event['after'] != state or type(event['operation_wall_ns']) is not int
                        or event['operation_wall_ns'] < tick['leaf_wall_ns']):
                    raise ValueError('original whole tick completion differs')
                if tick['event']['mode'] == 'tick':
                    if (tick['report'] != event['result'] or event['result']['status'] != 'paper_tick_complete'
                            or event['result']['market_observations'] != tick['provider_successes']):
                        raise ValueError('original worker report/result differs')
                    counts['ticks'] += 1
                else:
                    if tick['actions'] != 1 or tick['endpoint'] != event['result']:
                        raise ValueError('original endpoint mark differs')
                    counts['endpoint_marks'] += 1
                wall_pass &= event['operation_wall_ns'] <= lifecycle.maximum_operation_wall_seconds*1000000000
                tick = None;continue
            if kind == 'prepared':
                if pending is not None or phase not in {'action','market','exit'}:
                    raise ValueError('original worker call preparation differs')
                if tick['event']['mode'] == 'endpoint' and (phase != 'action' or event['operation'] != 'mark'):
                    raise ValueError('only original mark allowed at endpoint')
                field = 'actions' if phase == 'action' else phase
                tick[field] += 1
                maximum = (policy.maximum_actions_per_tick if phase == 'action' else
                    policy.maximum_market_requests_per_tick if phase == 'market' else policy.maximum_exit_requests_per_tick)
                if tick[field] > maximum or phase == 'action' and event['before'] != state:
                    raise ValueError('original bounded worker call/state differs')
                pending = (n, event);continue
            if (kind != 'complete' or pending is None or phase != pending[1]['phase']
                    or event['prepared_seq'] != pending[0] or type(event['operation_wall_ns']) is not int or event['operation_wall_ns'] < 0):
                raise ValueError('original worker call completion differs')
            prepared = pending[1]
            tick['leaf_wall_ns'] += event['operation_wall_ns']
            if phase in {'market','exit'}:
                counts[phase+'_requests'] += 1
                if event['error'] is not None:
                    if event['result'] is not None or type(event['error']) is not str or not event['error'].isidentifier():
                        raise ValueError('bounded original provider failure required')
                    counts['failed_'+phase+'_requests'] += 1
                elif phase == 'market':
                    _market_input(event['result']);_provider_source(prepared['pair'], event['result'], stamp(prepared['at']), at)
                    markets[prepared['pair']] = event['result']
                    tick['provider_successes'] += 1
                else:
                    result = event['result']
                    if type(result['exits']) is not bool or type(result['reasons']) is not list or any(type(r) is not str for r in result['reasons']):
                        raise ValueError('original typed exit indicator required')
            else:
                _transition(state, event['after']);_checkpoint_refs(source, event['after'], prefix)
                if (event['after']['checkpoint']['generation'] > state['checkpoint']['generation']
                        and event['after']['checkpoint']['watermarks'] != _compaction_watermarks(state)):
                    raise ValueError('original worker compaction watermark differs')
                _action_rows(prepared, event, protocol)
                _prediction_link(prepared, tick, protocol)
                if _apply(state['sources'], event['changes'], maximum_bytes=log.policy.maximum_record_bytes) != event['after']['sources']:
                    raise ValueError('original worker delta/commitment differs')
                operation, inputs = prepared['operation'], prepared['inputs']
                if operation in {'mark','execute'}:
                    if tick['event']['mode'] == 'endpoint':
                        if inputs != tick['event']['inputs']:raise ValueError('original endpoint input differs')
                        tick['endpoint'] = event['result']
                    else:
                        expected = (dict(quotes={p:v['quote'] for p,v in markets.items()},filters={p:v['filters'] for p,v in markets.items()})
                            if operation == 'mark' else dict(intent_id=inputs['intent_id'], **markets[inputs['quote']['pair']]))
                        if inputs != expected:raise ValueError('wallet inputs differ from original available provider sources')
                if operation == 'worker_event' and inputs['payload'].get('status') == 'paper_tick_complete':
                    tick['report'] = inputs['payload']
                counts['actions'] += 1;state = event['after']
            pending = None
        if tick is not None or pending is not None or terminal is None or n != seal['sequence']:
            raise ValueError('original completed whole worker trace required')
        _transition(state, seal['native_after'])
        if (seal['native_after']['sources'] != state['sources']
                or seal['native_after']['checkpoint']['generation'] != state['checkpoint']['generation']+1
                or seal['native_after']['checkpoint']['watermarks'] != _compaction_watermarks(state)):
            raise ValueError('original worker final compaction differs')
        _checkpoint_refs(source, seal['native_after'], prefix)
        summary = _empty()
        for name in SOURCES:
            for row in source.iter_rows(name):_adjust(summary, name, _valid_row(name,row), 1)
        with source._lease(writer=False):
            active = _active(source)
            for name in AUXILIARY:
                for row in active[name].values():_adjust(summary, name, row, 1)
            if dict(sources=summary,checkpoint=_checkpoint(source)) != seal['native_after']:
                raise ValueError('original final worker source union/checkpoint differs')
            source._check_seal();source._check_native()
        _load(root, expected_registration_sha256)
        if _metadata(root/'sealed.json', expected_seal_sha256) != seal:raise ValueError('worker seal changed during audit')
    return {**output, 'status':'worker_sources_and_native_actions_replayed', 'performance_hidden':False,
        'worker_source_trace_pass':True, 'events_checked':n, **counts, 'operation_wall_budget_pass':wall_pass,
        'terminal_reason':terminal['reason'], 'scope':'captured_sources_and_native_linkage_not_independent_decisions_or_profit'}
