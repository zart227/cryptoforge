"""Bounded independent cash/FIFO/valuation replay of sealed v4 paper sources.

The scratch index is disposable and preregistered; sources are read-only.
Computational replay does not qualify strategy decisions, fees or live trading.
"""
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D, ROUND_DOWN
import json
from pathlib import Path
import sqlite3
import tempfile
from time import monotonic_ns

from cryptoforge.evidence_segments import SegmentedEventLog, canonical, digest, parse, require_sha
from cryptoforge.native_paper_archive import NativePaperArchive, SOURCES, _key
from cryptoforge.paper_capture_v3 import _lease, _metadata, _write_new, stamp
from cryptoforge.paper_capture_v4 import (
    GROUPS, _adjust, _initial, _inventory, _load, _valid_row,
    audit_archived_capture, runtime_hashes as capture_runtime,
)
from cryptoforge.paper_lifecycle import mark_valid_until, measure_resources, seconds
from cryptoforge.paper_valuation_capture import _sources, replay_liquidation
from cryptoforge.paper_wallet import PaperConfig

SCHEMA = 'paper-streaming-replay-v1'
IMMUTABLE = {'wallet.marks', 'wallet.fills', 'wallet.closed_segments'}


@dataclass(frozen=True)
class ReplayPolicy:
    maximum_scratch_bytes: int
    maximum_state_rows: int
    maximum_active_rows: int
    maximum_active_bytes: int
    maximum_wall_seconds: int
    minimum_available_memory_bytes: int
    minimum_free_disk_bytes: int

    def __post_init__(self):
        if (any(type(v) is not int or v < 1 for v in asdict(self).values())
                or not 131072 <= self.maximum_scratch_bytes <= 1024**3 or self.maximum_scratch_bytes % 4096
                or not 3 <= self.maximum_state_rows <= 2**63-1 or not 16 <= self.maximum_active_rows <= 16384
                or not 65536 <= self.maximum_active_bytes <= 16*1024*1024
                or self.maximum_wall_seconds > 86400 or self.minimum_free_disk_bytes < self.maximum_scratch_bytes):
            raise ValueError('explicit bounded replay scratch/state/resource budgets required')


def runtime_hashes():
    runner = Path(__file__).resolve().parents[2]/'scripts/audit_paper_streaming.py'
    return {**capture_runtime(), 'streaming_replay': digest(Path(__file__).read_bytes()),
            'streaming_replay_runner': digest(runner.read_bytes())}


def _separate(path, root):
    if path.resolve() != path or path == root or root in path.parents or path in root.parents:
        raise ValueError('new replay/scratch/output namespace must be outside sources')


def _resources(policy, root):
    value = measure_resources(root)
    if (type(value['available_memory_bytes']) is not int or type(value['free_disk_bytes']) is not int
            or value['available_memory_bytes'] < policy.minimum_available_memory_bytes
            or value['free_disk_bytes'] < policy.minimum_free_disk_bytes):
        raise ValueError('frozen replay memory/disk resource floor failed')
    return value


def register_replay(root, *, capture_root, expected_registration_sha256, policy, clock=None):
    """Freeze a separate replay contract BEFORE the original capture starts."""
    capture_root, registration, protocol, lifecycle = _load(capture_root, expected_registration_sha256)
    if type(policy) is not ReplayPolicy:
        raise ValueError('typed replay policy required')
    root = Path(root).absolute();_separate(root, capture_root)
    now = stamp((clock or (lambda:datetime.now(UTC)))())
    if not stamp(registration['registered_at']) <= now < stamp(protocol['start']):
        raise ValueError('replay must be preregistered before original capture start')
    if policy.maximum_active_bytes < 4*protocol['storage_policy']['maximum_record_bytes']:
        raise ValueError('replay active budget must cover original bounded frames')
    measured = _resources(policy, root)
    if (measured['free_disk_bytes'] < lifecycle.minimum_free_disk_bytes+policy.maximum_scratch_bytes
            or measured['available_memory_bytes'] < lifecycle.minimum_available_memory_bytes):
        raise ValueError('combined capture/replay resource reservation insufficient')
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    value = dict(schema_version=SCHEMA, root=str(root), capture_root=str(capture_root),
        capture_registration_sha256=expected_registration_sha256, capture_protocol_sha256=registration['protocol_sha256'],
        candidate_sha256=protocol['candidate_sha256'], role=protocol['role'], start=protocol['start'], end=protocol['end'],
        registered_at=now.isoformat(), policy=asdict(policy), runtime=runtime_hashes(),
        registration_resources=measured, research_only=True, live_eligible=False)
    pin = _write_new(root/'registration.json', value)
    return dict(replay_registration_sha256=pin, root=str(root), live_admission_granted=False)


