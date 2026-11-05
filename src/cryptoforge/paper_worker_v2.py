"""Opt-in v2 paper controller. No actual exchange-order API or default wiring."""
from datetime import UTC,datetime,timedelta
from decimal import Decimal
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import time as monotonic_time

from cryptoforge.live_learning_protocol import time
from cryptoforge.paper_wallet_v2 import PaperWalletV2
from cryptoforge.paper_producer_v2 import VERSION,runtime_hashes,arithmetic
from cryptoforge.spot_buy_math_v2 import floor_quantity,sum_exact
from cryptoforge.exit_rules import price_time_exit


class PaperWorkerV2:
    def __init__(self,wallet: PaperWalletV2,state_path: Path,*,policy,market,exit_indicator=None,clock=None):
        if type(wallet) is not PaperWalletV2:raise ValueError('paper v2 worker requires its versioned wallet')
        wallet._check_identity()
        self.wallet=wallet;self.path=Path(state_path).absolute();self.policy=deepcopy(policy);self.market=market
        self._check_path()
        self.exit_indicator=exit_indicator or (lambda pair:(False,[]))
        self.clock=clock or (lambda:datetime.now(UTC))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=self._db()
        try:
            existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if existing-{'worker_state','seen_predictions','intent_links','worker_events'}:
                raise ValueError('paper worker requires an isolated state database')
            db.executescript('''CREATE TABLE IF NOT EXISTS worker_state (key TEXT PRIMARY KEY,value TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS seen_predictions (id TEXT PRIMARY KEY,status TEXT,observed_at TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS intent_links (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS worker_events (id INTEGER PRIMARY KEY,observed_at TEXT,payload TEXT);''')
            identity=self._identity_value()
            self._frozen_identity=identity
            old=db.execute("SELECT value FROM worker_state WHERE key='identity'").fetchone()
            if old and old[0]!=identity:raise ValueError('paper worker policy/candidate cannot change')
            if not old:
                with db:db.execute("INSERT INTO worker_state VALUES ('identity',?)",(identity,))
            self.path.chmod(0o600)
        finally:db.close()

    def _db(self):return sqlite3.connect(self.path,timeout=1)

    def _check_path(self,*,required=False):
        if (required and not self.path.exists()) or self.path.resolve()!=self.path or self.path==self.wallet.path or (self.path.exists() and (not self.path.is_file() or self.path.stat().st_nlink!=1)):
            raise ValueError('paper v2 worker requires its isolated original file path')

    def _identity_value(self):
        return json.dumps({'producer_version':VERSION,'runtime':runtime_hashes(),'worker_path':str(self.path),
            'wallet_identity_sha256':hashlib.sha256(self.wallet._identity.encode()).hexdigest(),
            'candidate':self.wallet.candidate_sha,'policy':self.policy},sort_keys=True,default=str)

    def _event(self,payload):
        db=self._db()
        try:
            with db:db.execute('INSERT INTO worker_events(observed_at,payload) VALUES (?,?)',
                (self.clock().isoformat(),json.dumps(payload,sort_keys=True,default=str)))
        finally:db.close()

    def _enqueue(self,identity,pair,side,created,payload,source_key=None):
        # An intent and its source/reason survive a crash as one transaction.
        # Both stores are isolated paper SQLite files on the same host.
        if not pair.endswith('/USDT'):raise ValueError('paper quote currency mismatch')
        observed=self.clock()
        if created.tzinfo is None or not 0<=(observed-created).total_seconds()<=5:
            raise ValueError('paper enqueue observation cannot be backdated')
        db=self.wallet._db()
        try:
            db.execute('ATTACH DATABASE ? AS worker_meta',(str(self.path.resolve()),))
            db.execute('BEGIN IMMEDIATE')
            existing=db.execute('SELECT 1 FROM worker_meta.intent_links WHERE id=?',(identity,)).fetchone()
            if existing:db.rollback();return False
            db.execute('INSERT INTO intents VALUES (?,?,?,?,?,?,NULL)',
                (identity,pair,side,created.isoformat(),observed.isoformat(),'pending'))
            db.execute('INSERT INTO worker_meta.intent_links VALUES (?,?)',
                (identity,json.dumps(payload,sort_keys=True,default=str)))
            if source_key:db.execute('INSERT INTO worker_meta.seen_predictions VALUES (?,?,?)',
                (source_key,'queued',observed.isoformat()))
            db.commit();return True
        except Exception:db.rollback();raise
        finally:db.close()

    def _seen(self,identity,status):
        db=self._db()
        try:
            with db:db.execute('INSERT INTO seen_predictions VALUES (?,?,?) ON CONFLICT(id) DO NOTHING',
                (identity,status,self.clock().isoformat()))
        finally:db.close()

    def tick(self,predictions,*,window_start,window_end,entry_cutoff=None):
        self._check_path(required=True)
        self.wallet._check_identity()
        if not self.policy.get('enabled') or self.policy.get('status')!='frozen':
            return {'status':'paper_policy_disabled','network_requests':0,'new_intents':0}
        if self._identity_value()!=self._frozen_identity:raise ValueError('paper runtime policy cannot change in place')
        db=self._db()
        try:
            row=db.execute("SELECT value FROM worker_state WHERE key='identity'").fetchone()
            if not row or row[0]!=self._frozen_identity:raise ValueError('paper v2 stored worker identity changed')
        finally:db.close()
        with arithmetic():
            return self._tick(predictions,window_start=window_start,window_end=window_end,entry_cutoff=entry_cutoff)

    def _tick(self,predictions,*,window_start,window_end,entry_cutoff=None):
        if not self.policy.get('enabled') or self.policy.get('status')!='frozen':
            return {'status':'paper_policy_disabled','network_requests':0,'new_intents':0}
        current_identity=self._identity_value()
        if current_identity!=self._frozen_identity:raise ValueError('paper runtime policy cannot change in place')
        now=self.clock()
        entry_cutoff=entry_cutoff or window_end
        if not window_start<=now<window_end:
            return {'status':'outside_paper_window','network_requests':0,'new_intents':0}
        start_wall=monotonic_time.monotonic();runtime=self.policy['runtime']
        db=self._db()
        try:
            seen={r[0] for r in db.execute('SELECT id FROM seen_predictions')}
            linked={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,payload FROM intent_links')}
        finally:db.close()
        pending=self.wallet.pending_intents();new=0;errors={};results=[]
        for prediction in sorted(predictions,key=lambda row:(time(row['predicted_at']),row['opportunity'])):
            if prediction['candidate_sha256']!=self.wallet.candidate_sha:continue
            identity=hashlib.sha256((prediction['candidate_sha256']+'|'+prediction['opportunity']).encode()).hexdigest()
            if identity in seen:continue
            predicted=time(prediction['predicted_at'])
            # Earlier sealed-test forecasts are outside this experiment's source scope.
            # Do not record them as lost opportunities or pollute paired source IDs.
            if not window_start<=predicted<window_end:continue
            if predicted>now:
                self._seen(identity,'outside_window_or_future');continue
            if not prediction.get('observed_at') or not predicted<=time(prediction['observed_at'])<=now:
                self._seen(identity,'unverified_prediction_observation');continue
            if not prediction['would_enter']:
                self._seen(identity,'candidate_rejected');continue
            deadline=predicted+timedelta(seconds=self.wallet.config.signal_expiry_seconds)
            if now>=deadline:
                self._seen(identity,'source_prediction_expired');continue
            if now>=entry_cutoff:
                self._seen(identity,'paper_entry_window_finished');continue
            if new>=runtime['maximum_new_signals_per_tick']:break
            intent='paper-buy:'+identity
            if self._enqueue(intent,prediction['pair'],'Buy',now,
                {'source_prediction':prediction,'source_deadline':deadline.isoformat()},source_key=identity):new+=1
        for intent in self.wallet.pending_intents():
            if intent['side']=='Buy' and self.clock()>=entry_cutoff:
                self.wallet.cancel_pending(intent['id'],'paper_entry_window_finished')
        pending=self.wallet.pending_intents();snapshot=self.wallet.snapshot()
        pairs=sorted({lot['pair'] for lot in snapshot['open_lots']}|{row['pair'] for row in pending})
        quotes={};filters={};requests=0
        for pair in pairs:
            if monotonic_time.monotonic()-start_wall>=runtime['wall_budget_seconds']:
                errors[pair]='paper_tick_wall_budget_exhausted';continue
            try:
                quotes[pair],filters[pair]=self.market(pair);requests+=1
            except Exception as exc:errors[pair]=type(exc).__name__
        mark=self.wallet.mark(quotes,filters)
        # Re-read links: entries queued above need their original expiry guard.
        db=self._db()
        try:linked={r[0]:json.loads(r[1]) for r in db.execute('SELECT id,payload FROM intent_links')}
        finally:db.close()
        for intent in sorted(pending,key=lambda row:(row['side']=='Buy',row['created_at'],row['id'])):
            if intent['side']=='Buy' and self.clock()>=entry_cutoff:
                self.wallet.cancel_pending(intent['id'],'paper_entry_window_finished');continue
            link=linked.get(intent['id'],{})
            if link.get('source_deadline') and self.clock()>=time(link['source_deadline']):
                self.wallet.cancel_pending(intent['id'],'source_prediction_expired');continue
            pair=intent['pair']
            if pair not in quotes:continue
            try:
                result=self.wallet.execute(intent['id'],quotes[pair],filters[pair],entry_cutoff=entry_cutoff);results.append(result['status'])
                self._event({'intent':intent['id'],'result':result})
                mark=self.wallet.mark(quotes,filters)
            except Exception as exc:errors['intent:'+intent['id']]=type(exc).__name__
        snapshot=self.wallet.snapshot();pending=self.wallet.pending_intents()
        selling={row['pair'] for row in pending if row['side']=='Sell'}
        by_pair={}
        for lot in snapshot['open_lots']:by_pair.setdefault(lot['pair'],[]).append(lot)
        for pair,lots in by_pair.items():
            if pair in selling or pair not in quotes:continue
            quote=quotes[pair];rules=filters[pair]
            if not timedelta(0)<=self.clock()-time(quote['observed_at'])<=timedelta(seconds=self.wallet.config.quote_max_age_seconds):
                errors['exit:'+pair]='stale_exit_quote';continue
            qty=sum_exact(Decimal(r['quantity']) for r in lots)
            step=Decimal(rules['quantity_step']);sellable=floor_quantity(qty,step)
            if sellable*Decimal(quote['bid'])*(1-self.wallet.config.slippage)<Decimal(rules['minimum_notional']):continue
            buys=[f for f in snapshot['fills'] if f['pair']==pair and f['side']=='Buy']
            latest=max(buys,key=lambda row:row['fill_sequence'])
            exit_rule=price_time_exit(price=Decimal(quote['bid']),entry_price=Decimal(latest['price']),
                stop_fraction=Decimal(self.policy['exits']['stop_fraction']),
                elapsed_seconds=(self.clock()-time(latest['filled_at'])).total_seconds(),
                maximum_hold_seconds=self.policy['exits']['maximum_hold_seconds'])
            reason=None
            if self.clock()>=entry_cutoff:reason='paper_window_closeout'
            elif exit_rule is not None:reason={'stop':'paper_hard_stop','timeout':'paper_maximum_hold'}[exit_rule]
            elif self.policy['exits'].get('shared_exit_signal'):
                if monotonic_time.monotonic()-start_wall>=runtime['wall_budget_seconds']:
                    errors['exit:'+pair]='paper_exit_wall_budget_exhausted';continue
                try:
                    exits,reasons=self.exit_indicator(pair)
                    if exits:reason='shared_exit_signal'
                except Exception as exc:errors['exit:'+pair]=type(exc).__name__
            if reason:
                inventory_key=hashlib.sha256(json.dumps([(r['id'],r['quantity']) for r in lots],sort_keys=True).encode()).hexdigest()
                identity='paper-sell:'+inventory_key+':'+self.clock().isoformat()
                self._enqueue(identity,pair,'Sell',self.clock(),{'exit_reason':reason,'inventory_key':inventory_key})
                self._event({'intent':identity,'exit_reason':reason})
        report={'producer_version':VERSION,'status':'paper_tick_complete','new_intents':new,'market_observations':requests,
                'fills_processed':results,'errors':errors,'equity_known':mark['equity'] is not None,
                'live_promotion_allowed':False,'mode':'paper'}
        self._event(report)
        return report
