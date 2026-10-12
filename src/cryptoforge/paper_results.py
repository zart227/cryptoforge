"""Read-only simulated results, distinct from actual execution training labels."""
from collections import Counter
from datetime import UTC,datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from cryptoforge.live_learning_protocol import time

D=Decimal


def export_results(wallet_path: Path,worker_path: Path,*,as_of: datetime) -> dict:
    if as_of.tzinfo is None:raise ValueError('timezone-aware paper export required')
    if not wallet_path.exists() or not worker_path.exists():
        return {'status':'paper_not_started','mode':'paper','simulated':True,'campaigns':[],
                'live_promotion_allowed':False,'profitability_established':False}
    db=sqlite3.connect('file:'+str(wallet_path.resolve())+'?mode=ro',uri=True)
    try:
        db.execute('ATTACH DATABASE ? AS worker',('file:'+str(worker_path.resolve())+'?mode=ro',))
        db.execute('BEGIN')
        state=dict(db.execute('SELECT key,value FROM state'));policy=json.loads(state['policy'])
        identity=json.loads(db.execute("SELECT value FROM worker.worker_state WHERE key='identity'").fetchone()[0])
        if identity['candidate']!=policy['candidate_sha']:raise ValueError('paper ledger candidate mismatch')
        links={key:json.loads(raw) for key,raw in db.execute('SELECT id,payload FROM worker.intent_links')}
        fills=[json.loads(raw) for raw, in db.execute('SELECT payload FROM fills')]
        segments=[json.loads(raw) for raw, in db.execute('SELECT payload FROM closed_segments ORDER BY id')]
        marks,mark_quality=_compress_marks(db,policy)
        intents=[dict(zip(('id','pair','side','created_at','observed_at','status','reason'),row)) for row in
                 db.execute('SELECT * FROM intents ORDER BY created_at,id')]
        lots={row[0]:dict(zip(('id','pair','opened_at','quantity','cost','entry_fee_quote'),row)) for row in
              db.execute('SELECT * FROM lots')}
        events=[];error_count=0
        for stamp,raw in db.execute('SELECT observed_at,payload FROM worker.worker_events ORDER BY id'):
            if time(stamp)>as_of:raise ValueError('cannot reconstruct earlier paper worker state from future events')
            event=json.loads(raw)
            if event.get('errors'):
                error_count+=1
                if len(events)<100:events.append({'observed_at':stamp,'payload':event})
        seen=[dict(zip(('id','status','observed_at'),row)) for row in db.execute('SELECT * FROM worker.seen_predictions')]
        db.rollback()
    finally:db.close()
    if any(time(row['filled_at'])>as_of for row in fills) or any(time(row['observed_at'])>as_of for row in marks):
        raise ValueError('cannot reconstruct an earlier paper balance from current inventory')
    if any(time(row['observed_at'])>as_of or time(row['created_at'])>as_of for row in intents) or any(time(row['observed_at'])>as_of for row in seen):
        raise ValueError('cannot reconstruct earlier paper decision state from current intents')
    if any(row.get('mode')!='paper' or row.get('candidate_sha256')!=policy['candidate_sha'] for row in fills+segments):
        raise ValueError('real or foreign candidate events cannot become simulated evidence')
    buys={row['intent_id']:row for row in fills if row['side']=='Buy'};by_buy={key:[] for key in buys}
    for row in segments:
        if row['entry_intent'] not in buys:raise ValueError('paper closing segment has no acquisition')
        by_buy[row['entry_intent']].append(row)
    campaigns=[]
    for key,buy in sorted(buys.items()):
        lot=lots[key];closed=by_buy[key];link=links.get(key,{})
        original_cost=D(buy['cost']);closed_cost=sum((D(row['cost']) for row in closed),D(0))
        basis=D(lot['cost']);qty=D(lot['quantity']);closed_pnl=sum((D(row['net_pnl']) for row in closed),D(0))
        if abs(original_cost-closed_cost-basis)>D('1e-20'):
            raise ValueError('paper acquisition basis is not conserved')
        entry_fee=D(buy['fee_quote_equivalent'])
        exit_fees=sum((D(row['fees'])-entry_fee*(D(row['cost'])/original_cost) for row in closed),D(0))
        source=link.get('source_prediction')
        campaigns.append({'mode':'paper','outcome_type':'simulated_cash_recovery',
            'candidate_artifact_sha256':policy['candidate_sha'],'paper_buy_intent':key,'pair':buy['pair'],
            'entry_at':buy['filled_at'],'cost':str(original_cost),'closed_cost':str(closed_cost),
            'closed_net_pnl':str(closed_pnl),'remaining_basis':str(basis),'remaining_quantity':str(qty),
            'cash_recovery_net_dust_zero':str(closed_pnl-basis),'entry_fee_quote_equivalent':str(entry_fee),
            'exit_fee_quote':str(exit_fees),'source_segments':len(closed),
            'has_exit':bool(closed),'fully_closed':qty==0,'source_prediction':source,
            'exit_reasons':[links.get(row['exit_intent'],{}).get('exit_reason','unknown') for row in closed],
            'closed_at':max((row['closed_at'] for row in closed),default=None)})
    capital=D(policy['config']['capital']);cash=D(state['cash']);basis=sum((D(row['cost']) for row in lots.values()),D(0))
    realized=sum((D(row['net_pnl']) for row in segments),D(0))
    if abs(cash+basis-capital-realized)>D('1e-20'):
        raise ValueError('paper wallet cash/basis/PnL does not reconcile')
    result={'schema_version':'paper-results-v1','status':'simulated_evidence_only','mode':'paper','simulated':True,
        'as_of':as_of.isoformat(),'candidate_artifact_sha256':policy['candidate_sha'],
        'policy':policy,'worker_policy':identity['policy'],'policy_sha256':hashlib.sha256(state['policy'].encode()).hexdigest(),
        'capital':str(capital),'cash':str(cash),'remaining_basis':str(basis),'realized_net_pnl':str(realized),
        'campaigns':campaigns,'fills':sorted(fills,key=lambda row:(time(row['filled_at']),row['intent_id'])),
        'equity_marks':marks,'mark_quality':mark_quality,'intents':intents,'worker_events':events,'seen_predictions':seen,
        'execution_counts':dict(Counter(row['side']+':'+row['status'] for row in intents)),
        'rejection_reasons':dict(Counter(row['side']+':'+str(row.get('reason')) for row in intents if row['status']=='rejected')),
        'worker_quality_errors':events,'worker_quality_error_count':error_count,
        'mark_export_policy':'minute_last_samples_with_exact_full_stream_risk_quality',
        'real_training_examples_allowed':False,'live_promotion_allowed':False,'profitability_established':False,
        'scope':'baseline_approved_opportunity_stream_simulated_top_book_execution'}
    result['snapshot_sha256']=hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()
    return result


