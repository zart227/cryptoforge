"""Read-only source-bound loss review of saved executions; never places orders."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, UTC
from decimal import Decimal
from cryptoforge.execution_loss_review import review_losses
from cryptoforge.live_trade_journal import reconstruct_trades
from cryptoforge.execution_identity import unique_executions
from cryptoforge.supabase_market import bybit_symbol_to_pair
from cryptoforge.source_contract import source_hashes, assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources, save_runtime_sources
from cryptoforge.atomic_reports import write_json_report


def review_saved_audit(audit_path, output):
    if output.exists():raise ValueError('immutable loss review already exists')
    raw=audit_path.read_bytes();audit=json.loads(raw)
    raw_inputs=Path(audit['input_reference']).read_bytes()
    if hashlib.sha256(raw_inputs).hexdigest()!=audit['input_sha256']:
        raise ValueError('original execution snapshot changed')
    load_runtime_sources(audit['runtime_source_bundle'],audit['implementation_hashes'])
    # Current replay is explicitly captured; old audit code is not executed.
    deps={'review':review_losses,'fifo':reconstruct_trades,'identity':unique_executions,
          'pair_mapping':bybit_symbol_to_pair,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps)
    rows,_=reconstruct_trades(json.loads(raw_inputs))
    report=review_losses(rows)
    if (sum((Decimal(row['realized_pnl']) for row in rows
             if row['status']=='closed' and row['realized_pnl'] is not None),Decimal(0))
            != Decimal(audit['net_pnl_quote'])):
        raise ValueError('current replay differs from original observed net')
    report.update(observed_at=datetime.now(UTC).isoformat(),source_audit_sha256=hashlib.sha256(raw).hexdigest(),
        execution_input_sha256=audit['input_sha256'],execution_input_reference=audit['input_reference'],
        implementation_hashes=hashes,runtime_source_bundle=save_runtime_sources(output.parent/'loss-review-runtime',deps,hashes),
        source='saved_execution_cache_not_fresh_wallet',current_wallet_verified=False)
    assert_source_dependencies(hashes,deps)
    write_json_report(output,report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=review_saved_audit(args.audit,args.output)
    print(json.dumps({key:report[key] for key in ('known_closed_segments','loss_segments',
        'loss_at_least_one_percent_segments','fee_equivalent_erased_nonnegative_segments')}))


if __name__=='__main__':main()