def _registration(root, pin, capture_root, registration, protocol):
    if root is None:raise ValueError('original prospective replay registration required')
    root = Path(root).absolute();_separate(root, capture_root)
    value = _metadata(root/'registration.json', pin)
    if (set(p.name for p in root.iterdir()) != {'registration.json'} or value.get('schema_version') != SCHEMA
            or value.get('root') != str(root) or value.get('capture_root') != str(capture_root)
            or value.get('capture_registration_sha256') != digest(canonical(registration))
            or value.get('capture_protocol_sha256') != registration['protocol_sha256']
            or any(value.get(k) != protocol[k] for k in ('candidate_sha256','role','start','end'))
            or not stamp(registration['registered_at']) <= stamp(value['registered_at']) < stamp(protocol['start'])
            or value.get('runtime') != runtime_hashes() or value.get('research_only') is not True
            or value.get('live_eligible') is not False):
        raise ValueError('original prospective replay identity/runtime required')
    policy = ReplayPolicy(**value['policy'])
    if policy.maximum_active_bytes < 4*protocol['storage_policy']['maximum_record_bytes']:
        raise ValueError('original replay frame capacity insufficient')
    measured = value['registration_resources']
    if (type(measured.get('available_memory_bytes')) is not int or type(measured.get('free_disk_bytes')) is not int
            or measured['available_memory_bytes'] < policy.minimum_available_memory_bytes
            or measured['free_disk_bytes'] < policy.minimum_free_disk_bytes
            or measured['available_memory_bytes'] < protocol['lifecycle']['minimum_available_memory_bytes']
            or measured['free_disk_bytes'] < protocol['lifecycle']['minimum_free_disk_bytes']+policy.maximum_scratch_bytes):
        raise ValueError('original replay resource registration differs')
    return root, value, policy


class StreamingCoverage:
    """Constant-size exact equivalent of the short-study CoverageTimeline."""
    def __init__(self, start, end, policy):
        self.start, self.end, self.policy = stamp(start), stamp(end), policy
        self.cursor, self.until = self.start, self.start
        self.known, self.maximum_unknown, self.maximum_mark_gap = D(0), D(0), D(0)
        self.first_known, self.last_known, self.last_mark = None, None, self.start

    def _advance(self, at):
        at = min(stamp(at), self.end)
        if at < self.cursor:
            raise ValueError('streaming coverage must remain causal')
        finish = min(at, self.until)
        if finish > self.cursor:
            self.maximum_unknown = max(self.maximum_unknown, seconds(self.cursor-(self.last_known or self.start)))
            if self.first_known is None:self.first_known = self.cursor
            self.known += seconds(finish-self.cursor)
            self.last_known = finish
        self.cursor = at

    def invalidate(self, at):
        self._advance(at);self.until = self.cursor

    def mark(self, at, valid_until, *, sources_known):
        at = stamp(at);self._advance(at)
        self.maximum_mark_gap = max(self.maximum_mark_gap, seconds(at-self.last_mark))
        self.last_mark = at
        self.until = min(stamp(valid_until), self.end) if sources_known else self.cursor

    def finish(self):
        self._advance(self.end)
        total = seconds(self.end-self.start)
        leading = seconds(self.first_known-self.start) if self.first_known is not None else total
        trailing = seconds(self.end-self.last_known) if self.last_known is not None else total
        gap = max(self.maximum_unknown, trailing)
        mark_gap = max(self.maximum_mark_gap, seconds(self.end-self.last_mark))
        fraction = self.known/total
        checks = dict(known_time_fraction=fraction >= D(self.policy.minimum_known_time_fraction),
            mark_cadence=mark_gap <= self.policy.maximum_mark_gap_seconds,
            unknown_gap=gap <= self.policy.maximum_mark_gap_seconds,
            leading_endpoint=leading <= self.policy.maximum_endpoint_gap_seconds,
            trailing_endpoint=trailing <= self.policy.maximum_endpoint_gap_seconds)
        return dict(window_seconds=str(total), known_seconds=str(self.known), known_fraction=str(fraction),
            maximum_mark_gap_seconds=str(mark_gap), maximum_unknown_gap_seconds=str(gap),
            leading_unknown_seconds=str(leading), trailing_unknown_seconds=str(trailing), checks=checks,
            coverage_pass=all(checks.values()), covers_end=self.last_known == self.end)


