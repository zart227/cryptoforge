"""Opt-in v2 paper wallet: committed fill order and strict affordable sizing.

Top-of-book prices with adverse slippage are assumptions, not guaranteed fills.
Entry fees are deducted in base quantity, exit fees in quote cash.
"""
from dataclasses import asdict
from datetime import UTC,datetime,timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from cryptoforge.spot_buy_math_v2 import spot_acquisition,spot_sale,floor_quantity,exact_product,sum_exact,subtract_exact,allocate_basis,_ratio
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_producer_v2 import VERSION,runtime_hashes,pinned_operation

D=Decimal


def _time(value):
    result=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('timezone-aware paper event required')
    return result


def _number(value,*,zero=False):
    result=D(str(value))
    _ratio(result,zero=zero)
    if not result.is_finite() or result<0 or (not zero and result==0):raise ValueError('invalid paper quantity/price')
    return result


class PaperWalletV2:
    def __init__(self,path: Path,*,candidate_sha: str,config: PaperConfig,clock=None):
        if len(candidate_sha)!=64 or any(c not in '0123456789abcdef' for c in candidate_sha):
            raise ValueError('explicit candidate artifact SHA required')
        self.path=Path(path).absolute();self.config=config;self.candidate_sha=candidate_sha
        if type(config) is not PaperConfig:raise ValueError('versioned PaperConfig required')
        self._check_path()
        for value in asdict(config).values():
            if isinstance(value,D):_ratio(value,zero=True)
        self.clock=clock or (lambda:datetime.now(UTC))
        self._runtime=runtime_hashes()
        self._initialize()
        self._identity=self._identity_value()

    def _identity_value(self):
        return json.dumps({'producer_version':VERSION,'runtime':self._runtime,
            'wallet_path':str(self.path),'candidate_sha':self.candidate_sha,'config':asdict(self.config)},sort_keys=True,default=str)

    def _check_path(self,*,required=False):
        if (required and not self.path.exists()) or self.path.resolve()!=self.path or (self.path.exists() and (not self.path.is_file() or self.path.stat().st_nlink!=1)):
            raise ValueError('paper v2 requires its isolated original file path')

    def _check_identity(self):
        self._check_path(required=True)
        if self._runtime!=runtime_hashes() or self._identity_value()!=self._identity:
            raise ValueError('paper v2 runtime/candidate/config cannot change')
        db=self._db()
        try:
            row=db.execute("SELECT value FROM state WHERE key='policy'").fetchone()
            if not row or row[0]!=self._identity:
                raise ValueError('paper v2 stored policy changed')
            if db.execute('SELECT 1 FROM fills f LEFT JOIN fill_order o ON o.intent_id=f.intent_id WHERE o.sequence IS NULL LIMIT 1').fetchone():
                raise ValueError('paper v2 missing causal fill order')
            if db.execute('SELECT 1 FROM lots l LEFT JOIN fills f ON f.intent_id=l.id WHERE f.intent_id IS NULL LIMIT 1').fetchone():
                raise ValueError('paper v2 orphaned lot')
            if db.execute('SELECT 1 FROM fill_order o LEFT JOIN fills f ON f.intent_id=o.intent_id WHERE f.intent_id IS NULL OR o.sequence<=0 LIMIT 1').fetchone():
                raise ValueError('paper v2 invalid causal fill order')
            for sequence,payload in db.execute('SELECT o.sequence,f.payload FROM fill_order o JOIN fills f ON f.intent_id=o.intent_id'):
                fill=json.loads(payload)
                if type(fill.get('fill_sequence')) is not int or fill['fill_sequence']!=sequence or fill.get('producer_version')!=VERSION:
                    raise ValueError('paper v2 causal fill identity differs')
        finally:db.close()

    def _db(self):return sqlite3.connect(self.path,timeout=1)

    def _initialize(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        policy=self._identity_value()
        db=self._db()
        try:
            existing={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            allowed={'state','intents','lots','fills','closed_segments','marks','market_cache','fill_order'}
            if existing and existing!=allowed:
                raise ValueError('paper v2 requires a new namespace or its exact versioned database')
            if existing and not db.execute("SELECT 1 FROM state WHERE key='policy'").fetchone():
                raise ValueError('existing paper database is missing its immutable policy')
            db.executescript('''CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY,value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS intents (id TEXT PRIMARY KEY,pair TEXT,side TEXT,created_at TEXT,observed_at TEXT,status TEXT,reason TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS lots (id TEXT PRIMARY KEY,pair TEXT,opened_at TEXT,qty TEXT,cost TEXT,entry_fee_quote TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS fills (intent_id TEXT PRIMARY KEY,payload TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS fill_order (sequence INTEGER PRIMARY KEY AUTOINCREMENT,intent_id TEXT NOT NULL UNIQUE);
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

    @pinned_operation
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

    @pinned_operation
    def execute(self,intent_id,quote,filters,*,entry_cutoff=None):
        db=self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            now=self.clock()
            row=db.execute('SELECT pair,side,created_at,observed_at,status FROM intents WHERE id=?',(intent_id,)).fetchone()
            if not row:raise ValueError('paper intent must exist before execution')
            pair,side,created,enqueued,status=row
            if status!='pending':db.rollback();return {'status':status,'duplicate':True}
            if side=='Buy' and entry_cutoff is not None and now>=entry_cutoff:
                return self._reject(db,intent_id,'paper_entry_window_finished')
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
            lots=db.execute('SELECT l.id,l.pair,l.opened_at,l.qty,l.cost,l.entry_fee_quote FROM lots l JOIN fill_order f ON f.intent_id=l.id ORDER BY f.sequence').fetchall()
            lots=[lot for lot in lots if D(lot[3])>0]
            owned=[lot for lot in lots if lot[1]==pair]
            self._store_filters(db,pair,filters)
            if side=='Buy':
                if self._daily_loss_hit(db,now):return self._reject(db,intent_id,'daily_equity_guard_or_missing_fresh_mark')
                owned_qty=sum_exact(D(lot[3]) for lot in owned);owned_cost=sum_exact(D(lot[4]) for lot in owned)
                owned_rounded=floor_quantity(owned_qty,step)
                if owned and (owned_rounded*bid>=minimum or owned_cost>self.config.stake*self.config.max_dust_basis_fraction):
                    return self._reject(db,intent_id,'existing_inventory_requires_review')
                active={lot[1] for lot in lots}
                latest=db.execute('SELECT payload FROM marks ORDER BY id DESC LIMIT 1').fetchone()
                if latest:active-=set(json.loads(latest[0]).get('nontradable_small_basis_pairs',[]))
                if owned and owned_qty and owned_cost<=self.config.stake*self.config.max_dust_basis_fraction and owned_rounded*bid<minimum:active.discard(pair)
                if len(active)>=self.config.max_positions:return self._reject(db,intent_id,'position_limit')
                if cash<self.config.stake:return self._reject(db,intent_id,'insufficient_shared_cash')
                price=exact_product(ask,1+self.config.slippage)
                purchase=spot_acquisition(stake=self.config.stake,price=price,quantity_step=step,
                    fee_fraction=self.config.entry_fee,fee_currency='base')
                gross_qty=purchase.gross_quantity
                if gross_qty<=0 or gross_qty*price<minimum:return self._reject(db,intent_id,'minimum_notional')
                quantity=purchase.net_quantity;cost=purchase.cash_cost
                if cost>self.config.stake or cost>cash:
                    raise ValueError('paper v2 strict stake/cash invariant failed')
                if gross_qty>maximum or gross_qty>depth*self.config.max_depth_fraction:
                    return self._reject(db,intent_id,'size_or_displayed_liquidity_limit')
                rounded_exit=floor_quantity(quantity,step)
                if (step*price>self.config.stake*self.config.max_dust_basis_fraction or
                    rounded_exit*bid*(1-self.config.entry_stop_reserve_fraction)*(1-self.config.slippage)<minimum):
                    return self._reject(db,intent_id,'exit_minimum_or_residual_precision_risk')
                fee=purchase.fee_quote_equivalent
                db.execute('INSERT INTO lots VALUES (?,?,?,?,?,?)',(intent_id,pair,now.isoformat(),str(quantity),str(cost),str(fee)))
                cash=subtract_exact(cash,cost);proceeds=None
            else:
                total=sum_exact(D(lot[3]) for lot in owned);quantity=floor_quantity(total,step)
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
                    sold=min(left,qty);allocated=allocate_basis(basis,sold,qty);entry_allocated=allocate_basis(entry_fee,sold,qty)
                    segment_sale=spot_sale(quantity=sold,price=price,fee_fraction=self.config.exit_fee,fee_currency='quote')
                    net=subtract_exact(segment_sale.cash_proceeds,allocated)
                    segment={'mode':'paper','candidate_sha256':self.candidate_sha,'entry_intent':lot_id,'exit_intent':intent_id,
                             'pair':pair,'opened_at':opened,'closed_at':now.isoformat(),'quantity':str(sold),
                             'cost':str(allocated),'net_pnl':str(net),'fees':str(sum_exact((entry_allocated,segment_sale.fee_amount)))}
                    db.execute('INSERT INTO closed_segments(payload) VALUES (?)',(json.dumps(segment,sort_keys=True),))
                    db.execute('UPDATE lots SET qty=?,cost=?,entry_fee_quote=? WHERE id=?',
                        (str(subtract_exact(qty,sold)),str(subtract_exact(basis,allocated)),str(subtract_exact(entry_fee,entry_allocated)),lot_id));left=subtract_exact(left,sold)
                cash=sum_exact((cash,proceeds));cost=None
            sequence=db.execute('INSERT INTO fill_order(intent_id) VALUES (?)',(intent_id,)).lastrowid
            if cash<0:raise ValueError('paper v2 negative cash forbidden')
            fill={'producer_version':VERSION,'fill_sequence':sequence,'mode':'paper','candidate_sha256':self.candidate_sha,'intent_id':intent_id,'pair':pair,'side':side,
                  'signal_time':created.isoformat(),'quote_observed_at':observed.isoformat(),'filled_at':now.isoformat(),
                  'quantity':str(quantity),'price':str(price),'cost':str(cost) if cost is not None else None,
                  'proceeds':str(proceeds) if proceeds is not None else None,'fee_quote_equivalent':str(fee),
                  'fee_currency':'base' if side=='Buy' else 'quote',
                  'fee_amount':str(purchase.fee_amount) if side=='Buy' else str(fee),
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
        return subtract_exact(anchor,equity)>=self.config.max_daily_loss

    @pinned_operation
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
                bucket=totals.setdefault(pair,[D(0),D(0)]);bucket[0]=sum_exact((bucket[0],qty));bucket[1]=sum_exact((bucket[1],D(cost)))
            gross_equity=cash;liquidation=cash;missing=[];uncertain=[];dust=[]
            for pair,(qty,basis) in totals.items():
                quote=quotes.get(pair)
                if (not quote or quote.get('pair')!=pair or
                    not timedelta(0)<=now-_time(quote['observed_at'])<=timedelta(seconds=self.config.quote_max_age_seconds)):
                    missing.append(pair);continue
                gross_equity=sum_exact((gross_equity,exact_product(qty,_number(quote['bid']))))
                try:
                    step,minimum,maximum=self._validate_market(pair,quote,filters[pair],now)
                    rounded=floor_quantity(qty,step)
                    sell_price=_number(quote['bid'])*(1-self.config.slippage)
                    if rounded==0 or rounded*sell_price<minimum:
                        if basis<=self.config.stake*self.config.max_dust_basis_fraction:dust.append(pair)
                        # Nontradable inventory stays owned but has zero cash value.
                    elif rounded>maximum or rounded>_number(quote['bid_qty'])*self.config.max_depth_fraction:
                        uncertain.append(pair)
                    else:liquidation=sum_exact((liquidation,spot_sale(quantity=rounded,price=sell_price,fee_fraction=self.config.exit_fee,fee_currency='quote').cash_proceeds))
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

    @pinned_operation
    def snapshot(self):
        db=self._db()
        try:
            db.execute('BEGIN')
            policy=db.execute("SELECT value FROM state WHERE key='policy'").fetchone()[0]
            return {'producer_version':VERSION,'mode':'paper','candidate_sha256':self.candidate_sha,'live_eligible':False,
                'policy_sha256':hashlib.sha256(policy.encode()).hexdigest(),
                'cash':db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0],
                'open_lots':[dict(zip(('id','pair','opened_at','quantity','cost','entry_fee'),row)) for row in
                             db.execute('SELECT l.* FROM lots l JOIN fill_order f ON f.intent_id=l.id ORDER BY f.sequence') if D(row[3])>0],
                'closed_segments':[json.loads(row[0]) for row in db.execute('SELECT payload FROM closed_segments ORDER BY id')],
                'fills':[json.loads(row[0]) for row in db.execute('SELECT f.payload FROM fills f JOIN fill_order o ON o.intent_id=f.intent_id ORDER BY o.sequence')]}
        finally:db.close()


    @pinned_operation
    def pending_intents(self):
        db=self._db()
        try:return [dict(zip(('id','pair','side','created_at','observed_at'),row)) for row in db.execute(
            "SELECT id,pair,side,created_at,observed_at FROM intents WHERE status='pending' ORDER BY created_at,id")]
        finally:db.close()

    @pinned_operation
    def cancel_pending(self,intent_id,reason):
        db=self._db()
        try:
            with db:db.execute("UPDATE intents SET status='rejected',reason=?,observed_at=? WHERE id=? AND status='pending'",(reason,self.clock().isoformat(),intent_id))
        finally:db.close()
