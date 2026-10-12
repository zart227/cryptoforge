"""Isolated prospective quote-driven Spot simulation. No exchange-order API.

Top-of-book prices with adverse slippage are assumptions, not guaranteed fills.
Entry fees are deducted in base quantity, exit fees in quote cash.
"""
from dataclasses import dataclass,asdict
from datetime import UTC,datetime,timedelta
from decimal import Decimal,ROUND_DOWN
import hashlib
import json
from pathlib import Path
import sqlite3
from cryptoforge.spot_buy_math import spot_acquisition,spot_sale

D=Decimal


def _time(value):
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('timezone-aware paper event required')
    return result


def _number(value,*,zero=False):
    result=D(str(value))
    if not result.is_finite() or result<0 or (not zero and result==0):raise ValueError('invalid paper quantity/price')
    return result


@dataclass(frozen=True)
class PaperConfig:
    capital: Decimal
    stake: Decimal
    entry_fee: Decimal
    exit_fee: Decimal
    slippage: Decimal
    cost_assumption_id: str
    max_positions: int=6
    max_daily_loss: Decimal=D('2')
    delay_seconds: int=1
    signal_expiry_seconds: int=30
    quote_max_age_seconds: int=10
    filter_max_age_seconds: int=300
    max_depth_fraction: Decimal=D('.01')
    max_dust_basis_fraction: Decimal=D('.01')
    entry_stop_reserve_fraction: Decimal=D('.04')

    def __post_init__(self):
        for field in ('capital','stake','max_daily_loss','max_depth_fraction','max_dust_basis_fraction','entry_stop_reserve_fraction'):
            object.__setattr__(self,field,_number(getattr(self,field)))
        for field in ('entry_fee','exit_fee','slippage'):
            value=_number(getattr(self,field),zero=True)
            object.__setattr__(self,field,value)
            if value>=1:raise ValueError('paper cost fractions must be below one')
        if not 0<_number(self.entry_stop_reserve_fraction)<1:raise ValueError('invalid stop reserve')
        _number(self.max_depth_fraction);_number(self.max_dust_basis_fraction)
        if self.max_dust_basis_fraction>1:raise ValueError('invalid residual basis budget')
        if not 0<self.max_depth_fraction<=1:raise ValueError('invalid displayed-depth participation')
        if (self.stake>self.capital or self.max_positions<1 or self.delay_seconds<1 or
            self.signal_expiry_seconds<=self.delay_seconds or self.quote_max_age_seconds<1 or
            self.filter_max_age_seconds<1 or not self.cost_assumption_id):raise ValueError('invalid paper policy')