class _Scratch:
    """Fresh disposable index. Immutable history retains keys/hashes, not payloads."""
    def __init__(self, path, policy):
        self.path, self.policy, self.count = path, policy, 0
        self.db = sqlite3.connect(path)
        try:
            self.db.execute('PRAGMA trusted_schema=OFF')
            self.db.execute('PRAGMA cache_size=-256')
            self.db.execute('PRAGMA journal_mode=MEMORY')
            self.db.execute('PRAGMA synchronous=OFF')
            pages = policy.maximum_scratch_bytes//self.db.execute('PRAGMA page_size').fetchone()[0]
            if self.db.execute(f'PRAGMA max_page_count={pages}').fetchone()[0] != pages:
                raise ValueError('hard replay scratch page budget unavailable')
            self.db.execute('CREATE TABLE rows (source TEXT,key TEXT,raw TEXT,sha TEXT NOT NULL,PRIMARY KEY(source,key)) WITHOUT ROWID')
            self.path.chmod(0o600)
        except Exception:
            self.db.close();raise

    def _key(self, source, key):
        return _key(source, key) if source in SOURCES else str(key)

    def get(self, source, key):
        row = self.db.execute('SELECT raw,sha FROM rows WHERE source=? AND key=?', (source,self._key(source,key))).fetchone()
        if row is None:return None
        if row[0] is None:raise ValueError('immutable replay row identity cannot be created twice')
        raw = parse(row[0])
        if digest(canonical(raw)) != row[1]:raise ValueError('scratch native row hash differs')
        return raw

    def put(self, source, row):
        raw = canonical(row)
        key = self._key(source, row[0])
        exists = self.db.execute('SELECT 1 FROM rows WHERE source=? AND key=?', (source,key)).fetchone()
        if not exists:
            if self.count >= self.policy.maximum_state_rows:raise ValueError('replay scratch row budget exhausted')
            self.count += 1
        self.db.execute('INSERT INTO rows VALUES (?,?,?,?) ON CONFLICT(source,key) DO UPDATE SET raw=excluded.raw,sha=excluded.sha',
            (source,key,None if source in IMMUTABLE else raw.decode(),digest(raw)))


def _number(value, *, zero=False):
    result = D(str(value))
    if not result.is_finite() or result < 0 or (result == 0 and not zero):
        raise ValueError('finite positive replay quantity/price required')
    return result


def _json(value):return json.dumps(value, sort_keys=True, default=str)


