"""Resource-gated registered feature ablation of a frozen development control."""
import argparse,hashlib,json
from pathlib import Path
from cryptoforge.ablation_study import run_registered_ablation,dependencies as study_dependencies
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.research_protocol import prepare_research
from cryptoforge.source_contract import source_hashes


def dependencies():
    return {**study_dependencies(),'cli_runner':Path(__file__),
            'report_writer':write_json_report,'resource_guard':prepare_research}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--original',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    raw=args.protocol.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=args.protocol.with_suffix('.sha256').read_text().strip():raise ValueError('ablation protocol checksum mismatch')
    protocol=prepare_research(str(args.protocol));policy=protocol['ablation_policy']
    hashes=source_hashes(dependencies())
    if hashes!=policy['implementation_hashes'] or policy['live_eligible'] is not False:
        raise ValueError('frozen research-only ablation source contract required')
    original_raw=args.original.read_bytes()
    if hashlib.sha256(original_raw).hexdigest()!=policy['original_report_sha256']:
        raise ValueError('original ablation control report changed')
    original=json.loads(original_raw)
    if original['study_sha256']!=policy['original_study_sha256']:raise ValueError('original study differs from freeze')
    report=run_registered_ablation(original,control_parameters=policy['control_parameters'],
        removed_grid=policy['removed_grid'],ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite')),
        protocol_id=sha,protocol_version=protocol['protocol_version'],
        maximum_per_family=protocol['search_limits']['max_configurations_per_family'])
    if source_hashes(dependencies())!=hashes:raise ValueError('ablation sources changed before export')
    write_json_report(args.output,report,default=str)
    print(json.dumps({'study_sha256':report['study_sha256'],'results':[
        {'removed_indices':result['parameters']['removed_indices'],
         'rmse':result['metrics']['rmse'],'rmse_difference':result['rmse_difference_from_control']}
        for result in report['results']],'feature_selection_performed':False,'live_promotion_allowed':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
