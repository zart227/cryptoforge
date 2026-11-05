"""Read exact live order decisions for a saved exchange audit; no publication."""
import argparse
import os,shlex,json
from pathlib import Path
from datetime import datetime,UTC
from cryptoforge.supabase_market import SupabaseRestClient
from cryptoforge.live_feedback import LiveFeedbackReader,analyze_feedback
from cryptoforge.atomic_reports import write_json_report
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audit-dir',type=Path,required=True)
args=parser.parse_args()
p=args.audit_dir
if (p/'decisions.json').exists():raise ValueError('decision evidence already exists')
allowed={'SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_SECRET_KEY','CRYPTOFORGE_BACKEND','CRYPTOFORGE_LOCAL_API_URL','CRYPTOFORGE_LOCAL_API_KEY','CRYPTOFORGE_LOCAL_API_KEY_FILE'}
for line in Path('.env').read_text().splitlines():
 k,sep,v=line.partition('=');k=k.strip().removeprefix('export ')
 if sep and k in allowed:
  vals=shlex.split(v,comments=True)
  if len(vals)==1:os.environ.setdefault(k,vals[0])
inputs=json.loads((p/'inputs.json').read_text());trades=json.loads((p/'trades.json').read_text())
reader=LiveFeedbackReader(SupabaseRestClient.from_env(timeout_seconds=15))
start=datetime.fromtimestamp(inputs['history_start_ms']/1000,UTC).isoformat()
end=inputs['query_finished_at']
rows,truncated=reader._rows('trade_decisions',{'mode':'eq.live','decision':'in.(approve_entry,approve_exit)','and':f'(decided_at.gte.{start},decided_at.lte.{end})','order':'decided_at.asc,id.asc','select':'pair,decided_at,decision,reasons,features,strategy_name,strategy_version'})
write_json_report(p/'decisions.json',{'rows':rows,'truncated':truncated,'observed_at':datetime.now(UTC).isoformat()},default=str)
if truncated:raise ValueError('decision capture truncated; do not treat as complete attribution')
write_json_report(p/'decision-rows.json',rows,default=str)
feedback=analyze_feedback(trades,rows,as_of=datetime.fromisoformat(end))
write_json_report(p/'attributed-feedback.json',feedback,default=str)
print(json.dumps({'decisions':len(rows),'truncated':truncated,'coverage':feedback['exact_entry_cost_coverage_fraction'],'summary':feedback['summary'],'exit_matches':sum(r['exit_context_match']=='exact_order' for r in feedback['outcomes']),'outcome_orders':len(feedback['outcomes'])},default=str))
