"""Collect conservative experimental dust labels; no orders or model promotion."""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
from collections import Counter

from cryptoforge.cash_recovery import build_cash_recovery
from cryptoforge.experience_memory import remember_experiences,available_experiences
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.live_feedback import LiveFeedbackReader
from cryptoforge.live_experience import bind_examples_to_audit,_order
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.dust_observations import observe_pairs
from cryptoforge.supabase_market import SupabaseRestClient


def main():
    audit=json.loads(Path('.local/state/live-feedback.json').read_bytes())
    cutoff=datetime.fromisoformat(audit['as_of'].replace('Z','+00:00'))
    now=datetime.now(UTC)
    quality=(timedelta(0)<=now-cutoff<=timedelta(minutes=5)
             and audit.get('accounting_quality_verified') is True
             and (audit.get('inventory_audit') or {}).get('consistent') is True)
    reader=LiveFeedbackReader(SupabaseRestClient.from_env(timeout_seconds=20))
    trades,truncated=reader._rows('trades',{'mode':'eq.live','order':'opened_at.asc,id.asc',
        'select':'idempotency_key,pair,mode,status,opened_at,closed_at,amount,stake_amount,realized_pnl,fee_amount,entry_reason,exit_reason'})
    decisions,context_truncated=reader._rows('trade_decisions',{'mode':'eq.live','decision':'eq.approve_entry',
        'order':'decided_at.asc,id.asc','select':'pair,decision,decided_at,features,reasons'})
    covered_keys={(outcome['pair'],entry['entry_order']) for outcome in audit.get('outcomes',[])
                  for entry in outcome['entries']}
    # Expired old campaigns stay in as-of memory; do not query instruments for
    # rows that the current bounded audit cannot certify.
    all_trades=trades
    trades=[row for row in trades if (row['pair'],_order(row.get('entry_reason'))) in covered_keys]
    preliminary=build_cash_recovery(trades,decisions,{},observed_at=now,source_as_of=cutoff,
        accounting_quality_verified=quality,truncated=truncated or context_truncated)
    pairs=sorted({row['pair'] for row in preliminary['excluded']
                  if row['reason']=='instrument_observation_unavailable'})
    observations={};errors={};client=BybitPublicClient(timeout=5,max_retries=0)
    if quality:observations,errors=observe_pairs(client,pairs)
    seen=datetime.now(UTC)
    quality=quality and timedelta(0)<=seen-cutoff<=timedelta(minutes=5)
    result=build_cash_recovery(trades,decisions,observations,observed_at=seen,source_as_of=cutoff,
        accounting_quality_verified=quality,truncated=truncated or context_truncated or
        audit.get('trades_truncated',False) or audit.get('decisions_truncated',False))
    result=bind_examples_to_audit(result,audit)
    from cryptoforge.cash_collection_coverage import collection_coverage
    result['collection_coverage']=collection_coverage(all_trades,covered_keys,result,source_as_of=cutoff)
    result['examples']=[{**row,'example':asdict(row['example'])} for row in result['examples']]
    result['observation_errors']=errors
    result['observation_scope']={'pairs':pairs,'eligible_pair_count':len(pairs),'observed_pair_count':len(observations),
        'maximum_public_requests':2,'request_timeout_seconds':5,'alphabetical_cap_removed':True,
        'missing_observations_excluded':True,'exchange_wide_sampling_claims_allowed':False}
    memory=Path('.local/state/live-experience-memory.sqlite')
    result['memory']=remember_experiences(result,memory,observed_at=seen)
    # Output this snapshot only; do not resurrect no-longer-eligible old rows.
    known={(r['pair'],r['entry_order']):r for r in available_experiences(memory,target=result['target_version'],as_of=seen)}
    result['examples']=[known[(r['pair'],r['entry_order'])] for r in result['examples']]
    output=Path('.local/state/cash-recovery-dataset.json');write_json_report(output,result,default=str)
    print(json.dumps({'examples':len(result['examples']),'excluded':dict(Counter(r['reason'] for r in result['excluded'])),
                     'memory':result['memory'],'target':result['target_version'],'promotion_allowed':False}))


if __name__=='__main__':main()