def _compress_marks(db,policy):
    buckets={};count=known=0;first=last=None;peak=Decimal(policy['config']['capital']);drawdown=Decimal(0);max_gap=0
    digest=hashlib.sha256()
    for stamp,raw in db.execute('SELECT observed_at,payload FROM marks ORDER BY id'):
        observed=time(stamp);m=json.loads(raw)
        if last and observed<last:raise ValueError('paper mark chronology moved backwards')
        if last:max_gap=max(max_gap,(observed-last).total_seconds())
        if first is None:first=observed
        last=observed;count+=1;digest.update((stamp+'\n'+raw+'\n').encode())
        if m.get('equity') is not None:
            equity=Decimal(m['equity'])
            if not equity.is_finite() or equity<0:raise ValueError('invalid paper equity stream')
            known+=1;peak=max(peak,equity);drawdown=max(drawdown,(peak-equity)/peak)
        bucket=observed.astimezone(UTC).replace(second=0,microsecond=0).isoformat();buckets[bucket]=m
    quality={'raw_mark_count':count,'known_mark_count':known,'all_marks_known':bool(count) and count==known,
             'first_mark_at':first.isoformat() if first else None,'last_mark_at':last.isoformat() if last else None,
             'max_gap_seconds':max_gap,'max_drawdown':str(drawdown),'full_stream_sha256':digest.hexdigest()}
    return list(buckets.values()),quality
