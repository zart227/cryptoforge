"""Audit the selected historical basket against source-verified filter facts."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from cryptoforge.instrument_coverage import load_fact_events, execution_coverage
from cryptoforge.instrument_history import timestamp


def main():
    ledger_path=Path('.local/state/historical-fact-ledger.json')
    decision_path=Path('.local/state/historical-universe-20251001.json')
    proof=json.loads(Path('.local/state/historical-universe-evidence-quality.json').read_bytes())
    if hashlib.sha256(decision_path.read_bytes()).hexdigest()!=proof['decision_sha256'] or not proof['replay_matches']:
        raise ValueError('historical selection evidence changed; replay it before auditing rules')
    decision=json.loads(decision_path.read_bytes());ledger,events=load_fact_events(ledger_path)
    report=execution_coverage(events,decision['selected_symbols'],start=timestamp(decision['protocol']['as_of']),
                              end=datetime(2026,10,1,tzinfo=UTC))
    report.update(verified_at=datetime.now(UTC).isoformat(),
                  ledger_sha256=hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
                  historical_selection_sha256=proof['decision_sha256'],
                  source_coverage_gaps=ledger.get('source_coverage_gaps',[]),
                  unconfirmed_sources=ledger.get('unconfirmed_sources',[]),
                  scope='dated_initial_basket_partial_historical_metadata')
    output=Path('.local/state/historical-execution-coverage.json')
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'symbols':len(report['symbols']),'segments':len(report['segments']),
        'field_known_fraction':report['last_documented_value_fraction_of_symbol_time'],
        'certified_execution_segments':report['certified_execution_segments'],
        'source_coverage_gaps':len(report['source_coverage_gaps']),'output':str(output.resolve())}))


if __name__=='__main__':main()
