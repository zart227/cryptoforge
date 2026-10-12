"""Read-only feedback from execution-backed net PnL, with attribution limits."""
from collections import defaultdict
from datetime import datetime,UTC,timedelta
from decimal import Decimal
import re
from statistics import median
from zoneinfo import ZoneInfo

D=Decimal


def _dt(value):
    return datetime.fromisoformat(str(value).replace('Z','+00:00'))


def _order(reason):
    match=re.search(r'\border=([^\s]+)',str(reason or ''))
    return match.group(1) if match else None


def _reasons(decision):
    result={}
    for reason in (decision or {}).get('reasons',[]):
        if '=' in reason:
            key,value=reason.split('=',1);result[key]=value
    return result


def _decision_order(decision):
    order=(decision.get('features') or {}).get('order') or {}
    result=order.get('result') or {}
    return str(result.get('orderId') or '') if isinstance(result,dict) else ''


def analyze_feedback(trades,decisions,*,as_of=None):
    as_of=as_of or datetime.now(UTC)
    if as_of.tzinfo is None:raise ValueError('timezone-aware feedback cutoff required')
    contexts={};groups=defaultdict(list);excluded=[];seen=set()
    for decision in decisions:
        order=_decision_order(decision)
        if order and _dt(decision['decided_at'])<=as_of:
            contexts[(decision['pair'],order,decision['decision'])]=decision
    for trade in trades:
        if trade.get('status')!='closed' or trade.get('mode')!='live':continue
        if _dt(trade['closed_at'])>as_of:continue
        # Reconciled rows are execution-to-lot segments, not independent trades.
        identity=trade.get('idempotency_key') or trade.get('external_trade_id') or trade.get('id')
        if identity is None:
            excluded.append({'pair':trade['pair'],'reason':'missing_segment_identity'});continue
        if identity in seen:
            raise ValueError('duplicate trade segment would double count PnL')
        seen.add(identity)
        order=_order(trade.get('exit_reason'))
        if not order or not str(identity).startswith('bybit:spot:fifo:'):
            excluded.append({'pair':trade['pair'],'reason':'not_execution_backed_or_missing_order'});continue
        groups[(trade['pair'],order)].append(trade)
    outcomes=[]
    for (pair,order),segments in groups.items():
        valid=all(s.get('realized_pnl') is not None and s.get('fee_amount') is not None and D(str(s.get('stake_amount',0)))>0 for s in segments)
        if not valid:
            excluded.append({'pair':pair,'reason':'missing_cost_pnl_or_fees'});continue
        cost=sum((D(str(s['stake_amount'])) for s in segments),D(0))
        pnl=sum((D(str(s['realized_pnl'])) for s in segments),D(0))
        fees=sum((D(str(s['fee_amount'])) for s in segments),D(0))
        weighted_seconds=sum(D(str((_dt(s['closed_at'])-_dt(s['opened_at'])).total_seconds()))*D(str(s['stake_amount'])) for s in segments)/cost
        if not all(value.is_finite() for value in (cost,pnl,fees)):
            excluded.append({'pair':pair,'reason':'nonfinite_accounting_values'});continue
        exit_decision=contexts.get((pair,order,'approve_exit'))
        entries=[]
        for segment in segments:
            entry_order=_order(segment.get('entry_reason'))
            context=contexts.get((pair,entry_order,'approve_entry'))
            entries.append({'cost':str(segment['stake_amount']),'net_pnl':str(segment['realized_pnl']),
                            'entry_order':entry_order,'context_match':'exact_order' if context else 'missing',
                            'entry_reason_values':_reasons(context),'entry_features':(context or {}).get('features') or {},
                            'entry_at':segment['opened_at'],'closed_at':segment['closed_at'],
                            'source_idempotency_key':segment.get('idempotency_key'),
                            'entry_execution':str(segment.get('entry_reason') or ''),
                            'maturity':'unknown_partial_close_possible'})
        risk=_reasons(exit_decision)
        controlled=all('origin=cryptoforge' in str(s.get('exit_reason') or '') for s in segments)
        outcomes.append({'pair':pair,'exit_order':order,'exit_controlled_by_bot':controlled,
            'exit_kind':'conversion' if order.startswith('conversion:') else 'spot_order','closed_at':max(s['closed_at'] for s in segments),
            'segments':len(segments),'cost':str(cost),'net_pnl':str(pnl),'net_return':str(pnl/cost),
            'net_return_pct':str(100*pnl/cost),'reported_fees':str(fees),'fee_drag_fraction':str(fees/cost),
            'gross_before_reported_fees_estimate':str(pnl+fees),
            'weighted_hold_seconds':float(weighted_seconds),'exit_context_match':'exact_order' if exit_decision else 'missing',
            'exit_reason_values':risk,'entries':entries,'profitable':pnl>0,
            'fee_erased_gross_gain':pnl<0 and pnl+fees>=0,'short_hold':weighted_seconds<=D(300),
            'reentry_exit_conflict_observed':any(e['entry_features'].get('entry_exit_conflict') is True for e in entries),
            'effective_information_end':max(s['closed_at'] for s in segments)})
    outcomes.sort(key=lambda row:row['closed_at'],reverse=True)
    today=as_of.astimezone(ZoneInfo('Europe/Moscow')).date()
    daily=[r for r in outcomes if _dt(r['closed_at']).astimezone(ZoneInfo('Europe/Moscow')).date()==today]
    def summary(rows):
        fees=sum((D(r['reported_fees']) for r in rows),D(0));pnl=sum((D(r['net_pnl']) for r in rows),D(0))
        return {'closed_exit_orders':len(rows),'profitable':sum(r['profitable'] for r in rows),
                'losing':sum(D(r['net_pnl'])<0 for r in rows),'net_pnl_usdt':str(pnl),'fees_usdt':str(fees),
                'short_hold_orders':sum(r['short_hold'] for r in rows),
                'fee_erased_gross_gains':sum(r['fee_erased_gross_gain'] for r in rows),
                'median_observed_round_trip_fee_fraction':str(median(D(r['fee_drag_fraction']) for r in rows)) if rows else None}
    # Attribute only exact-order entry portions; unmatched cost remains explicit.
    cohorts=defaultdict(lambda:defaultdict(lambda:{"cost":D(0),"pnl":D(0)}))
    matched_cost=total_cost=D(0)
    for outcome in outcomes:
        total_cost+=D(outcome["cost"])
        for entry in outcome["entries"]:
            if entry["context_match"]!="exact_order":continue
            cost=D(entry["cost"]);pnl=D(entry["net_pnl"]);matched_cost+=cost
            reasons=entry["entry_reason_values"]
            labels=[name for name in ("emerging_momentum","intraday_reversion","breakout","pullback","bounce") if reasons.get(name)=="True"]
            cohort=("+".join(labels) or "unclassified_logged_entry")+"|"+outcome['exit_kind']
            bucket=cohorts[cohort][outcome["exit_order"]]
            bucket["cost"]+=cost;bucket["pnl"]+=pnl
    cohort_report=[]
    for name,orders in sorted(cohorts.items()):
        pnl=sum((r["pnl"] for r in orders.values()),D(0));cost=sum((r["cost"] for r in orders.values()),D(0))
        top=sorted((r["pnl"] for r in orders.values()),reverse=True)[:2]
        cohort_report.append({"entry_flags":name,"exact_context_exit_orders":len(orders),
            "attributed_cost":str(cost),"attributed_net_pnl":str(pnl),
            "net_pnl_without_two_largest_outcomes":str(pnl-sum(top,D(0))),
            "sample_status":"diagnostic_only_requires_independent_validation"})
    controlled_daily=[r for r in daily if r['exit_controlled_by_bot'] and r['exit_kind']=='spot_order']
    short=[r for r in controlled_daily if r['short_hold']]
    conflict_orders=[r for r in outcomes if r['exit_controlled_by_bot']
                     and r['exit_kind']=='spot_order' and r['reentry_exit_conflict_observed']]
    conflict_report={**summary(conflict_orders),
                     'pairs':sorted({r['pair'] for r in conflict_orders}),
                     'sample_status':'diagnostic_only_partial_closes_possible'}
    hypotheses=[]
    if conflict_orders:
        hypotheses.append({'kind':'simultaneous_entry_exit_signals',
            'evidence_orders':len(conflict_orders),'net_pnl_usdt':conflict_report['net_pnl_usdt'],
            'action':'paper_compare_entry_conflict_filter_with_unchanged_hard_stops',
            'status':'hypothesis_not_live_rule'})
    if short:
        hypotheses.append({'kind':'entry_exit_horizon_mismatch','evidence_orders':len(short),
            'net_pnl_usdt':str(sum(D(r['net_pnl']) for r in short)),
            'action':'paper_compare_strategy_specific_exits_without_delaying_hard_stops','status':'hypothesis_not_live_rule'})
    if controlled_daily:
        measured=median(D(r['fee_drag_fraction']) for r in controlled_daily)
        if measured>D('0.003'):
            hypotheses.append({'kind':'cost_assumption_underestimates_observed_fees','observed_fee_floor':str(measured),
                'action':'calibrate_candidate_cost_floor_on_prior_completed_trades_plus_slippage','status':'hypothesis_not_live_rule'})
    return {'schema_version':'live-feedback-v1','as_of':as_of.isoformat(),'timezone':'Europe/Moscow',
            'outcomes':outcomes,'large_bot_losses':analyze_large_bot_losses(outcomes),'summary':summary(outcomes),'today':summary(daily),
            'today_bot_exits':summary(controlled_daily),'today_external_exits':summary([r for r in daily if not r['exit_controlled_by_bot']]),'excluded':excluded,
            'entry_conflict_outcomes':conflict_report,'entry_cohorts':cohort_report,'exact_entry_cost_coverage_fraction':str(matched_cost/total_cost) if total_cost else '0',
            'closed_pnl_without_two_largest_outcomes':str(sum((D(r['net_pnl']) for r in outcomes),D(0))-sum(sorted((D(r['net_pnl']) for r in outcomes),reverse=True)[:2],D(0))),
            'hypotheses':hypotheses,'fee_accounting':'net_pnl_already_includes_fees_do_not_subtract_again',
            'sample_limitations':'exit orders can combine multiple FIFO lots; partial closes are not independent outcomes',
            'automatic_live_changes_allowed':False}


