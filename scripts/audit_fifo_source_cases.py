"""Audit the fixed saved recent segment set; no strategy selection or orders."""
import argparse,hashlib,json
from datetime import datetime,UTC
from pathlib import Path
from cryptoforge.fifo_case_audit import audit_segment
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.atomic_reports import write_json_report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('original source audit is immutable')
    raw=args.review.read_bytes();review=json.loads(raw)
    inputs=Path(review['execution_input_reference']).read_bytes()
    if hashlib.sha256(inputs).hexdigest()!=review['execution_input_sha256']:raise ValueError('execution source changed')
    fills=json.loads(inputs);deps={'auditor':audit_segment,'runner':Path(__file__).resolve()};hashes=source_hashes(deps)
    samples=[case['source_segment'] for case in review['recent_cases']]
    if len({sample['external_trade_id'] for sample in samples})!=len(samples):raise ValueError('unique original case set required')
    results=[audit_segment(sample,fills) for sample in samples]
    report={'observed_at':datetime.now(UTC).isoformat(),'review_source_sha256':hashlib.sha256(raw).hexdigest(),
        'review_source_path':str(args.review.resolve()),'execution_input_sha256':review['execution_input_sha256'],
        'cases':results,'completed_cases':len(results),'implementation_hashes':hashes,
        'runtime_source_bundle':save_runtime_sources(args.output.parent/'fifo-case-runtime',deps,hashes),
        'independent_arithmetic_passed':True,'manual_review_complete':False,'full_fifo_order_certified':False,'live_promotion_allowed':False}
    assert_source_dependencies(hashes,deps);write_json_report(args.output,report)
    print(json.dumps({'cases':len(results),'partial_acquisition_allocations':sum(case['partial_acquisition_allocation'] for case in results)}))


if __name__=='__main__':main()
