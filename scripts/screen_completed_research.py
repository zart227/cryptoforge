"""Summarize rejections from immutable completed portfolio studies; no fitting."""
import argparse,hashlib,json
from pathlib import Path
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.development_screen import screen_development_comparison
from cryptoforge.research_evidence import verify_registered_report
from cryptoforge.source_contract import source_hashes


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,action='append',required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);raw=args.protocol.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.protocol.with_suffix('.sha256').read_text().strip():
        raise ValueError('screening gate protocol checksum mismatch')
    gates=json.loads(raw)['paper_candidate_gates']
    sources=source_hashes({'screen':screen_development_comparison,'ledger_verifier':verify_registered_report,'runner':Path(__file__)})
    results=[];seen=set()
    for path in args.report:
        if path.stat().st_size>16*1024*1024:raise ValueError('bounded screening input report required')
        report_raw=path.read_bytes();report=json.loads(report_raw)
        verify_registered_report(report,args.ledger)
        if report['study_sha256'] in seen:raise ValueError('duplicate study cannot inflate screening evidence')
        seen.add(report['study_sha256'])
        for result in report['results']:
            results.append({'study_sha256':report['study_sha256'],'report_sha256':hashlib.sha256(report_raw).hexdigest(),
                'parameters':result['parameters'],**screen_development_comparison(result['comparison'],
                    minimum_trades=gates['min_out_of_sample_trades'],minimum_profit_factor=gates['min_profit_factor'],
                    maximum_drawdown=gates['max_portfolio_drawdown'])})
    output={'results':results,'gates_protocol_sha256':hashlib.sha256(raw).hexdigest(),'implementation_hashes':sources,
        'screened_configurations':len(results),'economic_passes':sum(r['economic_screen_passed'] for r in results),
        'independent_admission_granted':False,'live_promotion_allowed':False,'fitting_performed':False}
    write_json_report(args.output,output)
    print(json.dumps({key:output[key] for key in ('screened_configurations','economic_passes','live_promotion_allowed','fitting_performed')}))
    return 0


if __name__=='__main__':raise SystemExit(main())
