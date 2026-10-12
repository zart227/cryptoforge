"""Retry exactly one frozen ablation study; completed fits are never repeated."""
import argparse,hashlib,json,subprocess,sys,shutil
from datetime import UTC,datetime
from pathlib import Path
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.research_protocol import assert_resources
from cryptoforge.research_evidence import verify_registered_report
from cryptoforge.source_contract import source_hashes
from scripts.evaluate_net_ablation import dependencies

PROTOCOL_SHA='ea7ffc8baae9c8bcd838bf6fcd52af79dc1ff8cf4a72532c249406fb7f02beb7'
ARGS=['scripts/evaluate_net_ablation.py','--protocol','config/net-feature-ablation-research-v1.json',
      '--original','.local/state/archive-net-window-report.json',
      '--output','.local/state/archive-net-feature-ablation-report.json']


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--register-only',action='store_true')
    args=parser.parse_args(argv);root=Path.cwd()
    raw=Path(ARGS[2]).read_bytes();protocol=json.loads(raw)
    if hashlib.sha256(raw).hexdigest()!=PROTOCOL_SHA:raise ValueError('pinned ablation protocol changed')
    policy=protocol['ablation_policy']
    if source_hashes(dependencies())!=policy['implementation_hashes']:
        raise ValueError('frozen ablation sources changed; review before retry')
    if hashlib.sha256(Path(ARGS[4]).read_bytes()).hexdigest()!=policy['original_report_sha256']:
        raise ValueError('frozen original report changed')
    request_path=Path('.local/state/pending-feature-ablation-request-v1.json')
    binding={'protocol_sha256':PROTOCOL_SHA,'arguments':ARGS,
        'retry_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'live_promotion_allowed':False,'maximum_configurations':7}
    if request_path.exists():
        request=json.loads(request_path.read_bytes())
        if request['binding']!=binding:raise ValueError('observed ablation retry binding changed')
    else:
        write_json_report(request_path,{'observed_at':datetime.now(UTC).isoformat(),'binding':binding})
    if args.register_only:return 0
    status_path=Path('.local/state/pending-feature-ablation-status.json')
    def status(value,**details):
        result={'observed_at':datetime.now(UTC).isoformat(),'status':value,
                'live_promotion_allowed':False,**details}
        write_json_report(status_path,result);print(json.dumps(result));return 0
    output=Path(ARGS[6])
    if output.exists():
        report=json.loads(output.read_bytes())
        verify_registered_report(report,Path('.local/state/research-attempts.sqlite'))
        if (report['manifest']['original_study_sha256']!=policy['original_study_sha256']
                or sorted(r['parameters']['removed_indices'] for r in report['results'])!=sorted(policy['removed_grid'])):
            raise ValueError('completed ablation report differs from pinned grid')
        return status('original_completed_ablation_preserved',completed=True,study_sha256=report['study_sha256'])
    memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    try:assert_resources(protocol,memory['MemAvailable']/1024,shutil.disk_usage(root).free/1024**2)
    except ValueError:return status('deferred_by_resource_guard',completed=False)
    process=subprocess.run([sys.executable,*ARGS],capture_output=True,text=True,timeout=125)
    if process.returncode:
        if any(reason in process.stderr for reason in ('insufficient resources:','another offline research worker')):
            return status('deferred_by_resource_or_worker_guard',completed=False)
        status('ablation_failed_requires_review',completed=False,exit_code=process.returncode)
        raise RuntimeError('frozen ablation failed; inspect study records before changing protocol')
    report=json.loads(output.read_bytes())
    verify_registered_report(report,Path('.local/state/research-attempts.sqlite'))
    return status('completed_registered_ablation',completed=True,study_sha256=report['study_sha256'])


if __name__=='__main__':raise SystemExit(main())