class _Replay:
    def __init__(self, protocol, native_manifest_pin, scratch, policy, lifecycle):
        self.protocol, self.scratch, self.policy, self.lifecycle = protocol, scratch, policy, lifecycle
        self.config = PaperConfig(**protocol['config'])
        self.cash = str(self.config.capital)
        self.lots, self.filters, self.anchors = {}, {}, {}
        self.latest, self.latest_known = None, None
        self.latest_source_qualified, self.pending_count = False, 0
        self.summary = _initial(protocol, native_manifest_pin)['sources']
        self.changes = {}
        self.marks = self.fills = self.segments = self.raw_fills = self.raw_marks = self.buy_count = self.sell_count = 0
        self.material_zero_marks = 0
        self.realized, self.fees, self.peak_active_bytes, self.peak_active_rows = D(0), D(0), 0, 0
        for name,row in [('wallet.state',['cash',self.cash]),
                ('wallet.state',['policy',_json(dict(candidate_sha=protocol['candidate_sha256'],config=asdict(self.config)))]),
                ('worker.state',['identity',_json(dict(candidate=protocol['candidate_sha256'],policy=protocol['worker_policy']))])]:
            scratch.put(name,row)
        scratch.db.commit()
        self.coverage = StreamingCoverage(protocol['start'],protocol['end'],lifecycle)

    def _put(self, name, row):
        row = _valid_row(name,row)
        old = self.scratch.get(name,row[0])
        if old == row:return
        identity = name,row[0]
        if identity in self.changes:raise ValueError('one native source row changed twice in an operation')
        self.changes[identity] = dict(source=name,key=row[0],before=old,after=row)
        if name == 'wallet.intents':
            self.pending_count += int(row[5] == 'pending')-int(old is not None and old[5] == 'pending')
        if old is not None:_adjust(self.summary,name,old,-1)
        _adjust(self.summary,name,row,1)
        self.scratch.put(name,row)

    def _guard(self):
        if not D(self.cash).is_finite() or D(self.cash) < 0:
            raise ValueError('independent replay cash conservation violated')
        active = dict(lots=self.lots,filters=self.filters,anchors=self.anchors,latest=self.latest)
        size = len(canonical(active))
        rows = len(self.lots)+len(self.filters)+len(self.anchors)
        self.peak_active_bytes,self.peak_active_rows = max(size,self.peak_active_bytes),max(rows,self.peak_active_rows)
        if size > self.policy.maximum_active_bytes or rows > self.policy.maximum_active_rows:
            raise ValueError('frozen replay active state budget exhausted')

    def _wallet(self):
        return dict(state=dict(cash=self.cash,**self.anchors),lots=[dict(zip(
            ('id','pair','opened_at','qty','cost','entry_fee_quote'),r)) for r in sorted(self.lots.values(),key=lambda r:(r[2],r[0]))])

    def _filter(self, pair, rule):
        if rule['pair'] != pair:raise ValueError('replay instrument cache pair differs')
        old = self.filters.get(pair)
        raw = _json(rule)
        if old is not None and (stamp(rule['observed_at']) < stamp(old['observed_at'])
                or (stamp(rule['observed_at']) == stamp(old['observed_at']) and raw != _json(old))):
            raise ValueError('replay instrument source rewound or rewritten')
        self._put('wallet.filters',[pair,raw]);self.filters[pair] = rule

    def _anchor(self, now, equity):
        key = 'day_anchor:'+now.date().isoformat()
        old = self.scratch.get('wallet.day_anchors',key)
        if old:return D(old[1])
        previous = D(self.anchors[max(self.anchors)]) if self.anchors else equity
        if self.latest_known is not None:previous = self.latest_known
        anchor = max(equity,previous)
        self._put('wallet.day_anchors',[key,str(anchor)]);self.anchors[key] = str(anchor)
        self.anchors = {k:self.anchors[k] for k in sorted(self.anchors)[-2:]}
        return anchor

    def _daily_block(self, now):
        if self.latest is None:
            if self.lots:return True
            self._anchor(now,D(self.cash));return False
        if (self.latest['equity'] is None or not timedelta(0) <= now-stamp(self.latest['observed_at'])
                <= timedelta(seconds=self.config.quote_max_age_seconds)):
            return True
        equity = D(self.latest['equity'])
        return self._anchor(now,equity)-equity >= self.config.max_daily_loss

    def _market(self, pair, quote, rule, now):
        if (quote.get('market'),rule.get('market'),quote.get('venue'),rule.get('venue'),rule.get('status')) != (
                'spot','spot','bybit_global','bybit_global','Trading'):
            raise ValueError('original Trading global Spot inputs required')
        if quote['pair'] != pair or rule['pair'] != pair:raise ValueError('replay market pair differs')
        for item,age in ((quote,self.config.quote_max_age_seconds),(rule,self.config.filter_max_age_seconds)):
            if not timedelta(0) <= now-stamp(item['observed_at']) <= timedelta(seconds=age):
                raise ValueError('stale or future replay market source')
        if _number(quote['bid']) > _number(quote['ask']):raise ValueError('crossed replay book')
        _number(quote['bid_qty']);_number(quote['ask_qty'])
        return tuple(_number(rule[k]) for k in ('quantity_step','minimum_notional','maximum_market_quantity'))

    def _reject(self, intent, now, reason):
        self._put('wallet.intents',intent[:4]+[now.isoformat(),'rejected',reason])
        return dict(status='rejected',reason=reason)

    def execute(self, inputs, now):
        c,identity,quote,rule = self.config,inputs['intent_id'],inputs['quote'],inputs['filters']
        intent = self.scratch.get('wallet.intents',identity)
        if not intent:raise ValueError('original replay intent missing')
        pair,side = intent[1:3]
        if intent[5] != 'pending':return dict(status=intent[5],duplicate=True)
        if (now-stamp(intent[3])).total_seconds() > c.signal_expiry_seconds:
            return self._reject(intent,now,'expired_signal')
        if stamp(quote['observed_at']) < max(stamp(intent[3]),stamp(intent[4]))+timedelta(seconds=c.delay_seconds):
            return dict(status='pending',reason='awaiting_later_quote')
        step,minimum,maximum = self._market(pair,quote,rule,now)
        bid,ask = _number(quote['bid']),_number(quote['ask'])
        depth = _number(quote['ask_qty'] if side == 'Buy' else quote['bid_qty'])
        # Dict insertion order comes from original completed Buy events. Equal
        # wall clocks do not authorize lexicographic intent IDs to reorder FIFO.
        owned = [r for r in self.lots.values() if r[1] == pair]
        self._filter(pair,rule)
        if side == 'Buy':
            if self._daily_block(now):return self._reject(intent,now,'daily_equity_guard_or_missing_fresh_mark')
            owned_qty = sum((D(r[3]) for r in owned),D(0))
            owned_cost = sum((D(r[4]) for r in owned),D(0))
            rounded = (owned_qty/step).to_integral_value(rounding=ROUND_DOWN)*step
            if owned and (rounded*bid >= minimum or owned_cost > c.stake*c.max_dust_basis_fraction):
                return self._reject(intent,now,'existing_inventory_requires_review')
            active = {r[1] for r in self.lots.values()}
            if self.latest:active -= set(self.latest['nontradable_small_basis_pairs'])
            if owned and owned_qty and owned_cost <= c.stake*c.max_dust_basis_fraction and rounded*bid < minimum:active.discard(pair)
            if len(active) >= c.max_positions:return self._reject(intent,now,'position_limit')
            if D(self.cash) < c.stake:return self._reject(intent,now,'insufficient_shared_cash')
            price = ask*(1+c.slippage)
            order = (c.stake/price/step).to_integral_value(rounding=ROUND_DOWN)*step
            if order <= 0 or order*price < minimum:return self._reject(intent,now,'minimum_notional')
            quantity,cost = order*(1-c.entry_fee),order*price
            if order > maximum or order > depth*c.max_depth_fraction:
                return self._reject(intent,now,'size_or_displayed_liquidity_limit')
            rounded_exit = (quantity/step).to_integral_value(rounding=ROUND_DOWN)*step
            if (step*price > c.stake*c.max_dust_basis_fraction
                    or rounded_exit*bid*(1-c.entry_stop_reserve_fraction)*(1-c.slippage) < minimum):
                return self._reject(intent,now,'exit_minimum_or_residual_precision_risk')
            if cost > c.stake or cost > D(self.cash):
                raise ValueError('independent replay purchase exceeds frozen stake or cash conservation')
            _number(quantity)
            fee,fee_amount,proceeds = cost*c.entry_fee,order*c.entry_fee,None
            row = [identity,pair,now.isoformat(),str(quantity),str(cost),str(fee)]
            self._put('wallet.lots',row);self.lots[identity] = row
            cash = D(self.cash)-cost;self.buy_count += 1
        else:
            if side != 'Sell':raise ValueError('Spot replay Buy/Sell side required')
            order = quantity = (sum((D(r[3]) for r in owned),D(0))/step).to_integral_value(rounding=ROUND_DOWN)*step
            price = bid*(1-c.slippage)
            if quantity <= 0 or quantity*price < minimum:return self._reject(intent,now,'unsellable_inventory_preserved')
            if quantity > maximum or quantity > depth*c.max_depth_fraction:
                return self._reject(intent,now,'size_or_displayed_liquidity_limit')
            notional = quantity*price
            proceeds,fee,fee_amount,cost = notional*(1-c.exit_fee),notional*c.exit_fee,notional*c.exit_fee,None
            left = quantity
            for row in owned:
                if not left:break
                qty,basis,entry_fee = (D(row[i]) for i in (3,4,5))
                sold = min(left,qty);fraction = sold/qty
                allocated,entry_allocated = basis*fraction,entry_fee*fraction
                segment_notional = sold*price
                net,fees = segment_notional*(1-c.exit_fee)-allocated,entry_allocated+segment_notional*c.exit_fee
                segment = dict(mode='paper',candidate_sha256=self.protocol['candidate_sha256'],entry_intent=row[0],
                    exit_intent=identity,pair=pair,opened_at=row[2],closed_at=now.isoformat(),quantity=str(sold),
                    cost=str(allocated),net_pnl=str(net),fees=str(fees))
                self.segments += 1;self.realized += net
                self._put('wallet.closed_segments',[self.segments,_json(segment)])
                remainder = row[:3]+[str(qty-sold),str(basis-allocated),str(entry_fee-entry_allocated)]
                self._put('wallet.lots',remainder)
                if qty-sold > 0:self.lots[row[0]] = remainder
                else:self.lots.pop(row[0])
                left -= sold
            if left:raise ValueError('replay FIFO sells unowned quantity')
            cash = D(self.cash)+proceeds;self.sell_count += 1
        fill = dict(mode='paper',candidate_sha256=self.protocol['candidate_sha256'],intent_id=identity,pair=pair,side=side,
            signal_time=stamp(intent[3]).isoformat(),quote_observed_at=stamp(quote['observed_at']).isoformat(),filled_at=now.isoformat(),
            quantity=str(quantity),price=str(price),cost=str(cost) if cost is not None else None,
            proceeds=str(proceeds) if proceeds is not None else None,fee_quote_equivalent=str(fee),
            fee_currency='base' if side == 'Buy' else 'quote',fee_amount=str(fee_amount),order_quantity=str(order),
            fill_assumption='top_quote_adverse_slippage_not_guaranteed_market_fill',cost_assumption_id=c.cost_assumption_id,
            quote=quote,filters=rule)
        self._put('wallet.fills',[identity,_json(fill)])
        self.cash = str(cash);self._put('wallet.state',['cash',self.cash])
        self._put('wallet.intents',intent[:4]+[now.isoformat(),'filled',intent[6]])
        self.fills += 1;self.raw_fills += int(_sources(quote,rule));self.fees += fee
        return dict(status='filled',fill=fill)

    def operation(self, prepared, complete):
        self.changes = {}
        name,inputs,now = prepared['operation'],prepared['inputs'],stamp(prepared['at'])
        before = self._wallet()
        if name == 'mark':
            for pair,rule in inputs['filters'].items():self._filter(pair,rule)
            result,quality = replay_liquidation(before,inputs['quotes'],self.filters,self.config,now)
            if result['equity'] is not None:self._anchor(now,D(result['equity']))
            self.marks += 1
            self._put('wallet.marks',[self.marks,now.isoformat(),_json(result)])
            self.latest = result
            if result['equity'] is not None:self.latest_known = D(result['equity'])
            self.raw_marks += int(quality['raw_sources_verified'])
            deadline = mark_valid_until(self.lifecycle,now,before,inputs['quotes'],self.filters,self.config)
            material_zero = False
            if quality['raw_sources_verified']:
                pairs = {row[1] for row in self.lots.values()}
                for pair in pairs-set(result['nontradable_small_basis_pairs']):
                    qty = sum((D(r[3]) for r in self.lots.values() if r[1] == pair),D(0))
                    step = D(self.filters[pair]['quantity_step'])
                    rounded = (qty/step).to_integral_value(rounding=ROUND_DOWN)*step
                    if rounded == 0 or rounded*D(inputs['quotes'][pair]['bid'])*(1-self.config.slippage) < D(self.filters[pair]['minimum_notional']):
                        material_zero = True
            self.material_zero_marks += int(material_zero)
            self.latest_source_qualified = quality['raw_sources_verified'] and quality['conditional_valuation_known'] and not material_zero
            self.coverage.mark(complete['at'],deadline,sources_known=self.latest_source_qualified)
        elif name == 'execute':result = self.execute(inputs,now)
        elif name == 'enqueue':
            old = self.scratch.get('wallet.intents',inputs['intent_id'])
            if (inputs['side'] not in {'Buy','Sell'} or not inputs['pair'].endswith('/USDT')
                    or not 0 <= (now-stamp(inputs['created_at'])).total_seconds() <= 5):
                raise ValueError('original replay enqueue clock/identity differs')
            if old:
                if old[1:4] != [inputs['pair'],inputs['side'],inputs['created_at']]:
                    raise ValueError('original replay intent cannot be overwritten')
                result = False
            else:
                self._put('wallet.intents',[inputs['intent_id'],inputs['pair'],inputs['side'],inputs['created_at'],now.isoformat(),'pending',None])
                result = True
        elif name == 'cancel_pending':
            old = self.scratch.get('wallet.intents',inputs['intent_id'])
            if old and old[5] == 'pending':self._put('wallet.intents',old[:4]+[now.isoformat(),'rejected',inputs['reason']])
            result = None
        elif name == 'compact':result = dict(status='native_projection_compacted',live_admission_granted=False)
        else:raise ValueError('unknown independent replay operation')
        ordered = sorted(self.changes.values(),key=lambda c:(GROUPS.index(c['source']),c['key']))
        if (complete['result'] != result or complete['changes'] != ordered or complete['after']['sources'] != self.summary):
            raise ValueError('independent cash/FIFO/fill/valuation source transition mismatch')
        self._guard()
        self.scratch.db.commit()


