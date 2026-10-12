"""Capture complete execution outcomes; no automatic live model promotion."""
from dataclasses import asdict
from datetime import datetime,UTC,timedelta
import json
from pathlib import Path
from collections import Counter

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.live_feedback import LiveFeedbackReader
from cryptoforge.live_experience import build_live_experiences,bind_examples_to_audit
from cryptoforge.supabase_market import SupabaseRestClient


def main():
    reader=LiveFeedbackReader(SupabaseRestClient.from_env(timeout_seconds=25))
    trades,truncated=reader._rows('trades',{'mode':'eq.live','order':'opened_at.asc,id.asc','select':'idempotency_key,pair,mode,status,opened_at,closed_at,amount,stake_amount,realized_pnl,fee_amount,entry_reason,exit_reason'})
    decisions,context_truncated=reader._rows('trade_decisions',{'mode':'eq.live','decision':'eq.approve_entry',
         'order':'decided_at.asc,id.asc','select':'pair,decision,decided_at,features,reasons'})
    observed=datetime.now(UTC)
    # The preceding audit independently reconciles fills/conversions to wallet.
    # Only its bounded snapshot can certify the rows collected here.
    audit_path=Path('.local/state/live-feedback.json')
    quality=False;cutoff=observed;audit={}
    if audit_path.exists():
        try:
            audit=json.loads(audit_path.read_bytes())
            cutoff=datetime.fromisoformat(audit['as_of'].replace('Z','+00:00'))
            quality=(timedelta(0)<=observed-cutoff<=timedelta(minutes=5)
                     and audit.get('accounting_quality_verified') is True
                     and (audit.get('inventory_audit') or {}).get('consistent') is True
                     and not audit.get('trades_truncated') and not audit.get('decisions_truncated'))
        except (ValueError,KeyError,TypeError):quality=False;cutoff=observed
    result=build_live_experiences(trades,decisions,observed_at=observed,
        truncated=truncated or context_truncated,accounting_quality_verified=quality,
        source_as_of=cutoff if quality else observed)
    result=bind_examples_to_audit(result,audit)
    result['examples']=[{**row,'example':asdict(row['example'])} for row in result['examples']]
    output=Path('.local/state/live-experience-dataset.json');write_json_report(output,result,default=str)
    print(json.dumps({'eligible_examples':len(result['examples']),'excluded':dict(Counter(row['reason'] for row in result['excluded'])),
                      'target_version':result['target_version'],'promotion_allowed':False}))


if __name__=='__main__':main()
