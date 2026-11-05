"""Source-bound conservation replay of all saved FIFO segments and residuals."""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,UTC
from cryptoforge.fifo_conservation_audit import audit_conservation
from cryptoforge.fifo_case_audit import audit_segment
from cryptoforge.live_trade_journal import reconstruct_trades
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw
from cryptoforge.atomic_reports import write_json_report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--audit',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('immutable conservation report already exists')
    original=args.audit.read_bytes();receipt=json.loads(original);raw=Path(receipt['input_reference']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt['input_sha256']:raise ValueError('original execution input changed')
    fills=json.loads(raw);rows,_=reconstruct_trades(fills)
    deps={'conservation':audit_conservation,'arithmetic':audit_segment,'producer':reconstruct_trades,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps);result=audit_conservation(fills,rows)
    result.update(observed_at=datetime.now(UTC).isoformat(),source_audit_sha256=hashlib.sha256(original).hexdigest(),
        input_snapshot=_save_raw(args.output.parent/'conservation-inputs',json.dumps({'fills':fills,'records':rows},sort_keys=True).encode()),
        implementation_hashes=hashes,runtime_source_bundle=save_runtime_sources(args.output.parent/'conservation-runtime',deps,hashes))
    assert_source_dependencies(hashes,deps);write_json_report(args.output,result)
    print(json.dumps({key:result[key] for key in ('closed_allocations_checked','remaining_records_checked','open_lots','open_basis','unmatched_sale_quantity')}))


if __name__=='__main__':main()