def audit_streaming_paper(capture_root, *, expected_registration_sha256, expected_seal_sha256=None,
        replay_root=None, expected_replay_registration_sha256=None, scratch_parent=None, clock=None):
    capture_root, registration, protocol, lifecycle = _load(capture_root,expected_registration_sha256)
    output = dict(schema_version=SCHEMA,capture_registration_sha256=expected_registration_sha256,
        paper_evidence_pass=False,economic_profitability_established=False,live_admission_granted=False,
        full_worker_or_host_qualified=False,full_fifo_replay_pass=False,coverage_evidence_pass=False)
    if stamp((clock or (lambda:datetime.now(UTC)))()) < stamp(protocol['end']):
        return {**output,'status':'sealed_until_capture_end','performance_hidden':True}
    replay_root,replay,policy = _registration(replay_root,expected_replay_registration_sha256,
        capture_root,registration,protocol)
    parent = Path(scratch_parent or tempfile.gettempdir()).absolute()
    if parent.resolve() != parent or not parent.is_dir() or any(parent == p or p in parent.parents for p in (capture_root,replay_root)):
        raise ValueError('scratch parent must be outside original sources')
    _resources(policy,parent)
    started = monotonic_ns()
    def budget():
        if monotonic_ns()-started > policy.maximum_wall_seconds*1000000000:
            raise ValueError('frozen streaming replay wall budget exhausted')
    trace = audit_archived_capture(capture_root,expected_registration_sha256=expected_registration_sha256,
        expected_seal_sha256=expected_seal_sha256,clock=clock)
    budget()
    with _lease(capture_root,writer=False):
        _inventory(capture_root)
        seal = _metadata(capture_root/'sealed.json',expected_seal_sha256)
        log = SegmentedEventLog._load(capture_root/'storage',registration['storage_manifest_sha256'])
        source = NativePaperArchive.reader(capture_root/'native',expected_manifest_sha256=registration['native_manifest_sha256'],
            expected_seal_sha256=seal['native_seal_sha256'])
        with tempfile.TemporaryDirectory(prefix='cryptoforge-paper-replay-',dir=parent) as temporary:
            temporary = Path(temporary);_separate(temporary,capture_root);_separate(temporary,replay_root)
            scratch = _Scratch(temporary/'state.sqlite',policy)
            try:
                replayed = _Replay(protocol,registration['native_manifest_sha256'],scratch,policy,lifecycle)
                pending,terminal,count = None,None,0
                for record in log.iter_events(expected_head_sha256=seal['head_sha256'],expected_catalog_sha256=seal['catalog_sha256']):
                    count += 1;budget()
                    if count % 128 == 0:_resources(policy,temporary)
                    event,kind = record['payload'],record['kind']
                    if kind == 'genesis':
                        if event['after']['sources'] != replayed.summary:raise ValueError('independent initial cash state differs')
                    elif kind == 'prepared':
                        if event['before']['sources'] != replayed.summary:raise ValueError('independent pre-operation state differs')
                        replayed.coverage.invalidate(event['at']);pending = event
                    elif kind == 'complete':
                        if pending is None:raise ValueError('independent completion missing preparation')
                        replayed.operation(pending,event);pending = None
                    elif kind == 'terminated':
                        replayed.coverage.invalidate(event['at']);terminal = event
                if (pending is not None or terminal is None or count != seal['sequence']
                        or replayed.summary != seal['native_after']['sources']):
                    raise ValueError('independent final source state differs')
                coverage = replayed.coverage.finish()
                final_known = replayed.latest is not None and replayed.latest['equity'] is not None
                dust = set(replayed.latest['nontradable_small_basis_pairs']) if final_known else set()
                material = {row[1] for row in replayed.lots.values()}-dust
                lifecycle_checks = dict(completed=terminal['reason'] == 'completed',coverage=coverage['coverage_pass'],
                    covers_end=coverage['covers_end'],final_valuation_known=final_known,closeout_no_material_inventory=not material,
                    final_valuation_source_verified=replayed.latest_source_qualified,no_pending_intents=replayed.pending_count == 0,
                    raw_fill_sources=replayed.raw_fills == replayed.fills,operation_wall_budget=trace['operation_wall_budget_pass'])
                _resources(policy,temporary);budget()
                result = {**output,'status':'streaming_cash_fifo_valuation_replayed','performance_hidden':False,
                    'replay_registration_sha256':expected_replay_registration_sha256,'source_checkpoint_trace_pass':True,
                    'full_fifo_replay_pass':True,'coverage_evidence_pass':all(lifecycle_checks.values()),
                    'lifecycle_checks':lifecycle_checks,'coverage':coverage,'events_checked':count,'marks_checked':replayed.marks,
                    'fills_checked':replayed.fills,'segments_checked':replayed.segments,'buys':replayed.buy_count,'sells':replayed.sell_count,
                    'raw_source_marks':replayed.raw_marks,'raw_source_fills':replayed.raw_fills,'final_cash':replayed.cash,
                    'material_zero_marks':replayed.material_zero_marks,
                    'pending_intents':replayed.pending_count,
                    'final_equity':replayed.latest['equity'] if final_known else None,'allocated_realized_pnl':str(replayed.realized),
                    'fill_fee_quote_equivalent':str(replayed.fees),'material_inventory_pairs':sorted(material),
                    'scratch_rows':scratch.count,'scratch_bytes':scratch.path.stat().st_size,
                    'peak_active_bytes':replayed.peak_active_bytes,'peak_active_rows':replayed.peak_active_rows,
                    'scope':'independent_paper_wallet_math_and_source_time_coverage_not_worker_strategy_account_fee_or_live_admission'}
            finally:scratch.db.close()
        source._check_seal()
        _load(capture_root,expected_registration_sha256)
        if _metadata(capture_root/'sealed.json',expected_seal_sha256) != seal:raise ValueError('source seal changed during replay')
        if _registration(replay_root,expected_replay_registration_sha256,capture_root,registration,protocol)[1] != replay:
            raise ValueError('replay registration changed during audit')
        budget()
    return result