def analyze_large_bot_losses(outcomes, *, threshold=D('0.01'), maximum_examples=10):
    """Explain already-net FIFO exit losses without charging fees twice."""
    if not threshold.is_finite() or not 0<threshold<1 or type(maximum_examples) is not int or maximum_examples<1:
        raise ValueError('bounded positive loss diagnostic required')
    rows=[r for r in outcomes if r['exit_controlled_by_bot'] and r['exit_kind']=='spot_order'
          and D(r['net_return'])<=-threshold]
    rows.sort(key=lambda r:D(r['net_return']))
    examples=[]
    for row in rows[:maximum_examples]:
        pnl=D(row['net_pnl']);fees=D(row['reported_fees']);cost=D(row['cost'])
        gross=pnl+fees
        examples.append({'pair':row['pair'],'exit_order':row['exit_order'],'closed_at':row['closed_at'],
            'net_return_pct':str(100*pnl/cost),'reported_fee_drag_pct':str(100*fees/cost),
            'gross_before_reported_fees_estimate_pct':str(100*gross/cost),
            'loss_component':'fees_erased_nonnegative_gross' if gross>=0 else 'negative_gross_and_reported_fees',
            'exit_context_match':row['exit_context_match'],'entry_exit_conflict_observed':row['reentry_exit_conflict_observed']})
    return {'threshold_net_loss_fraction':str(threshold),'closed_bot_exit_orders':len(rows),
        'fee_erased_nonnegative_gross_orders':sum(D(r['net_pnl'])+D(r['reported_fees'])>=0 for r in rows),
        'examples':examples,'examples_truncated':len(rows)>maximum_examples,
        'fees_already_in_net_pnl':True,'partial_fifo_closes_may_overlap':True,
        'causal_failure_reason_established':False,'automatic_live_changes_allowed':False}


