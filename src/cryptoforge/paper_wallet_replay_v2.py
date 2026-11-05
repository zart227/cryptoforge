"""Independent bounded financial replay of the fourteen-group v2 source domain.

Only metadata/commitment helpers are shared with capture. Orders, lot allocation,
valuation and causal clocks are recomputed without native producer execution.
"""
from dataclasses import asdict,dataclass
from datetime import timedelta
from decimal import Decimal as D
from fractions import Fraction
import json
from pathlib import Path
import sqlite3

from cryptoforge.evidence_segments import canonical,digest,parse
from cryptoforge.native_paper_archive_v2 import SOURCES,_key
from cryptoforge.paper_capture_state_v2 import GROUPS,_adjust,_empty,_valid_row
from cryptoforge.paper_capture_v3 import stamp
from cryptoforge.paper_lifecycle import mark_valid_until,measure_resources,seconds
from cryptoforge.paper_valuation_capture import _sources
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_replay_math_v2 import (
    number as _number,decimal,total,product,difference,floor_quantity,acquisition,sale,allocate,
)

IMMUTABLE={'wallet.marks','wallet.fills','wallet.closed_segments','wallet.fill_order','worker.worker_events'}


def _identities(protocol):
    kernel=protocol['kernel_contract']
    wallet=json.dumps(dict(producer_version=kernel['producer_version'],runtime=kernel['runtime'],
        wallet_path=str(Path(protocol['root'])/'native'/'wallet.sqlite'),candidate_sha=protocol['candidate_sha256'],
        config=asdict(PaperConfig(**protocol['config']))),sort_keys=True,default=str)
    worker=json.dumps(dict(producer_version=kernel['producer_version'],runtime=kernel['runtime'],
        worker_path=str(Path(protocol['root'])/'native'/'worker.sqlite'),wallet_identity_sha256=digest(wallet.encode()),
        candidate=protocol['candidate_sha256'],policy=protocol['worker_policy']),sort_keys=True,default=str)
    return wallet,worker


@dataclass(frozen=True)
class ReplayPolicyV2:
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


def _json(value):return json.dumps(value, sort_keys=True, default=str)


