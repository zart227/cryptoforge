"""Conservative conditional simulation gates; no real model promotion."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal
import random

from cryptoforge.live_learning_protocol import time

D=Decimal


def validate_acceptance_policy(policy):
    if policy.get('status') not in {'draft_not_preregistered','frozen'} or policy.get('allow_real_promotion') is not False:
        raise ValueError('research-only acceptance policy required')
    for key in ('minimum_buys','minimum_entry_days','minimum_pairs','maximum_mark_gap_seconds',
                'maximum_endpoint_gap_seconds','bootstrap_repetitions','bootstrap_block_days'):
        if type(policy[key]) is not int or policy[key]<1:raise ValueError('positive integer acceptance bounds required')
    if policy['bootstrap_repetitions']<100 or policy['bootstrap_block_days']>policy['minimum_entry_days']:
        raise ValueError('invalid bootstrap design')
    for key in ('minimum_net_return','minimum_stress_net_return','minimum_block_bootstrap_lower_bound'):
        if not D(policy[key]).is_finite() or D(policy[key])<0:raise ValueError('nonnegative finite return gates required')
    for key in ('maximum_drawdown','maximum_pair_fraction','maximum_entry_day_fraction','minimum_mark_coverage'):
        value=D(policy[key])
        if not value.is_finite() or not 0<value<=1:raise ValueError('invalid acceptance fraction')
    if (not D(policy['minimum_profit_factor']).is_finite() or D(policy['minimum_profit_factor'])<1 or
        not D(policy['stress_cost_multiplier']).is_finite() or D(policy['stress_cost_multiplier'])<1 or
        not 0<D(policy['bootstrap_lower_quantile'])<D('.5')):raise ValueError('invalid profit/stress/confidence gate')
    if policy.get('require_paired_baseline') is not True or policy.get('require_all_sources_accounted') is not True:
        raise ValueError('paired control and complete source accounting required')


def _stats(results,start,end):
    if any(not start<=time(fill['filled_at'])<=end for fill in results.get('fills',[])):
        raise ValueError('execution outside paper window cannot repair its result')
    if any(row.get('closed_at') and time(row['closed_at'])>end for row in results['campaigns']):
        raise ValueError('late closing cannot resolve an expired paper window')
    capital=D(results['capital']);marks=[m for m in results['equity_marks'] if start<=time(m['observed_at'])<=end]
    if not capital.is_finite() or capital<=0:raise ValueError('invalid evaluation capital')
    all_known=bool(marks) and all(m.get('equity') is not None for m in marks)
    for m in marks:
        if m.get('equity') is not None and (not D(m['equity']).is_finite() or D(m['equity'])<0):
            raise ValueError('invalid simulated equity')
    known=[m for m in marks if m.get('equity') is not None]
    ordered=sorted(known,key=lambda m:time(m['observed_at']))
    peak=capital;drawdown=D(0)
    for m in ordered:
        equity=D(m['equity']);peak=max(peak,equity);drawdown=max(drawdown,(peak-equity)/peak)
    rows=results['campaigns']
    if any(not start<=time(row['entry_at'])<end for row in rows):
        raise ValueError('paper acquisition lies outside frozen evaluation window')
    counts=Counter(r['pair'] for r in rows)
    dates=Counter(time(r['entry_at']).date().isoformat() for r in rows)
    cap=D(results['policy']['config']['stake'])*D(results['policy']['config']['max_dust_basis_fraction'])
    unresolved=[r['paper_buy_intent'] for r in rows if not r['has_exit'] or D(r['remaining_basis'])>cap]
    pnls=[D(r['cash_recovery_net_dust_zero']) for r in rows]
    if not all(value.is_finite() for value in pnls):raise ValueError('invalid paper campaign outcome')
    wins=sum((v for v in pnls if v>0),D(0));losses=-sum((v for v in pnls if v<0),D(0))
    profit_factor=wins/losses if losses else None
    stamps=sorted(set(time(m['observed_at']) for m in marks))
    gaps=[(b-a).total_seconds() for a,b in zip(stamps,stamps[1:])]
    quality=results.get('mark_quality') or {}
    raw_count=quality.get('raw_mark_count',len(marks));known_count=quality.get('known_mark_count',len(known))
    if quality:
        if ((quality.get('first_mark_at') and time(quality['first_mark_at'])<start) or
            (quality.get('last_mark_at') and time(quality['last_mark_at'])>end)):
            raise ValueError('risk summary contains marks outside the paper window')
        all_known=quality['all_marks_known'];drawdown=D(quality['max_drawdown'])
    first=time(quality['first_mark_at']) if quality.get('first_mark_at') else (stamps[0] if stamps else None)
    last=time(quality['last_mark_at']) if quality.get('last_mark_at') else (stamps[-1] if stamps else None)
    first_gap=(first-start).total_seconds() if first else None
    last_gap=(end-last).total_seconds() if last else None
    final=ordered[-1] if ordered else None
    daily={}
    for m in ordered:daily[time(m['observed_at']).date().isoformat()]=D(m['equity'])/capital
    return {'buy_orders':len(rows),'entry_days':len(dates),'pairs':len(counts),
        'net_return':str((D(final['equity'])-capital)/capital) if final else None,
        'max_drawdown':str(drawdown),'profit_factor':str(profit_factor) if profit_factor is not None else None,
        'positive_sum':str(wins),'loss_sum':str(losses),'unresolved_buy_intents':unresolved,
        'all_marks_known':all_known,'known_mark_fraction':str(D(known_count)/raw_count) if raw_count else '0',
        'max_mark_gap_seconds':quality.get('max_gap_seconds',max(gaps,default=0)),'first_mark_gap_seconds':first_gap,'last_mark_gap_seconds':last_gap,
        'pair_concentration':str(D(max(counts.values(),default=0))/len(rows)) if rows else '0',
        'day_concentration':str(D(max(dates.values(),default=0))/len(rows)) if rows else '0',
        '_daily':daily}


def _bootstrap_difference(candidate,baseline,policy):
    if set(candidate)!=set(baseline):return None
    days=sorted(candidate);increments=[];prev_c=prev_b=D(1)
    for day in days:
        increments.append(float((candidate[day]-prev_c)-(baseline[day]-prev_b)))
        prev_c=candidate[day];prev_b=baseline[day]
    if len(days)<policy['minimum_entry_days']:return None
    length=policy['bootstrap_block_days'];rng=random.Random(policy['bootstrap_seed']);samples=[]
    for _ in range(policy['bootstrap_repetitions']):
        selected=[]
        while len(selected)<len(increments):
            origin=rng.randrange(len(increments))
            selected.extend(increments[(origin+j)%len(increments)] for j in range(length))
        samples.append(sum(selected[:len(increments)])/len(increments))
    samples.sort();index=int(float(policy['bootstrap_lower_quantile'])*(len(samples)-1))
    return str(samples[index])


def _execution_incomplete(results):
    # Expected cash/precision/risk rejections remain valid portfolio outcomes.
    # Expiration means the opportunity was lost to latency, not evaluated.
    return (bool(results.get('worker_quality_errors')) or bool(results.get('worker_quality_error_count',0)) or
            any(row['status']=='pending' or
                (row['status']=='rejected' and row.get('reason') in {'expired_signal','source_prediction_expired'})
                for row in results.get('intents',[])))


def evaluate_paper(candidate,baseline,stress,policy,*,window_start,window_end,as_of,preregistered=False):
    validate_acceptance_policy(policy)
    result={'policy_version':policy['policy_version'],'as_of':as_of.isoformat(),
            'paper_evidence_pass':False,'live_promotion_allowed':False,'live_profitability_established':False,
            'scope':policy['scope'],'failures':[]}
    if as_of<window_end:return {**result,'status':'sealed_until_paper_end','performance_hidden':True}
    failures=result['failures']
    if not preregistered or policy['status']!='frozen':failures.append('acceptance_policy_not_observed_before_paper')
    if not candidate or candidate.get('status')=='paper_not_started':
        return {**result,'status':'paper_not_started','performance_hidden':False,'failures':failures+['missing_candidate_execution']}
    stats=_stats(candidate,window_start,window_end);result['candidate']={k:v for k,v in stats.items() if k!='_daily'}
    for key,minimum in [('buy_orders','minimum_buys'),('entry_days','minimum_entry_days'),('pairs','minimum_pairs')]:
        if stats[key]<policy[minimum]:failures.append('insufficient_'+key)
    if stats['net_return'] is None or D(stats['net_return'])<=D(policy['minimum_net_return']):failures.append('nonpositive_net_return')
    if stats['profit_factor'] is None:
        if D(stats['positive_sum'])<=0:failures.append('no_positive_closed_evidence')
    elif D(stats['profit_factor'])<D(policy['minimum_profit_factor']):failures.append('profit_factor_below_minimum')
    if D(stats['max_drawdown'])>D(policy['maximum_drawdown']):failures.append('drawdown_exceeds_limit')
    if stats['unresolved_buy_intents']:failures.append('material_or_unclosed_positions')
    for key,bound in [('pair_concentration','maximum_pair_fraction'),('day_concentration','maximum_entry_day_fraction')]:
        if D(stats[key])>D(policy[bound]):failures.append(key+'_exceeds_limit')
    if (not stats['all_marks_known'] or D(stats['known_mark_fraction'])<D(policy['minimum_mark_coverage']) or
        stats['max_mark_gap_seconds']>policy['maximum_mark_gap_seconds'] or
        any(v is None or v>policy['maximum_endpoint_gap_seconds'] for v in (stats['first_mark_gap_seconds'],stats['last_mark_gap_seconds']))):
        failures.append('incomplete_equity_observation')
    if policy.get('require_all_sources_accounted') and any(row['status'] in {'source_prediction_expired','unverified_prediction_observation','outside_window_or_future'} for row in candidate.get('seen_predictions',[])):
        failures.append('source_opportunities_missing_or_expired')
    if _execution_incomplete(candidate):
        failures.append('worker_errors_or_pending_intents')
    if not baseline:failures.append('paired_baseline_missing')
    else:
        bstats=_stats(baseline,window_start,window_end)
        if candidate.get('candidate_artifact_sha256')!=baseline.get('candidate_artifact_sha256'):
            failures.append('baseline_candidate_identity_mismatch')
        if candidate.get('worker_policy') and baseline.get('worker_policy') and candidate['worker_policy']['exits']!=baseline['worker_policy']['exits']:
            failures.append('baseline_exit_rules_not_equal')
        if candidate['capital']!=baseline['capital'] or candidate['policy']['config']!=baseline['policy']['config']:
            failures.append('baseline_execution_assumptions_not_equal')
        c_sources={row['id'] for row in candidate.get('seen_predictions',[])}
        b_sources={row['id'] for row in baseline.get('seen_predictions',[])}
        if not c_sources or c_sources!=b_sources:failures.append('baseline_source_opportunities_not_identical')
        if any(row['status'] in {'source_prediction_expired','unverified_prediction_observation','outside_window_or_future'} for row in baseline.get('seen_predictions',[])):
            failures.append('baseline_source_opportunities_missing_or_expired')
        if _execution_incomplete(baseline):
            failures.append('baseline_quality_errors')
        if any(v is None or v>policy['maximum_endpoint_gap_seconds'] for v in (bstats['first_mark_gap_seconds'],bstats['last_mark_gap_seconds'])) or bstats['max_mark_gap_seconds']>policy['maximum_mark_gap_seconds']:
            failures.append('baseline_incomplete_equity_observation')
        if not bstats['all_marks_known'] or bstats['unresolved_buy_intents']:failures.append('baseline_unresolved_or_unknown')
        lower=_bootstrap_difference(stats['_daily'],bstats['_daily'],policy)
        result['paired_day_bootstrap_lower_bound']=lower
        if lower is None or D(lower)<=D(policy['minimum_block_bootstrap_lower_bound']):failures.append('no_paired_positive_bootstrap_bound')
    if not stress:failures.append('prospective_stress_scenario_missing')
    else:
        sstats=_stats(stress,window_start,window_end);result['stress_net_return']=sstats['net_return']
        multiplier=D(policy['stress_cost_multiplier'])
        if any(D(stress['policy']['config'][key])!=D(candidate['policy']['config'][key])*multiplier for key in ('entry_fee','exit_fee','slippage')):
            failures.append('stress_costs_not_preregistered_multiplier')
        if sstats['net_return'] is None or D(sstats['net_return'])<=D(policy['minimum_stress_net_return']):failures.append('stress_not_profitable')
        if candidate['capital']!=stress['capital'] or candidate.get('candidate_artifact_sha256')!=stress.get('candidate_artifact_sha256'):
            failures.append('stress_candidate_or_capital_mismatch')
        if {row['id'] for row in candidate.get('seen_predictions',[])}!={row['id'] for row in stress.get('seen_predictions',[])}:
            failures.append('stress_source_opportunities_not_identical')
        ignored={'entry_fee','exit_fee','slippage','cost_assumption_id'}
        if {k:v for k,v in candidate['policy']['config'].items() if k not in ignored}!={k:v for k,v in stress['policy']['config'].items() if k not in ignored}:
            failures.append('stress_execution_assumptions_not_equal')
        if candidate.get('worker_policy') and stress.get('worker_policy') and candidate['worker_policy']['exits']!=stress['worker_policy']['exits']:
            failures.append('stress_exit_rules_not_equal')
        if any(row['status'] in {'source_prediction_expired','unverified_prediction_observation','outside_window_or_future'} for row in stress.get('seen_predictions',[])):
            failures.append('stress_source_opportunities_missing_or_expired')
        if _execution_incomplete(stress):
            failures.append('stress_quality_errors')
        if any(v is None or v>policy['maximum_endpoint_gap_seconds'] for v in (sstats['first_mark_gap_seconds'],sstats['last_mark_gap_seconds'])) or sstats['max_mark_gap_seconds']>policy['maximum_mark_gap_seconds']:
            failures.append('stress_incomplete_equity_observation')
        if not sstats['all_marks_known'] or sstats['unresolved_buy_intents']:failures.append('stress_unresolved_or_unknown')
    result.update(status='conditional_simulation_evaluated',performance_hidden=False,paper_evidence_pass=not failures)
    return result


class AcceptanceRegistry:
    """One actual-clock criterion freeze per protocol, independent of candidates."""
    def __init__(self,path,*,clock=None):
        from datetime import UTC,datetime
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))

    def freeze(self,raw,*,protocol_sha):
        import hashlib,json,sqlite3
        now=self.clock()
        if now.tzinfo is None:raise ValueError('timezone-aware criterion freeze required')
        policy=json.loads(raw);validate_acceptance_policy(policy)
        if policy['status']!='frozen' or policy['allow_real_promotion'] is not False:
            raise ValueError('conditional simulation criteria only')
        self.path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path)
        try:
            existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if existing-{'acceptance_freezes'}:raise ValueError('acceptance registry requires an isolated database')
            db.execute('CREATE TABLE IF NOT EXISTS acceptance_freezes (protocol_sha TEXT PRIMARY KEY,policy_sha TEXT,observed_at TEXT,payload TEXT) WITHOUT ROWID')
            digest=hashlib.sha256(raw).hexdigest()
            with db:db.execute('INSERT INTO acceptance_freezes VALUES (?,?,?,?)',(protocol_sha,digest,now.isoformat(),raw.decode()))
            self.path.chmod(0o600)
        finally:db.close()
        return {'protocol_sha256':protocol_sha,'policy_sha256':digest,'observed_at':now.isoformat()}

    def verify(self,raw,receipt):
        import hashlib,sqlite3
        if not self.path.exists():raise ValueError('no observed acceptance criterion registration')
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:row=db.execute('SELECT policy_sha,observed_at,payload FROM acceptance_freezes WHERE protocol_sha=?',(receipt['protocol_sha256'],)).fetchone()
        finally:db.close()
        if row!=(receipt['policy_sha256'],receipt['observed_at'],raw.decode()) or hashlib.sha256(raw).hexdigest()!=receipt['policy_sha256']:
            raise ValueError('acceptance policy differs from its actual observed freeze')


    def registered(self,protocol_sha):
        """Recover exact committed bytes and receipt without creating a database."""
        import hashlib,sqlite3
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            row=db.execute('SELECT policy_sha,observed_at,payload FROM acceptance_freezes WHERE protocol_sha=?',(protocol_sha,)).fetchone()
        finally:db.close()
        if row is None:return None
        raw=row[2].encode()
        if hashlib.sha256(raw).hexdigest()!=row[0]:raise ValueError('corrupt registered acceptance policy')
        receipt={'protocol_sha256':protocol_sha,'policy_sha256':row[0],'observed_at':row[1]}
        self.verify(raw,receipt)
        return raw,receipt
