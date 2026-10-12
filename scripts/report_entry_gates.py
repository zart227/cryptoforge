"""Read recent live decisions and report collection blockers, never change policy."""
from datetime import datetime,UTC,timedelta
import json
from cryptoforge.live_feedback import LiveFeedbackReader
from cryptoforge.supabase_market import SupabaseRestClient
from cryptoforge.entry_gate_diagnostics import analyze_entry_decisions
from cryptoforge.atomic_reports import write_json_report


def main():
    now=datetime.now(UTC);start=now-timedelta(minutes=15)
    try:
        reader=LiveFeedbackReader(SupabaseRestClient.from_env(timeout_seconds=2))
        rows,truncated=reader._rows('trade_decisions',{'mode':'eq.live','decided_at':'gte.'+start.isoformat(),
            'order':'decided_at.desc,id.desc','select':'pair,decision,decided_at,reasons'})
        result=analyze_entry_decisions(rows,as_of=now,truncated=truncated)
    except Exception as exc:
        result={'as_of':now.isoformat(),'status':'recent_decision_diagnostic_unavailable','error':type(exc).__name__,'live_policy_changed':False}
    write_json_report('.local/state/current-entry-gate-diagnostics.json',result)
    print(json.dumps(result))


if __name__=='__main__':main()