class _Replay:
    def __init__(self, protocol, native_manifest_pin, scratch, policy, lifecycle):
        self.protocol, self.scratch, self.policy, self.lifecycle = protocol, scratch, policy, lifecycle
        self.config = PaperConfig(**protocol['config'])
        self.cash = str(self.config.capital)
        self.lots, self.filters, self.anchors = {}, {}, {}
        self.lot_order = {}
        self.latest, self.latest_known = None, None
        self.window_latest,self.window_source_qualified = None,False
        self.latest_source_qualified, self.pending_count = False, 0
        self.summary = _empty()
        self.changes = {}
        self.marks = self.fills = self.segments = self.raw_fills = self.raw_marks = self.buy_count = self.sell_count = 0
        self.material_zero_marks = 0
        self.realized, self.fees, self.peak_active_bytes, self.peak_active_rows = D(0), D(0), 0, 0
        wallet_identity,worker_identity=_identities(protocol)
        for name,row in [('wallet.state',['cash',self.cash]),('wallet.state',['policy',wallet_identity]),
                ('worker.state',['identity',worker_identity])]:
            scratch.put(name,row);_adjust(self.summary,name,row,1)
        self._leaf_clocks=[];self._leaf_index=0
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
        if (Fraction(D(self.cash))+sum((Fraction(D(row[4])) for row in self.lots.values()),Fraction(0))
                != Fraction(self.config.capital)+Fraction(self.realized)):
            raise ValueError('independent exact cash/basis/realized conservation violated')
        if not D(self.cash).is_finite() or D(self.cash) < 0:
            raise ValueError('independent replay cash conservation violated')
        active = dict(lots=self.lots,filters=self.filters,anchors=self.anchors,latest=self.latest,
            window_latest=self.window_latest,lot_order=self.lot_order,leaf_clocks=self._leaf_clocks)
        size = len(canonical(active))
        rows = len(self.lots)+len(self.filters)+len(self.anchors)
        self.peak_active_bytes,self.peak_active_rows = max(size,self.peak_active_bytes),max(rows,self.peak_active_rows)
        if size > self.policy.maximum_active_bytes or rows > self.policy.maximum_active_rows:
            raise ValueError('frozen replay active state budget exhausted')

    def _wallet(self):
        return dict(state=dict(cash=self.cash,**self.anchors),lots=[dict(zip(
            ('id','pair','opened_at','qty','cost','entry_fee_quote'),r)) for r in sorted(self.lots.values(),key=lambda r:self.lot_order[r[0]])])

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
        return difference(self._anchor(now,equity),equity) >= self.config.max_daily_loss

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

    def _begin_clocks(self,complete):
        self._leaf_clocks=complete['native_clocks'];self._leaf_index=0

    def _clock(self):
        if self._leaf_index>=len(self._leaf_clocks):raise ValueError('independent native clock missing')
        at=stamp(self._leaf_clocks[self._leaf_index]);self._leaf_index+=1
        return at

    def _finish_clocks(self):
        if self._leaf_index!=len(self._leaf_clocks):raise ValueError('independent native clock surplus')

    def _reject(self,intent,now,reason,*,second=True):
        observed=self._clock() if second else now
        self._put('wallet.intents',intent[:4]+[observed.isoformat(),'rejected',reason])
        return dict(status='rejected',reason=reason)

    def execute(self, inputs, now):
        c,identity,quote,rule = self.config,inputs['intent_id'],inputs['quote'],inputs['filters']
        intent = self.scratch.get('wallet.intents',identity)
        if not intent:raise ValueError('original replay intent missing')
        pair,side = intent[1:3]
        if intent[5] != 'pending':return dict(status=intent[5],duplicate=True)
        if side=='Buy' and now>=stamp(self.protocol['plan']['entry_cutoff']):
            return self._reject(intent,now,'paper_entry_window_finished')
        if (now-stamp(intent[3])).total_seconds() > c.signal_expiry_seconds:
            return self._reject(intent,now,'expired_signal',second=False)
        if stamp(quote['observed_at']) < max(stamp(intent[3]),stamp(intent[4]))+timedelta(seconds=c.delay_seconds):
            return dict(status='pending',reason='awaiting_later_quote')
        step,minimum,maximum = self._market(pair,quote,rule,now)
        bid,ask = _number(quote['bid']),_number(quote['ask'])
        depth = _number(quote['ask_qty'] if side == 'Buy' else quote['bid_qty'])
        # Dict insertion order comes from original completed Buy events. Equal
        # wall clocks do not authorize lexicographic intent IDs to reorder FIFO.
        owned = [r for r in sorted(self.lots.values(),key=lambda row:self.lot_order[row[0]]) if r[1] == pair]
        self._filter(pair,rule)
        if side == 'Buy':
            if self._daily_block(now):return self._reject(intent,now,'daily_equity_guard_or_missing_fresh_mark')
            owned_qty = total(D(r[3]) for r in owned)
            owned_cost = total(D(r[4]) for r in owned)
            rounded = floor_quantity(owned_qty,step)
            if owned and (rounded*bid >= minimum or owned_cost > c.stake*c.max_dust_basis_fraction):
                return self._reject(intent,now,'existing_inventory_requires_review')
            active = {r[1] for r in self.lots.values()}
            if self.latest:active -= set(self.latest['nontradable_small_basis_pairs'])
            if owned and owned_qty and owned_cost <= c.stake*c.max_dust_basis_fraction and rounded*bid < minimum:active.discard(pair)
            if len(active) >= c.max_positions:return self._reject(intent,now,'position_limit')
            if D(self.cash) < c.stake:return self._reject(intent,now,'insufficient_shared_cash')
            price = product(ask,1+c.slippage)
            purchase=acquisition(c.stake,price,step,c.entry_fee)
            order=purchase['gross']
            if order <= 0 or order*price < minimum:return self._reject(intent,now,'minimum_notional')
            quantity,cost = purchase['quantity'],purchase['cost']
            if order > maximum or order > depth*c.max_depth_fraction:
                return self._reject(intent,now,'size_or_displayed_liquidity_limit')
            rounded_exit = floor_quantity(quantity,step)
            if (step*price > c.stake*c.max_dust_basis_fraction
                    or rounded_exit*bid*(1-c.entry_stop_reserve_fraction)*(1-c.slippage) < minimum):
                return self._reject(intent,now,'exit_minimum_or_residual_precision_risk')
            if cost > c.stake or cost > D(self.cash):
                raise ValueError('independent replay purchase exceeds frozen stake or cash conservation')
            _number(quantity,limit=4096)
            fee,fee_amount,proceeds = purchase['fee'],purchase['amount'],None
            row = [identity,pair,now.isoformat(),str(quantity),str(cost),str(fee)]
            self._put('wallet.lots',row);self.lots[identity] = row
            cash = difference(D(self.cash),cost);self.buy_count += 1
            self.lot_order[identity]=self.fills+1
        else:
            if side != 'Sell':raise ValueError('Spot replay Buy/Sell side required')
            order = quantity = floor_quantity(total(D(r[3]) for r in owned),step)
            price = bid*(1-c.slippage)
            if quantity <= 0 or quantity*price < minimum:return self._reject(intent,now,'unsellable_inventory_preserved')
            if quantity > maximum or quantity > depth*c.max_depth_fraction:
                return self._reject(intent,now,'size_or_displayed_liquidity_limit')
            proceeds,fee = sale(quantity,price,c.exit_fee)
            fee_amount,cost=fee,None
            left = quantity
            for row in owned:
                if not left:break
                qty,basis,entry_fee = (D(row[i]) for i in (3,4,5))
                sold = min(left,qty)
                allocated,entry_allocated = allocate(basis,sold,qty),allocate(entry_fee,sold,qty)
                segment_cash,segment_fee=sale(sold,price,c.exit_fee)
                net,fees = difference(segment_cash,allocated),total((entry_allocated,segment_fee))
                segment = dict(mode='paper',candidate_sha256=self.protocol['candidate_sha256'],entry_intent=row[0],
                    exit_intent=identity,pair=pair,opened_at=row[2],closed_at=now.isoformat(),quantity=str(sold),
                    cost=str(allocated),net_pnl=str(net),fees=str(fees))
                self.segments += 1;self.realized = total((self.realized,net))
                self._put('wallet.closed_segments',[self.segments,_json(segment)])
                remainder = row[:3]+[str(difference(qty,sold)),str(difference(basis,allocated)),str(difference(entry_fee,entry_allocated))]
                self._put('wallet.lots',remainder)
                if difference(qty,sold) > 0:self.lots[row[0]] = remainder
                else:self.lots.pop(row[0]);self.lot_order.pop(row[0])
                left = difference(left,sold)
            if left:raise ValueError('replay FIFO sells unowned quantity')
            cash = total((D(self.cash),proceeds));self.sell_count += 1
        fill = dict(producer_version=self.protocol['kernel_contract']['producer_version'],fill_sequence=self.fills+1,mode='paper',candidate_sha256=self.protocol['candidate_sha256'],intent_id=identity,pair=pair,side=side,
            signal_time=stamp(intent[3]).isoformat(),quote_observed_at=stamp(quote['observed_at']).isoformat(),filled_at=now.isoformat(),
            quantity=str(quantity),price=str(price),cost=str(cost) if cost is not None else None,
            proceeds=str(proceeds) if proceeds is not None else None,fee_quote_equivalent=str(fee),
            fee_currency='base' if side == 'Buy' else 'quote',fee_amount=str(fee_amount),order_quantity=str(order),
            fill_assumption='top_quote_adverse_slippage_not_guaranteed_market_fill',cost_assumption_id=c.cost_assumption_id,
            quote=quote,filters=rule)
        self._put('wallet.fill_order',[self.fills+1,identity])
        self._put('wallet.fill_counter',['fill_order',self.fills+1])
        self._put('wallet.fills',[identity,_json(fill)])
        self.cash = str(cash);self._put('wallet.state',['cash',self.cash])
        self._put('wallet.intents',intent[:4]+[now.isoformat(),'filled',intent[6]])
        self.fills += 1;self.raw_fills += int(_sources(quote,rule));self.fees = total((self.fees,fee))
        return dict(status='filled',fill=fill)

    def valuation(self,quotes,now):
        inventory={}
        for row in self.lots.values():
            qty,basis=D(row[3]),D(row[4])
            if qty:
                item=inventory.setdefault(row[1],[D(0),D(0)])
                item[0]=total((item[0],qty));item[1]=total((item[1],basis))
        gross=liquidation=D(self.cash)
        missing,uncertain,dust,normalized_only=[],[],[],[]
        for pair,(qty,basis) in inventory.items():
            quote=quotes.get(pair)
            if (not quote or quote.get('pair')!=pair or not timedelta(0)<=now-stamp(quote['observed_at'])<=timedelta(seconds=self.config.quote_max_age_seconds)):
                missing.append(pair);continue
            bid=_number(quote['bid']);gross=total((gross,product(qty,bid)))
            try:
                rule=self.filters[pair]
                step,minimum,maximum=self._market(pair,quote,rule,now)
                rounded=floor_quantity(qty,step);price=bid*(1-self.config.slippage)
                if rounded==0 or rounded*price<minimum:
                    if basis<=self.config.stake*self.config.max_dust_basis_fraction:dust.append(pair)
                elif rounded>maximum or rounded>_number(quote['bid_qty'])*self.config.max_depth_fraction:uncertain.append(pair)
                else:liquidation=total((liquidation,sale(rounded,price,self.config.exit_fee)[0]))
                if not _sources(quote,rule):normalized_only.append(pair)
            except (ValueError,KeyError,TypeError):uncertain.append(pair)
        result=dict(mode='paper',observed_at=now.isoformat(),cash=self.cash,
            equity=str(liquidation) if not missing and not uncertain else None,
            gross_bid_equity=str(gross) if not missing else None,missing_mark_pairs=sorted(set(missing)),
            uncertain_liquidation_pairs=sorted(set(uncertain)),nontradable_small_basis_pairs=sorted(set(dust)),
            valuation='conditional_top_book_liquidation_after_fee_slip_dust_zero_assumption',live_eligible=False)
        return result,dict(raw_sources_verified=not(missing or uncertain or normalized_only),conditional_valuation_known=not(missing or uncertain))

    def operation(self, prepared, complete):
        self.changes = {}
        name,inputs = prepared['operation'],prepared['inputs']
        self._begin_clocks(complete)
        now=self._clock() if name!='compact' else stamp(prepared['at'])
        before = self._wallet()
        if name == 'mark':
            for pair,rule in inputs['filters'].items():self._filter(pair,rule)
            result,quality = self.valuation(inputs['quotes'],now)
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
                    qty = total(D(r[3]) for r in self.lots.values() if r[1] == pair)
                    step = D(self.filters[pair]['quantity_step'])
                    rounded = floor_quantity(qty,step)
                    if rounded == 0 or rounded*D(inputs['quotes'][pair]['bid'])*(1-self.config.slippage) < D(self.filters[pair]['minimum_notional']):
                        material_zero = True
            self.material_zero_marks += int(material_zero)
            self.latest_source_qualified = quality['raw_sources_verified'] and quality['conditional_valuation_known'] and not material_zero
            self.coverage.mark(complete['at'],deadline,sources_known=self.latest_source_qualified)
            if stamp(complete['at'])<=stamp(self.protocol['end']):
                self.window_latest,self.window_source_qualified=result,self.latest_source_qualified
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
        self._finish_clocks();self._guard()
        self.scratch.db.commit()
