"""Mature execution labels with original features; never infer missing context."""
from dataclasses import dataclass
from datetime import datetime,UTC,timedelta
from decimal import Decimal
from math import isfinite
import re

from cryptoforge.model_training import TrainingExample,FEATURE_VERSION

TARGET_VERSION='spot-long-real-execution-net-v1'


def _time(value):return datetime.fromisoformat(str(value).replace('Z','+00:00'))


def _order(reason):
    match=re.search(r'\border=([^\s]+)',str(reason or ''))
    return match.group(1) if match else None


def original_input_contract(features):
    keys=('model_feature_calculation_contract','model_feature_lookback_candles','model_input_timeframe')
    if not any(key in features for key in keys):return None
    width=features.get('model_feature_lookback_candles');state=features.get('model_input_candle_state')
    if (features.get('feature_version')!=FEATURE_VERSION or features.get('model_feature_calculation_contract')!='bounded-window-candle-v1'
        or features.get('model_input_timeframe')!='5m' or type(width) is not int or not 36<=width<=1000
        or state not in {'legacy_asof_snapshot','closed_only'}):
        raise ValueError('invalid_original_input_contract')
    return {'feature_version':features['feature_version'],'timeframe':'5m','input_candle_state':state,
            'calculation_contract':'bounded-window-candle-v1','lookback_candles':width}


def build_live_experiences(trades,decisions,*,observed_at: datetime,truncated=False,
                           accounting_quality_verified=False,source_as_of: datetime | None=None):
    if observed_at.tzinfo is None:raise ValueError('timezone-aware observed_at required')
    cutoff=source_as_of or observed_at
    if cutoff.tzinfo is None or cutoff>observed_at:raise ValueError('source cutoff must be known by observation time')
    if not accounting_quality_verified:
        return {'target_version':TARGET_VERSION,'examples':[],'excluded':[{'reason':'unverified_accounting_snapshot'}],
                'accounting_quality_verified':False,'live_eligible':False}
    if truncated:return {'target_version':TARGET_VERSION,'examples':[],'excluded':[{'reason':'truncated_snapshot'}]}
    contexts={}
    for decision in decisions:
        if decision.get('decision')!='approve_entry':continue
        result=((decision.get('features') or {}).get('order') or {}).get('result') or {}
        order=result.get('orderId') if isinstance(result,dict) else None
        if order:contexts[(decision['pair'],str(order))]=decision
    groups={};excluded=[];seen=set()
    for row in trades:
        identity=str(row.get('idempotency_key') or '')
        if not identity.startswith('bybit:spot:fifo:') or row.get('mode')!='live':continue
        if identity in seen:raise ValueError('duplicate execution row')
        seen.add(identity)
        if _time(row['opened_at'])>cutoff:continue
        order=_order(row.get('entry_reason'))
        if not order:continue
        groups.setdefault((row['pair'],order),[]).append(row)
    examples=[]
    for (pair,order),rows in groups.items():
        reason=None
        remainders=[row for row in rows if str(row['idempotency_key']).endswith(':remaining')]
        closed=[row for row in rows if row['status']=='closed' and _time(row['closed_at'])<=cutoff]
        future_closes=any(row['status']=='closed' and _time(row['closed_at'])>cutoff for row in rows)
        if future_closes:
            reason='execution_not_mature_at_snapshot'
        elif not remainders or any(row['status']!='cancelled' or Decimal(str(row['amount']))!=0 for row in remainders):
            reason='position_not_fully_closed'
        elif not closed:
            reason='no_closed_execution'
        elif any('origin=cryptoforge' not in str(row.get('entry_reason')) or 'origin=cryptoforge' not in str(row.get('exit_reason')) for row in closed):
            reason='external_entry_or_exit_not_bot_training_target'
        elif any(row.get('realized_pnl') is None or row.get('fee_amount') is None for row in closed):
            reason='unknown_net_pnl_or_fees'
        context=contexts.get((pair,order))
        features=(context or {}).get('features') or {}
        if reason is None and (not context or features.get('feature_capture_status')!='complete' or features.get('feature_version')!=FEATURE_VERSION):
            reason='missing_original_feature_context'
        if reason is None and not features.get('feature_observed_at'):
            reason='feature_observation_time_unknown'
        if reason is None:
            feature_time=_time(features['feature_observed_at']);entry_time=min(_time(row['opened_at']) for row in closed)
            if feature_time>entry_time:reason='features_not_observed_before_execution'
        if reason is not None:
            excluded.append({'pair':pair,'entry_order':order,'reason':reason});continue
        values=tuple(float(x) for x in features.get('model_feature_values',[]))
        if len(values)!=7 or not all(isfinite(x) for x in values):
            excluded.append({'pair':pair,'entry_order':order,'reason':'invalid_feature_vector'});continue
        try:input_contract=original_input_contract(features)
        except ValueError as exc:
            excluded.append({'pair':pair,'entry_order':order,'reason':str(exc)});continue
        cost=sum(Decimal(str(row['stake_amount'])) for row in closed)
        pnl=sum(Decimal(str(row['realized_pnl'])) for row in closed)
        if not cost.is_finite() or cost<=0 or not pnl.is_finite():
            excluded.append({'pair':pair,'entry_order':order,'reason':'invalid_cost_or_pnl'});continue
        example=TrainingExample(pair,feature_time,values,int(pnl>0),0,float(pnl/cost),observed_at)
        examples.append({'entry_order':order,'example':example,'net_pnl':str(pnl),'cost':str(cost),
                         **({'feature_input_contract':input_contract} if input_contract is not None else {}),
                         'target_version':TARGET_VERSION,'label_available_at':observed_at.isoformat(),
                         'input_candle_state':features.get('model_input_candle_state','unknown'),
                         'closed_at':max(row['closed_at'] for row in closed),
                         'earliest_close_at':min(_time(row['closed_at']) for row in closed).isoformat(),
                         'source_segments':len(closed)})
    return {'target_version':TARGET_VERSION,'examples':examples,'excluded':excluded,
            'snapshot_observed_at':observed_at.isoformat(),'source_as_of':cutoff.isoformat(),
            'accounting_quality_verified':True,'live_eligible':False}


