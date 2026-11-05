"""Opt-in, new-study-only paper mark sources and causal operation ordering.

This does not change the frozen paper producer or confer trading admission.
An unfinished operation blocks reuse; its sources must never be backfilled.
The hash chain detects drift relative to retained pins, not a malicious rewrite
of every local database and external reference.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN, getcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from time import monotonic_ns

from cryptoforge.paper_market import normalize_market, observe_market
from cryptoforge.paper_runtime import paper_runtime_hashes
from cryptoforge.paper_wallet import PaperConfig, PaperWallet
from cryptoforge.paper_fill_audit import verify_paper_fill_arithmetic
from cryptoforge.paper_lifecycle import (
    CoverageTimeline, PaperLifecycle, mark_valid_until, measure_resources, resource_blocker, seconds,
)

MAX_BYTES = 64 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024
SCHEMA = 'prospective-paper-valuation-v1'
LIFECYCLE_SCHEMA = 'prospective-paper-valuation-v2'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate capture JSON field')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite capture JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def stamp(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('aware capture clock required')
    return result.astimezone(UTC)


def number(value, *, positive=False):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise ValueError('finite nonnegative valuation amount required')
    return result


def runtime_hashes():
    runner = Path(__file__).resolve().parents[2]/'scripts/audit_paper_valuation.py'
    return {**paper_runtime_hashes(), 'valuation_capture': digest(Path(__file__).read_bytes()),
            'valuation_audit_runner': digest(runner.read_bytes()),
            'valuation_lifecycle': digest(Path(__file__).with_name('paper_lifecycle.py').read_bytes())}


def decimal_contract():
    context = getcontext()
    return {**{key: getattr(context, key) for key in ('prec', 'rounding', 'Emin', 'Emax', 'clamp')},
            'traps': sorted(key.__name__ for key, value in context.traps.items() if value)}


def _file(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink():
        raise ValueError('capture paths cannot use symlinks')
    info = path.stat()
    if not path.is_file() or info.st_nlink != 1 or info.st_size > MAX_BYTES:
        raise ValueError('bounded single-link capture file required')
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(path) + suffix).exists():
            raise ValueError('capture requires quiescent DELETE-mode files')
    return path


def _read_db(path):
    db = sqlite3.connect(_file(path).as_uri() + '?mode=ro', uri=True, timeout=1)
    db.execute('PRAGMA query_only=ON')
    if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
        db.close()
        raise ValueError('DELETE-mode capture database required')
    if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1").fetchone():
        db.close()
        raise ValueError('capture cannot use views or triggers')
    return db


def fingerprint(path):
    path = _file(path)
    before = path.stat()
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024*1024), b''):
            sha.update(chunk)
    after = path.stat()
    if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns):
        raise ValueError('capture source changed while being read')
    return dict(sha256=sha.hexdigest(), inode=after.st_ino, device=after.st_dev,
                size=after.st_size, mtime_ns=after.st_mtime_ns)


def _wallet_state(path):
    db = _read_db(path)
    try:
        db.execute('BEGIN')
        state = dict(db.execute('SELECT key,value FROM state'))
        lots = [dict(zip(('id', 'pair', 'opened_at', 'qty', 'cost', 'entry_fee_quote'), row))
                for row in db.execute('SELECT * FROM lots ORDER BY opened_at,id')]
        filters = {pair: parse(raw) for pair, raw in db.execute('SELECT pair,filters FROM market_cache')}
        if len(lots) > 2000 or len(filters) > 100:
            raise ValueError('capture inventory resource limit exceeded')
        return dict(state=state, lots=lots, filters=filters,
                    fills=db.execute('SELECT count(*) FROM fills').fetchone()[0],
                    marks=db.execute('SELECT count(*) FROM marks').fetchone()[0])
    finally:
        db.close()


def observe_valuation_market(client, pair, *, clock=None):
    """Retain the FULL public instrument response as well as the book response."""
    if client.base_url != 'https://api.bybit.com':
        raise ValueError('exact global public Bybit origin required')
    responses = {}

    class PublicCapture:
        base_url = client.base_url

        def _get_json(self, endpoint, parameters):
            if endpoint not in {'/v5/market/instruments-info', '/v5/market/orderbook'}:
                raise ValueError('only public mark sources allowed')
            response = client._get_json(endpoint, parameters)
            responses[endpoint] = deepcopy(response)
            return response

    quote, filters = observe_market(PublicCapture(), pair, clock=clock)
    filters['raw_response'] = responses['/v5/market/instruments-info']
    return quote, filters


def _sources(quote, filters):
    """Check raw-source hashes AND normalization, when both raw sources exist."""
    if not quote or not filters or 'raw_orderbook' not in quote or 'raw_response' not in filters:
        return False
    normalized_quote, normalized_filters = normalize_market(
        quote['pair'], filters['raw_response'], quote['raw_orderbook'],
        instrument_at=stamp(filters['observed_at']), book_at=stamp(quote['observed_at']))
    return (canonical(normalized_quote) == canonical(quote)
            and canonical(normalized_filters) == canonical({k: v for k, v in filters.items() if k != 'raw_response'}))


def replay_liquidation(before, quotes, filters, config, observed_at):
    """Independent Decimal valuation; never call the producer's mark/sale code."""
    now = stamp(observed_at)
    cash = number(before['state']['cash'])
    inventory = {}
    for lot in before['lots']:
        qty, basis = number(lot['qty']), number(lot['cost'])
        if qty:
            item = inventory.setdefault(lot['pair'], [Decimal(0), Decimal(0)])
            item[0] += qty
            item[1] += basis
    gross = liquidation = cash
    missing, uncertain, dust, normalized_only = [], [], [], []
    for pair, (qty, basis) in inventory.items():
        quote = quotes.get(pair)
        if (not quote or quote.get('pair') != pair or not timedelta(0) <=
                now-stamp(quote['observed_at']) <= timedelta(seconds=config.quote_max_age_seconds)):
            missing.append(pair)
            continue
        bid = number(quote['bid'], positive=True)
        gross += qty*bid
        try:
            rule = filters[pair]
            if (quote.get('market'), quote.get('venue'), rule.get('market'), rule.get('venue'),
                    rule.get('status'), rule.get('pair')) != (
                        'spot', 'bybit_global', 'spot', 'bybit_global', 'Trading', pair):
                raise ValueError('global Trading Spot valuation required')
            if not timedelta(0) <= now-stamp(rule['observed_at']) <= timedelta(seconds=config.filter_max_age_seconds):
                raise ValueError('unavailable instrument rules')
            if bid > number(quote['ask'], positive=True):
                raise ValueError('crossed mark book')
            depth = number(quote['bid_qty'], positive=True)
            number(quote['ask_qty'], positive=True)
            step = number(rule['quantity_step'], positive=True)
            minimum = number(rule['minimum_notional'], positive=True)
            maximum = number(rule['maximum_market_quantity'], positive=True)
            rounded = (qty/step).to_integral_value(rounding=ROUND_DOWN)*step
            price = bid*(1-config.slippage)
            if rounded == 0 or rounded*price < minimum:
                if basis <= config.stake*config.max_dust_basis_fraction:
                    dust.append(pair)
            elif rounded > maximum or rounded > depth*config.max_depth_fraction:
                uncertain.append(pair)
            else:
                # Separate operations match the producer's Decimal rounding order.
                notional = rounded*price
                liquidation += notional*(1-config.exit_fee)
            if not _sources(quote, rule):
                normalized_only.append(pair)
        except (ValueError, KeyError, TypeError):
            uncertain.append(pair)
    mark = dict(mode='paper', observed_at=now.isoformat(), cash=str(cash),
                equity=str(liquidation) if not missing and not uncertain else None,
                gross_bid_equity=str(gross) if not missing else None,
                missing_mark_pairs=sorted(set(missing)), uncertain_liquidation_pairs=sorted(set(uncertain)),
                nontradable_small_basis_pairs=sorted(dust),
                valuation='conditional_top_book_liquidation_after_fee_slip_dust_zero_assumption',
                live_eligible=False)
    return mark, dict(raw_sources_verified=not (missing or uncertain or normalized_only),
                      normalized_only_pairs=sorted(normalized_only),
                      conditional_valuation_known=not (missing or uncertain))