class LiveFeedbackReader:
    """Read existing tables only; no trades, notifications or schema changes."""
    def __init__(self,client):self.client=client

    def _rows(self,table,filters):
        import json
        from urllib import parse,request
        result=[]
        for offset in range(0,5000,500):
            query=parse.urlencode({**filters,'limit':'500','offset':str(offset)})
            req=request.Request(self.client.supabase_url.rstrip('/')+'/rest/v1/'+table+'?'+query,
                headers={'apikey':self.client.service_role_key,'authorization':'Bearer '+self.client.service_role_key})
            with request.urlopen(req,timeout=self.client.timeout_seconds) as response:page=json.loads(response.read(),parse_float=D)
            result.extend(page)
            if len(page)<500:return result,False
        return result,True

    def read(self,*,as_of=None,lookback_days=14):
        as_of=as_of or datetime.now(UTC)
        since=as_of-timedelta(days=lookback_days)
        trades,truncated=self._rows('trades',{'status':'eq.closed','mode':'eq.live',
            'and':f'(closed_at.gte.{since.isoformat()},closed_at.lte.{as_of.isoformat()})',
            'order':'closed_at.asc,id.asc','select':'id,idempotency_key,external_trade_id,pair,status,mode,opened_at,closed_at,entry_price,exit_price,amount,stake_amount,fee_amount,realized_pnl,realized_pnl_pct,entry_reason,exit_reason'})
        context_start=min((_dt(t['opened_at']) for t in trades),default=since)
        decisions,context_truncated=self._rows('trade_decisions',{'mode':'eq.live','decision':'in.(approve_entry,approve_exit)',
            'and':f'(decided_at.gte.{context_start.isoformat()},decided_at.lte.{as_of.isoformat()})',
            'order':'decided_at.asc,id.asc','select':'pair,decided_at,decision,reasons,features,strategy_name,strategy_version'})
        report=analyze_feedback(trades,decisions,as_of=as_of)
        health,_=self._rows('bot_health',{'component':'eq.live_trade_journal','select':'status,payload,observed_at'})
        state=health[0] if health else {}
        report['accounting_quality_verified']=(state.get('status')=='ok' and (state.get('payload') or {}).get('accounting_version',0)>=2
                                               and (state.get('payload') or {}).get('inventory_verified') is True)
        report['accounting_quality_status']=state.get('status','unknown')
        report.update(trades_truncated=truncated,decisions_truncated=context_truncated,
                      source_lookback_days=lookback_days)
        return report


def candidate_cost_floor(report,*,minimum_orders=5,slippage_fraction=D('0.001')):
    """Fee calibration uses completed prior executions, not outcome profitability."""
    if report.get('trades_truncated') or not report.get('accounting_quality_verified'):
        return None
    eligible=[row for row in report.get('outcomes',[]) if row.get('exit_controlled_by_bot') and row.get('exit_kind')=='spot_order']
    if len(eligible)<minimum_orders:return None
    rates=[D(row['fee_drag_fraction']) for row in eligible]
    if not rates:return None
    return max(D(0),median(rates))+slippage_fraction