def bind_examples_to_audit(result: dict, audit: dict) -> dict:
    """Keep only closing evidence and original features in the verified audit.

    A fresh health flag cannot certify different rows fetched after a correction.
    This also makes the audit's bounded lookback explicit for training labels.
    """
    evidence={}
    for outcome in audit.get('outcomes',[]):
        for entry in outcome['entries']:
            key=(outcome['pair'],entry['entry_order'])
            bucket=evidence.setdefault(key,{'cost':Decimal(0),'pnl':Decimal(0),'segments':0,
                                            'features':set(),'latest_close':None})
            bucket['cost']+=Decimal(str(entry['cost']));bucket['pnl']+=Decimal(str(entry['net_pnl']))
            bucket['segments']+=1
            closed=_time(entry.get('closed_at',outcome['closed_at']))
            bucket['latest_close']=max(bucket['latest_close'],closed) if bucket['latest_close'] else closed
            features=entry.get('entry_features') or {}
            if features.get('feature_capture_status')=='complete' and features.get('feature_observed_at'):
                bucket['features'].add((_time(features['feature_observed_at']),
                                       tuple(float(v) for v in features.get('model_feature_values',[])),
                                       features.get('model_input_candle_state','unknown')))
    kept=[];mismatches=0
    for row in result['examples']:
        example=row['example'];key=(example.pair,row['entry_order']);proof=evidence.get(key)
        if audit.get('source_lookback_days') and time_outside_audit(row,audit):
            result['excluded'].append({'pair':example.pair,'entry_order':row['entry_order'],
                                      'reason':'closing_history_outside_verified_audit_window'})
            continue
        cost=Decimal(row.get('closed_cost',row.get('cost')))
        pnl=Decimal(row.get('closed_net_pnl',row.get('net_pnl')))
        if (not proof or proof['cost']!=cost or proof['pnl']!=pnl
            or proof['segments']!=row['source_segments'] or proof['latest_close']!=_time(row['closed_at'])
            or (example.open_time,tuple(example.features),row.get('input_candle_state','unknown')) not in proof['features']):
            mismatches+=1
            result['excluded'].append({'pair':example.pair,'entry_order':row['entry_order'],
                                      'reason':'execution_or_features_differ_from_verified_audit'})
            continue
        kept.append(row)
    result['examples']=kept
    result['source_binding_mismatches']=mismatches
    result['source_binding_verified']=mismatches==0 and result.get('accounting_quality_verified') is True
    result['source_binding']='closed_buy_evidence_and_features_match_verified_audit'
    return result


def time_outside_audit(row,audit):
    since=_time(audit['as_of'])-timedelta(days=audit['source_lookback_days'])
    return _time(row.get('earliest_close_at',row['closed_at']))<since