class PaperWallet:
    def __init__(self,path: Path,*,candidate_sha: str,config: PaperConfig,clock=None):
        if len(candidate_sha)!=64 or any(c not in '0123456789abcdef' for c in candidate_sha):
            raise ValueError('explicit candidate artifact SHA required')
        self.path=path;self.config=config;self.candidate_sha=candidate_sha
        self.clock=clock or (lambda:datetime.now(UTC));self._initialize()

    def _db(self):return sqlite3.connect(self.path,timeout=1)

    def _initialize(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        policy=json.dumps({'candidate_sha':self.candidate_sha,'config':asdict(self.config)},sort_keys=True,default=str)
        db=self._db()
        try:
            existing={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            allowed={'state','intents','lots','fills','closed_segments','marks','market_cache'}
            if existing and (existing-allowed or 'state' not in existing):
                raise ValueError('unrelated database cannot become a paper wallet')
            if existing and not db.execute("SELECT 1 FROM state WHERE key='policy'").fetchone():
                raise ValueError('existing paper database is missing its immutable policy')
            db.executescript('''CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS intents (id TEXT PRIMARY KEY,pair TEXT,side TEXT,created_at TEXT,observed_at TEXT,status TEXT,reason TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS lots (id TEXT PRIMARY KEY,pair TEXT,opened_at TEXT,qty TEXT,cost TEXT,entry_fee_quote TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS fills (intent_id TEXT PRIMARY KEY,payload TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS closed_segments (id INTEGER PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS market_cache (pair TEXT PRIMARY KEY,filters TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS marks (id INTEGER PRIMARY KEY,observed_at TEXT,payload TEXT NOT NULL);''')
            old=db.execute("SELECT value FROM state WHERE key='policy'").fetchone()
            if old and old[0]!=policy:raise ValueError('paper wallet candidate/policy cannot change')
            if not old:
                with db:
                    db.execute("INSERT INTO state VALUES ('policy',?)",(policy,))
                    db.execute("INSERT INTO state VALUES ('cash',?)",(str(self.config.capital),))
            self.path.chmod(0o600)
        finally:db.close()

    def enqueue(self,intent_id,pair,side,*,created_at):
        now=self.clock()
        if now.tzinfo is None or created_at.tzinfo is None or not 0<=(now-created_at).total_seconds()<=5:
            raise ValueError('paper signals cannot be backdated')
        if side not in {'Buy','Sell'}:raise ValueError('Spot Buy/Sell only')
        if not pair.endswith('/USDT'):raise ValueError('USDT quote wallet only')
        db=self._db()
        try:
            old=db.execute('SELECT pair,side,created_at FROM intents WHERE id=?',(intent_id,)).fetchone()
            values=(pair,side,created_at.isoformat())
            if old:
                if old!=values:raise ValueError('paper signal cannot be overwritten')
                return False
            with db:db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,NULL)',
                (intent_id,pair,side,created_at.isoformat(),now.isoformat(),'pending'))
            return True
        finally:db.close()

    def execute(self,intent_id,quote,filters):
        now=self.clock();db=self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT pair,side,created_at,observed_at,status FROM intents WHERE id=?',(intent_id,)).fetchone()
            if not row:raise ValueError('paper intent must exist before execution')
            pair,side,created,enqueued,status=row
            if status!='pending':db.rollback();return {'status':status,'duplicate':True}
            created=_time(created);observed=_time(quote['observed_at'])
            age=(now-created).total_seconds()
            if age>self.config.signal_expiry_seconds:
                db.execute("UPDATE intents SET status='rejected',reason='expired_signal',observed_at=? WHERE id=?",(now.isoformat(),intent_id));db.commit()
                return {'status':'rejected','reason':'expired_signal'}
            if observed<max(created,_time(enqueued))+timedelta(seconds=self.config.delay_seconds):
                db.rollback();return {'status':'pending','reason':'awaiting_later_quote'}
            step,minimum,maximum=self._validate_market(pair,quote,filters,now)
            bid=_number(quote['bid']);ask=_number(quote['ask'])
            depth=_number(quote['ask_qty'] if side=='Buy' else quote['bid_qty'])
            cash=D(db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0])
            lots=db.execute('SELECT id,pair,opened_at,qty,cost,entry_fee_quote FROM lots ORDER BY opened_at,id').fetchall()
            lots=[lot for lot in lots if D(lot[3])>0]
            owned=[lot for lot in lots if lot[1]==pair]
            self._store_filters(db,pair,filters)
            if side=='Buy':
                if self._daily_loss_hit(db,now):return self._reject(db,intent_id,'daily_equity_guard_or_missing_fresh_mark')
                owned_qty=sum((D(lot[3]) for lot in owned),D(0));owned_cost=sum((D(lot[4]) for lot in owned),D(0))
                owned_rounded=(owned_qty/step).to_integral_value(rounding=ROUND_DOWN)*step
                if owned and (owned_rounded*bid>=minimum or owned_cost>self.config.stake*self.config.max_dust_basis_fraction):
                    return self._reject(db,intent_id,'existing_inventory_requires_review')
                active={lot[1] for lot in lots}
                latest=db.execute('SELECT payload FROM marks ORDER BY id DESC LIMIT 1').fetchone()
                if latest:active-=set(json.loads(latest[0]).get('nontradable_small_basis_pairs',[]))
                if owned and owned_qty and owned_cost<=self.config.stake*self.config.max_dust_basis_fraction and owned_rounded*bid<minimum:active.discard(pair)
                if len(active)>=self.config.max_positions:return self._reject(db,intent_id,'position_limit')
                if cash<self.config.stake:return self._reject(db,intent_id,'insufficient_shared_cash')
                price=ask*(1+self.config.slippage)
                purchase=spot_acquisition(stake=self.config.stake,price=price,quantity_step=step,
                    fee_fraction=self.config.entry_fee,fee_currency='base')
                gross_qty=purchase.gross_quantity
                if gross_qty<=0 or gross_qty*price<minimum:return self._reject(db,intent_id,'minimum_notional')
                quantity=purchase.net_quantity;cost=purchase.cash_cost
                if gross_qty>maximum or gross_qty>depth*self.config.max_depth_fraction:
                    return self._reject(db,intent_id,'size_or_displayed_liquidity_limit')
                rounded_exit=(quantity/step).to_integral_value(rounding=ROUND_DOWN)*step
                if (step*price>self.config.stake*self.config.max_dust_basis_fraction or
                    rounded_exit*bid*(1-self.config.entry_stop_reserve_fraction)*(1-self.config.slippage)<minimum):
                    return self._reject(db,intent_id,'exit_minimum_or_residual_precision_risk')
                fee=purchase.fee_quote_equivalent
                db.execute('INSERT INTO lots VALUES (?,?,?,?,?,?)',(intent_id,pair,now.isoformat(),str(quantity),str(cost),str(fee)))
                cash-=cost;proceeds=None
            else:
                total=sum((D(lot[3]) for lot in owned),D(0));quantity=(total/step).to_integral_value(rounding=ROUND_DOWN)*step
                price=bid*(1-self.config.slippage)
                if quantity<=0 or quantity*price<minimum:return self._reject(db,intent_id,'unsellable_inventory_preserved')
                if quantity>maximum or quantity>depth*self.config.max_depth_fraction:
                    return self._reject(db,intent_id,'size_or_displayed_liquidity_limit')
                sale=spot_sale(quantity=quantity,price=price,fee_fraction=self.config.exit_fee,fee_currency='quote')
                proceeds=sale.cash_proceeds;fee=sale.fee_amount
                left=quantity
                for lot in owned:
                    if not left:break
                    lot_id,_,opened,qty,basis,entry_fee=lot;qty=D(qty);basis=D(basis);entry_fee=D(entry_fee)
                    sold=min(left,qty);fraction=sold/qty;allocated=basis*fraction;entry_allocated=entry_fee*fraction
                    segment_sale=spot_sale(quantity=sold,price=price,fee_fraction=self.config.exit_fee,fee_currency='quote')
                    net=segment_sale.cash_proceeds-allocated
                    segment={'mode':'paper','candidate_sha256':self.candidate_sha,'entry_intent':lot_id,'exit_intent':intent_id,
                             'pair':pair,'opened_at':opened,'closed_at':now.isoformat(),'quantity':str(sold),
                             'cost':str(allocated),'net_pnl':str(net),'fees':str(entry_allocated+segment_sale.fee_amount)}
                    db.execute('INSERT INTO closed_segments(payload) VALUES (?)',(json.dumps(segment,sort_keys=True),))
                    db.execute('UPDATE lots SET qty=?,cost=?,entry_fee_quote=? WHERE id=?',
                        (str(qty-sold),str(basis-allocated),str(entry_fee-entry_allocated),lot_id));left-=sold
                cash+=proceeds;cost=None
            fill={'mode':'paper','candidate_sha256':self.candidate_sha,'intent_id':intent_id,'pair':pair,'side':side,
                  'signal_time':created.isoformat(),'quote_observed_at':observed.isoformat(),'filled_at':now.isoformat(),
                  'quantity':str(quantity),'price':str(price),'cost':str(cost) if cost is not None else None,
                  'proceeds':str(proceeds) if proceeds is not None else None,'fee_quote_equivalent':str(fee),
                  'fee_currency':'base' if side=='Buy' else 'quote',
                  'fee_amount':str(gross_qty*self.config.entry_fee) if side=='Buy' else str(fee),
                  'order_quantity':str(gross_qty if side=='Buy' else quantity),
                  'fill_assumption':'top_quote_adverse_slippage_not_guaranteed_market_fill',
                  'cost_assumption_id':self.config.cost_assumption_id,'quote':quote,'filters':filters}
            db.execute('INSERT INTO fills VALUES (?,?)',(intent_id,json.dumps(fill,sort_keys=True,default=str)))
            db.execute("UPDATE state SET value=? WHERE key='cash'",(str(cash),))
            db.execute("UPDATE intents SET status='filled',observed_at=? WHERE id=?",(now.isoformat(),intent_id));db.commit()
            return {'status':'filled','fill':fill}
        except Exception:db.rollback();raise
        finally:db.close()

    def _store_filters(self,db,pair,filters):
        if filters['pair']!=pair:raise ValueError('instrument cache identity mismatch')
        raw=json.dumps(filters,sort_keys=True,default=str)
        old=db.execute('SELECT filters FROM market_cache WHERE pair=?',(pair,)).fetchone()
        if old:
            previous=json.loads(old[0]);before=_time(previous['observed_at']);after=_time(filters['observed_at'])
            if after<before or (after==before and old[0]!=raw):
                raise ValueError('instrument observations cannot be rewound or rewritten')
        db.execute('INSERT INTO market_cache VALUES (?,?) ON CONFLICT(pair) DO UPDATE SET filters=excluded.filters',(pair,raw))

    def _validate_market(self,pair,quote,filters,now):
        if quote.get('market')!='spot' or filters.get('market')!='spot' or quote.get('venue')!='bybit_global' or filters.get('venue')!='bybit_global' or filters.get('status')!='Trading':
            raise ValueError('global Trading Spot metadata required')
        _number(quote['bid_qty']);_number(quote['ask_qty'])
        if quote['pair']!=pair or filters['pair']!=pair:raise ValueError('quote/filter identity mismatch')
        if not timedelta(0)<=now-_time(quote['observed_at'])<=timedelta(seconds=self.config.quote_max_age_seconds):
            raise ValueError('stale or future paper quote')
        if not timedelta(0)<=now-_time(filters['observed_at'])<=timedelta(seconds=self.config.filter_max_age_seconds):
            raise ValueError('stale or future instrument filters')
        if _number(quote['bid'])>_number(quote['ask']):raise ValueError('crossed book')
        return (_number(filters['quantity_step']),_number(filters['minimum_notional']),_number(filters['maximum_market_quantity']))

    def _reject(self,db,intent_id,reason):
        db.execute("UPDATE intents SET status='rejected',reason=?,observed_at=? WHERE id=?",(reason,self.clock().isoformat(),intent_id));db.commit()
        return {'status':'rejected','reason':reason}

    def _anchor(self,db,now,equity):
        key='day_anchor:'+now.astimezone(UTC).date().isoformat()
        existing=db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        if existing:return D(existing[0])
        # Carry an overnight gap from the previous valid observation rather
        # than quietly resetting the loss budget below the last known equity.
        prior_anchor=db.execute("SELECT value FROM state WHERE key LIKE 'day_anchor:%' ORDER BY key DESC LIMIT 1").fetchone()
        previous=D(prior_anchor[0]) if prior_anchor else equity
        for row in db.execute('SELECT payload FROM marks ORDER BY id DESC'):
            marked=json.loads(row[0])['equity']
            if marked is not None:previous=D(marked);break
        anchor=max(equity,previous)
        db.execute('INSERT INTO state VALUES (?,?)',(key,str(anchor)))
        return anchor

    def _daily_loss_hit(self,db,now):
        latest_row=db.execute('SELECT payload FROM marks ORDER BY id DESC LIMIT 1').fetchone()
        has_inventory=any(D(row[0])>0 for row in db.execute('SELECT qty FROM lots'))
        cash=D(db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0])
        if not latest_row:
            if has_inventory:return True
            self._anchor(db,now,cash);return False
        latest=json.loads(latest_row[0])
        if not timedelta(0)<=now-_time(latest['observed_at'])<=timedelta(seconds=self.config.quote_max_age_seconds) or latest['equity'] is None:
            return True
        equity=D(latest['equity']);anchor=self._anchor(db,now,equity)
        return anchor-equity>=self.config.max_daily_loss

    def mark(self,quotes,filters_by_pair=None):
        now=self.clock();db=self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            for pair,filters in (filters_by_pair or {}).items():
                self._store_filters(db,pair,filters)
            filters={pair:json.loads(raw) for pair,raw in db.execute('SELECT pair,filters FROM market_cache')}
            cash=D(db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0])
            totals={}
            for pair,qty,cost in db.execute('SELECT pair,qty,cost FROM lots'):
                qty=D(qty)
                if qty<=0:continue
                bucket=totals.setdefault(pair,[D(0),D(0)]);bucket[0]+=qty;bucket[1]+=D(cost)
            gross_equity=cash;liquidation=cash;missing=[];uncertain=[];dust=[]
            for pair,(qty,basis) in totals.items():
                quote=quotes.get(pair)
                if (not quote or quote.get('pair')!=pair or
                    not timedelta(0)<=now-_time(quote['observed_at'])<=timedelta(seconds=self.config.quote_max_age_seconds)):
                    missing.append(pair);continue
                gross_equity+=qty*_number(quote['bid'])
                try:
                    step,minimum,maximum=self._validate_market(pair,quote,filters[pair],now)
                    rounded=(qty/step).to_integral_value(rounding=ROUND_DOWN)*step
                    sell_price=_number(quote['bid'])*(1-self.config.slippage)
                    if rounded==0 or rounded*sell_price<minimum:
                        if basis<=self.config.stake*self.config.max_dust_basis_fraction:dust.append(pair)
                        # Nontradable inventory stays owned but has zero cash value.
                    elif rounded>maximum or rounded>_number(quote['bid_qty'])*self.config.max_depth_fraction:
                        uncertain.append(pair)
                    else:liquidation+=spot_sale(quantity=rounded,price=sell_price,fee_fraction=self.config.exit_fee,fee_currency='quote').cash_proceeds
                except (ValueError,KeyError,TypeError):uncertain.append(pair)
            payload={'mode':'paper','observed_at':now.isoformat(),'cash':str(cash),
                     'equity':str(liquidation) if not missing and not uncertain else None,
                     'gross_bid_equity':str(gross_equity) if not missing else None,
                     'missing_mark_pairs':sorted(set(missing)),'uncertain_liquidation_pairs':sorted(set(uncertain)),
                     'nontradable_small_basis_pairs':sorted(set(dust)),
                     'valuation':'conditional_top_book_liquidation_after_fee_slip_dust_zero_assumption',
                     'live_eligible':False}
            if payload['equity'] is not None:self._anchor(db,now,D(payload['equity']))
            db.execute('INSERT INTO marks(observed_at,payload) VALUES (?,?)',(now.isoformat(),json.dumps(payload,sort_keys=True)))
            db.commit();return payload
        except Exception:db.rollback();raise
        finally:db.close()

    def snapshot(self):
        db=self._db()
        try:
            policy=db.execute("SELECT value FROM state WHERE key='policy'").fetchone()[0]
            return {'mode':'paper','candidate_sha256':self.candidate_sha,'live_eligible':False,
                'policy_sha256':hashlib.sha256(policy.encode()).hexdigest(),
                'cash':db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0],
                'open_lots':[dict(zip(('id','pair','opened_at','quantity','cost','entry_fee'),row)) for row in
                             db.execute('SELECT * FROM lots ORDER BY opened_at,id') if D(row[3])>0],
                'closed_segments':[json.loads(row[0]) for row in db.execute('SELECT payload FROM closed_segments ORDER BY id')],
                'fills':[json.loads(row[0]) for row in db.execute('SELECT payload FROM fills ORDER BY intent_id')]}
        finally:db.close()


    def pending_intents(self):
        db=self._db()
        try:return [dict(zip(('id','pair','side','created_at','observed_at'),row)) for row in db.execute(
            "SELECT id,pair,side,created_at,observed_at FROM intents WHERE status='pending' ORDER BY created_at,id")]
        finally:db.close()

    def cancel_pending(self,intent_id,reason):
        db=self._db()
        try:
            with db:db.execute("UPDATE intents SET status='rejected',reason=?,observed_at=? WHERE id=? AND status='pending'",(reason,self.clock().isoformat(),intent_id))
        finally:db.close()
