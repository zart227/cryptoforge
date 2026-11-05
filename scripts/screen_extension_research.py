"""Reject weak registered extension results using the existing declared gates."""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,UTC
from cryptoforge.extension_report_evidence import verify_extension_report
from cryptoforge.development_screen import screen_development_comparison
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.atomic_reports import write_json_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=Path('config/net-classifier-balance-research-v1.json'))
    parser.add_argument('--ledger',type=Path,default=Path('.local/state/research-attempts.sqlite'))
    args=parser.parse_args()
    if args.output.exists():parser.error('observed screen output is immutable')
    raw=args.protocol.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.protocol.with_suffix('.sha256').read_text().strip():
        raise ValueError('declared gate protocol changed')
    gates=json.loads(raw)['paper_candidate_gates'];source=args.report.read_bytes();report=json.loads(source)
    verification=verify_extension_report(report,args.ledger)
    deps={'screen':screen_development_comparison,'verifier':verify_extension_report,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps)
    results=[{'candidate':result['candidate'],**screen_development_comparison(result,
        minimum_trades=gates['min_out_of_sample_trades'],minimum_profit_factor=gates['min_profit_factor'],
        maximum_drawdown=gates['max_portfolio_drawdown'])} for result in report['results']]
    output={'observed_at':datetime.now(UTC).isoformat(),'study_sha256':report['study_sha256'],
        'source_report_path':str(args.report.resolve()),'source_report_sha256':hashlib.sha256(source).hexdigest(),
        'gates_protocol_sha256':hashlib.sha256(raw).hexdigest(),'source_verification':verification,
        'results':results,'screened_configurations':len(results),'economic_passes':sum(row['economic_screen_passed'] for row in results),
        'implementation_hashes':hashes,'runtime_source_bundle':save_runtime_sources(args.output.parent/'extension-screen-runtime',deps,hashes),
        'independent_admission_granted':False,'live_promotion_allowed':False}
    assert_source_dependencies(hashes,deps);write_json_report(args.output,output)
    print(json.dumps({'screened':len(results),'economic_passes':output['economic_passes']}))


if __name__=='__main__':main()