def _market_input(value):
    # Never accept credentials/notes alongside retained public sources.
    def check(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if re.search(r'(?i)secret|api.?key|authorization|password|token|cookie|service.?role|private.?key', key):
                    raise ValueError('credentials cannot enter paper capture')
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
    raw = canonical(value)
    if len(raw) > MAX_EVENT_BYTES:
        raise ValueError('bounded capture payload required')
    value = parse(raw)
    check(value)
    quote_fields = {'pair', 'market', 'venue', 'observed_at', 'bid', 'ask', 'bid_qty', 'ask_qty',
                    'source_server_timestamp_ms', 'source_update_id', 'source_sha256', 'raw_orderbook', 'source'}
    filter_fields = {'pair', 'market', 'venue', 'status', 'observed_at', 'quantity_step',
                     'minimum_notional', 'maximum_market_quantity', 'source_sha256', 'raw_instrument',
                     'source', 'raw_response'}
    quotes = value.get('quotes', {}).values() if 'quotes' in value else [value['quote']]
    filters = value['filters'].values() if 'quotes' in value else [value['filters']]
    if any(set(item)-quote_fields for item in quotes) or any(set(item)-filter_fields for item in filters):
        raise ValueError('only allowlisted public market fields can be retained')
    return value


def _load_protocol(root, pin):
    root = Path(root).absolute()
    raw = _file(root/'protocol.json').read_bytes()
    if len(raw) > MAX_EVENT_BYTES or digest(raw) != pin:
        raise ValueError('original capture protocol pin differs')
    protocol = parse(raw)
    if (protocol.get('schema_version') not in {SCHEMA, LIFECYCLE_SCHEMA} or protocol.get('root') != str(root)
            or protocol.get('research_only') is not True or protocol.get('live_eligible') is not False):
        raise ValueError('isolated research capture protocol required')
    if not stamp(protocol['registered_at']) < stamp(protocol['start']) < stamp(protocol['end']):
        raise ValueError('prospective capture preregistration required')
    if protocol['implementation_hashes'] != runtime_hashes():
        raise ValueError('capture runtime drift requires a new preregistration')
    if protocol['decimal_contract'] != decimal_contract():
        raise ValueError('capture Decimal context differs from preregistration')
    if protocol['schema_version'] == LIFECYCLE_SCHEMA:
        lifecycle = PaperLifecycle.from_payload(protocol['lifecycle'])
        if (lifecycle.plan(protocol['start'], protocol['end'], max_events=protocol['max_events'])
                != protocol['lifecycle_plan'] or resource_blocker(lifecycle, protocol['registration_resources'])):
            raise ValueError('original lifecycle preregistration differs')
    elif any(key in protocol for key in ('lifecycle', 'lifecycle_plan', 'registration_resources')):
        raise ValueError('legacy capture cannot adopt lifecycle fields')
    return root, protocol


class CapturedPaperWallet:
    """PaperWorker-compatible adapter, only for a NEW isolated namespace.

    An event is committed BEFORE each producer operation. If its completion
    cannot be retained, the prepared event remains and blocks further calls.
    """
    @classmethod
    def create(cls, root, *, candidate_sha, config, start, end, max_events=10000, lifecycle=None, clock=None):
        clock = clock or (lambda: datetime.now(UTC))
        root = Path(root).absolute()
        if root.resolve() != root or root.is_symlink():
            raise ValueError('isolated nonsymlink namespace required')
        if type(max_events) is not int or not 3 <= max_events <= 10000:
            raise ValueError('bounded event budget required')
        if not isinstance(config, PaperConfig):
            raise ValueError('explicit frozen paper config required')
        hashes = runtime_hashes()
        observed, start, end = stamp(clock()), stamp(start), stamp(end)
        if not observed < start < end:
            raise ValueError('register a new protocol before its future window')
        lifecycle_fields = {}
        if lifecycle is not None:
            if not isinstance(lifecycle, PaperLifecycle):
                raise ValueError('explicit typed lifecycle required')
            plan = lifecycle.plan(start, end, max_events=max_events)
            measured = measure_resources(root)
            if resource_blocker(lifecycle, measured):
                raise ValueError('resources do not satisfy prospective lifecycle contract')
            lifecycle_fields = dict(lifecycle=lifecycle.payload(), lifecycle_plan=plan, registration_resources=measured)
        root.mkdir(mode=0o700, parents=True, exist_ok=False)
        wallet = PaperWallet(root/'wallet.sqlite', candidate_sha=candidate_sha, config=config, clock=clock)
        protocol = dict(schema_version=LIFECYCLE_SCHEMA if lifecycle is not None else SCHEMA,
                        root=str(root), candidate_sha256=candidate_sha,
                        config=parse(json.dumps(asdict(config), default=str)), start=start.isoformat(),
                        end=end.isoformat(), registered_at=observed.isoformat(), max_events=max_events,
                        implementation_hashes=hashes, decimal_contract=decimal_contract(),
                        research_only=True, live_eligible=False, **lifecycle_fields)
        raw = canonical(protocol)
        with (root/'protocol.json').open('xb') as output:
            output.write(raw)
        (root/'protocol.json').chmod(0o600)
        pin = digest(raw)
        db = sqlite3.connect(root/'events.sqlite')
        try:
            db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,previous TEXT NOT NULL,sha TEXT NOT NULL)')
            payload = canonical(dict(at=observed.isoformat(), wallet=_wallet_state(wallet.path)))
            sha = digest(canonical(dict(seq=1, kind='genesis', payload=parse(payload), previous=pin)))
            with db:
                db.execute('INSERT INTO events VALUES (1,?,?,?,?)', ('genesis', payload.decode(), pin, sha))
        finally:
            db.close()
        (root/'events.sqlite').chmod(0o600)
        return cls.resume(root, expected_protocol_sha256=pin, clock=clock)

    @classmethod
    def resume(cls, root, *, expected_protocol_sha256, clock=None):
        root, protocol = _load_protocol(root, expected_protocol_sha256)
        _file(root/'wallet.sqlite')
        _file(root/'events.sqlite')
        obj = cls()
        obj.root, obj.protocol, obj.protocol_sha256 = root, protocol, expected_protocol_sha256
        obj.clock = clock or (lambda: datetime.now(UTC))
        obj.config = PaperConfig(**protocol['config'])
        obj.lifecycle = PaperLifecycle.from_payload(protocol['lifecycle']) if 'lifecycle' in protocol else None
        obj.candidate_sha = protocol['candidate_sha256']
        obj.path = root/'wallet.sqlite'
        with obj._lock():
            events = obj._head()
            if events[1] not in {'genesis', 'complete', 'terminated'}:
                raise ValueError('unfinished capture operation requires review; no retry or backfill')
            payload = parse(events[2])
            expected = payload['wallet'] if events[1] == 'genesis' else payload['after']
            if _wallet_state(obj.path) != expected:
                raise ValueError('uncaptured wallet mutation requires review')
            obj._wallet = PaperWallet(obj.path, candidate_sha=obj.candidate_sha, config=obj.config, clock=obj.clock)
        return obj

    @contextmanager
    def _lock(self):
        fd = os.open(self.root/'capture.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if os.fstat(fd).st_nlink != 1:
                raise ValueError('single-link capture lock required')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def _head(self):
        db = _read_db(self.root/'events.sqlite')
        try:
            row = db.execute('SELECT seq,kind,payload,previous,sha FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            count = db.execute('SELECT count(*) FROM events').fetchone()[0]
            if not row or row[0] != count:
                raise ValueError('capture sequence gap')
            if digest(canonical(dict(seq=row[0], kind=row[1], payload=parse(row[2]), previous=row[3]))) != row[4]:
                raise ValueError('capture head hash differs')
            return row
        finally:
            db.close()

    def _append(self, kind, payload):
        head = self._head()
        raw = canonical(payload)
        if len(raw) > MAX_EVENT_BYTES or head[0] >= self.protocol['max_events']:
            raise ValueError('capture resource budget exhausted')
        seq = head[0]+1
        sha = digest(canonical(dict(seq=seq, kind=kind, payload=payload, previous=head[4])))
        db = sqlite3.connect(self.root/'events.sqlite', timeout=1)
        try:
            with db:
                db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (seq, kind, raw.decode(), head[4], sha))
        finally:
            db.close()
        return seq

    def _verify_identity(self):
        _, original = _load_protocol(self.root, self.protocol_sha256)
        if (original != self.protocol or self.config != PaperConfig(**original['config'])
                or self.candidate_sha != original['candidate_sha256']
                or (self.lifecycle.payload() if self.lifecycle else None) != original.get('lifecycle')
                or self._wallet.config != self.config or self._wallet.candidate_sha != self.candidate_sha):
            raise ValueError('in-memory capture identity differs from original freeze')

    def _operation(self, kind, inputs):
        inputs = _market_input(inputs)
        with self._lock():
            self._verify_identity()
            head = self._head()
            if head[1] == 'terminated':
                raise ValueError('capture terminated; no further operations')
            if head[1] not in {'genesis', 'complete'}:
                raise ValueError('unfinished capture operation; no retry or backfill')
            if head[0]+2+int(self.lifecycle is not None) > self.protocol['max_events']:
                raise ValueError('capture event budget exhausted before operation')
            if (self.root/'events.sqlite').stat().st_size + 8*MAX_EVENT_BYTES > MAX_BYTES:
                raise ValueError('capture byte budget exhausted before operation')
            previous = parse(head[2])
            before = _wallet_state(self.path)
            if before != (previous['wallet'] if head[1] == 'genesis' else previous['after']):
                raise ValueError('uncaptured wallet mutation requires review')
            now = stamp(self.clock())
            if (now < stamp(previous['at']) or not stamp(self.protocol['start']) <= now <= stamp(self.protocol['end'])
                    or (kind == 'execute' and now == stamp(self.protocol['end']))):
                raise ValueError('operation outside prospective capture window')
            lifecycle_fields = {}
            if self.lifecycle is not None:
                slot = int(seconds(now-stamp(self.protocol['start']))//self.lifecycle.poll_seconds)
                if now == stamp(self.protocol['end']):
                    slot = self.protocol['lifecycle_plan']['poll_slots']
                count = previous.get('slot_operations', 0)+1 if previous.get('slot') == slot else 1
                limit = 1 if now == stamp(self.protocol['end']) else self.lifecycle.maximum_operations_per_poll
                measured = measure_resources(self.root)
                reason = resource_blocker(self.lifecycle, measured, reserve_bytes=8*MAX_EVENT_BYTES)
                if count > limit or reason:
                    self._terminate_locked('operation_rate_budget' if count > limit else 'resource_budget', resources=measured)
                    raise ValueError('lifecycle resource/operation budget terminated capture')
                if kind == 'execute' and now >= stamp(self.protocol['lifecycle_plan']['entry_cutoff']):
                    with self._db() as db:
                        row = db.execute('SELECT side FROM intents WHERE id=?', (inputs['intent_id'],)).fetchone()
                    if row and row[0] == 'Buy':
                        raise ValueError('lifecycle entry cutoff forbids new Buy fills')
                lifecycle_fields = dict(slot=slot, slot_operations=count, resources=measured)
            seq = self._append('prepared', dict(at=now.isoformat(), operation=kind, inputs=inputs,
                                                before=before, **lifecycle_fields))
            # One source event clock for the wrapper and native producer.
            self._wallet.clock = lambda: now
            operation_started = monotonic_ns()
            try:
                if kind == 'mark':
                    result = self._wallet.mark(inputs['quotes'], inputs['filters'])
                else:
                    result = self._wallet.execute(inputs['intent_id'], inputs['quote'], inputs['filters'])
            finally:
                self._wallet.clock = self.clock
            after = _wallet_state(self.path)
            wall_ns = monotonic_ns()-operation_started
            completed = stamp(self.clock())
            if not now <= completed <= stamp(self.protocol['end']):
                raise ValueError('operation completion outside causal capture window; review required')
            self._append('complete', dict(at=completed.isoformat(), prepared_seq=seq,
                                         result=result, after=after,
                                         **({**lifecycle_fields, 'operation_wall_ns': wall_ns} if self.lifecycle else {})))
            if self.lifecycle and wall_ns > self.lifecycle.maximum_operation_wall_seconds*1000000000:
                self._terminate_locked('operation_wall_budget')
                raise ValueError('lifecycle operation wall budget exceeded')
            return result

    def _terminate_locked(self, reason, *, resources=None):
        allowed = {'completed', 'operator_abort', 'resource_budget', 'operation_rate_budget', 'operation_wall_budget'}
        if self.lifecycle is None or reason not in allowed:
            raise ValueError('explicit lifecycle termination reason required')
        head = self._head()
        if head[1] not in {'genesis', 'complete'}:
            raise ValueError('unfinished or terminated capture cannot be finalized again')
        previous, now = parse(head[2]), stamp(self.clock())
        end = stamp(self.protocol['end'])
        if (now < max(stamp(previous['at']), stamp(self.protocol['start']))
                or now > end+timedelta(seconds=self.lifecycle.finalization_grace_seconds)
                or (reason == 'completed' and now < end)):
            raise ValueError('termination outside preregistered lifecycle bounds')
        state = _wallet_state(self.path)
        if state != (previous['wallet'] if head[1] == 'genesis' else previous['after']):
            raise ValueError('uncaptured wallet mutation before termination')
        seq = self._append('terminated', dict(at=now.isoformat(), reason=reason, after=state,
                                             resources=resources))
        return dict(status='terminated', reason=reason, sequence=seq, live_admission_granted=False)

    def terminate(self, reason):
        with self._lock():
            self._verify_identity()
            return self._terminate_locked(reason)

    def mark(self, quotes, filters_by_pair=None):
        return self._operation('mark', dict(quotes=quotes, filters=filters_by_pair or {}))

    def execute(self, intent_id, quote, filters):
        return self._operation('execute', dict(intent_id=intent_id, quote=quote, filters=filters))

    def enqueue(self, intent_id, pair, side, *, created_at):
        if self.lifecycle:
            self._verify_identity()
            now = stamp(self.clock())
            if (self._head()[1] == 'terminated' or not stamp(self.protocol['start']) <= now < stamp(self.protocol['end'])
                    or (side == 'Buy' and now >= stamp(self.protocol['lifecycle_plan']['entry_cutoff']))):
                raise ValueError('lifecycle entry window closed')
        return self._wallet.enqueue(intent_id, pair, side, created_at=created_at)

    def snapshot(self):
        return self._wallet.snapshot()

    def pending_intents(self):
        return self._wallet.pending_intents()

    def cancel_pending(self, *args, **kwargs):
        return self._wallet.cancel_pending(*args, **kwargs)

    def _db(self):
        # Existing PaperWorker writes only pending-intent linkage through this API.
        return self._wallet._db()


def _inventory_after(before, fill):
    cash, lots = number(before['state']['cash']), deepcopy(before['lots'])
    qty = number(fill['quantity'], positive=True)
    if fill['side'] == 'Buy':
        cash -= number(fill['cost'], positive=True)
        lots.append(dict(id=fill['intent_id'], pair=fill['pair'], opened_at=fill['filled_at'],
                         qty=str(qty), cost=fill['cost'], entry_fee_quote=fill['fee_quote_equivalent']))
    elif fill['side'] == 'Sell':
        cash += number(fill['proceeds'])
        left = qty
        for lot in lots:
            owned = number(lot['qty'])
            if lot['pair'] != fill['pair'] or not owned or not left:
                continue
            sold = min(owned, left)
            fraction = sold/owned
            lot['qty'] = str(owned-sold)
            lot['cost'] = str(number(lot['cost'])-number(lot['cost'])*fraction)
            lot['entry_fee_quote'] = str(number(lot['entry_fee_quote'])-number(lot['entry_fee_quote'])*fraction)
            left -= sold
        if left:
            raise ValueError('capture fill sells unavailable inventory')
    else:
        raise ValueError('Spot fill side required')
    number(cash)
    return str(cash), sorted(lots, key=lambda lot: (lot['opened_at'], lot['id']))


def audit_valuation_capture(root, *, expected_protocol_sha256, clock=None):
    """Sealed CLI audit; outcomes are read only after the preregistered end."""
    now = stamp((clock or (lambda: datetime.now(UTC)))())
    root, protocol = _load_protocol(root, expected_protocol_sha256)
    output = dict(schema_version='paper-valuation-audit-v1', protocol_sha256=expected_protocol_sha256,
                  live_admission_granted=False, economic_profitability_established=False)
    if now < stamp(protocol['end']):
        return {**output, 'status': 'sealed_until_capture_end', 'performance_hidden': True}
    config = PaperConfig(**protocol['config'])
    lifecycle = PaperLifecycle.from_payload(protocol['lifecycle']) if 'lifecycle' in protocol else None
    coverage = CoverageTimeline(protocol['start'], protocol['end'], lifecycle) if lifecycle else None
    sources = {name: fingerprint(root/name) for name in ('protocol.json', 'events.sqlite', 'wallet.sqlite')}
    db = _read_db(root/'events.sqlite')
    try:
        wallet_db = _read_db(root/'wallet.sqlite')
    except Exception:
        db.close()
        raise
    previous, sequence, prepared, state = expected_protocol_sha256, 0, None, None
    fills, marks, raw, known, raw_fills = [], 0, 0, 0, 0
    last_at = stamp(protocol['registered_at'])
    terminal, last_mark, last_quality, previous_slot, slot_operations = None, None, None, None, 0
    wall_budget_pass = True
    try:
        db.execute('BEGIN')
        wallet_db.execute('BEGIN')
        for seq, kind, payload, before_sha, sha in db.execute('SELECT * FROM events ORDER BY seq'):
            sequence += 1
            if sequence > protocol['max_events'] or seq != sequence or before_sha != previous or len(payload.encode()) > MAX_EVENT_BYTES:
                raise ValueError('capture sequence/resource/hash chain differs')
            event = parse(payload)
            if digest(canonical(dict(seq=seq, kind=kind, payload=event, previous=before_sha))) != sha:
                raise ValueError('capture event hash differs')
            previous = sha
            at = stamp(event['at'])
            upper = stamp(protocol['end'])
            if kind == 'terminated' and lifecycle:
                upper += timedelta(seconds=lifecycle.finalization_grace_seconds)
            if terminal is not None or not last_at <= at <= upper:
                raise ValueError('capture event clock differs')
            last_at = at
            if seq == 1:
                state = event['wallet']
                expected_policy = json.dumps(dict(candidate_sha=protocol['candidate_sha256'], config=asdict(config)), sort_keys=True, default=str)
                if (kind != 'genesis' or at != stamp(protocol['registered_at'])
                        or state['state'] != {'cash': str(config.capital), 'policy': expected_policy}
                        or state['lots'] or state['marks'] or state['fills'] or state['filters']):
                    raise ValueError('capture must start at original empty paper wallet')
                continue
            if not stamp(protocol['start']) <= at:
                raise ValueError('capture event before registered window')
            if kind == 'terminated':
                if (not lifecycle or prepared is not None or event['after'] != state
                        or event['reason'] not in {'completed', 'operator_abort', 'resource_budget',
                                                   'operation_rate_budget', 'operation_wall_budget'}
                        or (event['reason'] == 'completed' and at < stamp(protocol['end']))):
                    raise ValueError('invalid original lifecycle termination')
                terminal = event
                coverage.invalidate(at)
                continue
            if kind == 'prepared':
                if prepared is not None or state != event['before']:
                    raise ValueError('capture operation ordering or before-state differs')
                prepared = (seq, event)
                if lifecycle:
                    coverage.invalidate(at)
                    slot = int(seconds(at-stamp(protocol['start']))//lifecycle.poll_seconds)
                    if at == stamp(protocol['end']):
                        slot = protocol['lifecycle_plan']['poll_slots']
                    slot_operations = slot_operations+1 if previous_slot == slot else 1
                    limit = 1 if at == stamp(protocol['end']) else lifecycle.maximum_operations_per_poll
                    if (event['slot'] != slot or event['slot_operations'] != slot_operations
                            or slot_operations > limit or resource_blocker(lifecycle, event['resources'],
                                                                         reserve_bytes=8*MAX_EVENT_BYTES)):
                        raise ValueError('original operation violates lifecycle resource/slot budget')
                    previous_slot = slot
                continue
            if kind != 'complete' or prepared is None or event['prepared_seq'] != prepared[0]:
                raise ValueError('capture completion lacks original preparation')
            start = prepared[1]
            inputs, result, after = start['inputs'], event['result'], event['after']
            if lifecycle:
                if (any(event[key] != start[key] for key in ('slot', 'slot_operations', 'resources'))
                        or type(event['operation_wall_ns']) is not int or event['operation_wall_ns'] < 0):
                    raise ValueError('original operation resource evidence differs')
                wall_budget_pass &= event['operation_wall_ns'] <= lifecycle.maximum_operation_wall_seconds*1000000000
            expected_cash, expected_lots = state['state']['cash'], state['lots']
            expected_fills, expected_marks = state['fills'], state['marks']
            expected_filters = state['filters']
            if start['operation'] == 'mark':
                filters = {**state['filters'], **inputs['filters']}
                expected_filters = filters
                expected_mark, quality = replay_liquidation(state, inputs['quotes'], filters, config, start['at'])
                if result != expected_mark:
                    raise ValueError('original mark differs from independent liquidation replay')
                last_mark, last_quality = result, quality
                if lifecycle:
                    deadline = mark_valid_until(lifecycle, start['at'], state, inputs['quotes'], filters, config)
                    coverage.mark(at, deadline, sources_known=quality['raw_sources_verified']
                                  and quality['conditional_valuation_known'])
                marks += 1
                raw += int(quality['raw_sources_verified'])
                known += int(quality['conditional_valuation_known'])
                expected_marks += 1
                row = wallet_db.execute('SELECT payload FROM marks WHERE id=?', (expected_marks,)).fetchone()
                if not row or parse(row[0]) != result:
                    raise ValueError('original wallet mark missing or changed')
            elif start['operation'] == 'execute':
                if (not result.get('duplicate') and result.get('status') in {'filled', 'rejected'}
                        and result.get('reason') != 'expired_signal'):
                    expected_filters = {**state['filters'], inputs['filters']['pair']: inputs['filters']}
                if result.get('status') == 'filled' and not result.get('duplicate'):
                    fill = result['fill']
                    if (lifecycle and fill['side'] == 'Buy'
                            and stamp(start['at']) >= stamp(protocol['lifecycle_plan']['entry_cutoff'])):
                        raise ValueError('original Buy fill violates lifecycle entry cutoff')
                    if (fill['intent_id'] != inputs['intent_id'] or fill['quote'] != inputs['quote']
                            or fill['filters'] != inputs['filters'] or stamp(fill['filled_at']) != stamp(start['at'])):
                        raise ValueError('fill differs from captured input/clock')
                    if any(old['intent_id'] == fill['intent_id'] for old in fills):
                        raise ValueError('duplicate captured fill')
                    fills.append(fill)
                    raw_fills += int(_sources(fill['quote'], fill['filters']))
                    expected_cash, expected_lots = _inventory_after(state, fill)
                    expected_fills += 1
                    row = wallet_db.execute('SELECT payload FROM fills WHERE intent_id=?', (fill['intent_id'],)).fetchone()
                    if not row or parse(row[0]) != fill:
                        raise ValueError('original wallet fill missing or changed')
            else:
                raise ValueError('unknown capture operation')
            if (after['state']['cash'] != expected_cash or after['lots'] != expected_lots
                    or after['marks'] != expected_marks or after['fills'] != expected_fills
                    or after['filters'] != expected_filters
                    or after['state']['policy'] != state['state']['policy']):
                raise ValueError('captured inventory/cash/count replay differs')
            state, prepared = after, None
        if not sequence or prepared is not None:
            raise ValueError('unfinished capture operation requires review')
        if _wallet_state(root/'wallet.sqlite') != state:
            raise ValueError('uncaptured final wallet mutation')
        segments = [parse(row[0]) for row in wallet_db.execute('SELECT payload FROM closed_segments ORDER BY id')]
        verify_paper_fill_arithmetic(fills, segments, protocol['config'])
    finally:
        db.close()
        wallet_db.close()
    if sources != {name: fingerprint(root/name) for name in sources}:
        raise ValueError('capture source drift during replay')
    lifecycle_result = dict(status='not_preregistered', lifecycle_evidence_pass=False)
    if lifecycle:
        covered = coverage.finish()
        remaining = {lot['pair'] for lot in state['lots'] if number(lot['qty']) > 0}
        dust = set(last_mark['nontradable_small_basis_pairs']) if last_mark and last_quality['raw_sources_verified'] else set()
        closed = not remaining or (remaining <= dust and covered['covers_end'])
        terminated = terminal is not None and terminal['reason'] == 'completed'
        lifecycle_result = dict(status='evaluated', coverage=covered,
            terminal_reason=terminal['reason'] if terminal else 'missing',
            terminal_inventory_closed=closed, operation_wall_budget_pass=wall_budget_pass,
            lifecycle_evidence_pass=covered['coverage_pass'] and terminated and closed and wall_budget_pass,
            host_or_full_worker_tick_qualified=False)
    return {**output, 'status': 'capture_replayed', 'performance_hidden': False,
            'events_checked': sequence, 'head_sha256': previous, 'marks_checked': marks,
            'fills_checked': len(fills), 'known_valuation_marks': known, 'raw_source_marks': raw,
            'raw_source_fills': raw_fills,
            'fill_source_evidence_pass': bool(fills) and raw_fills == len(fills),
            'mark_source_evidence_pass': bool(marks) and marks == raw == known,
            'lifecycle': lifecycle_result,
            'input_files': sources,
            'scope': 'recorded_conditional_paper_valuation_not_actual_fills_or_strategy_admission'}
