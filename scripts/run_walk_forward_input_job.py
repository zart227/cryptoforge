"""Resume one source-bound input preparation under the authorized RAM reserve."""
import argparse,hashlib,json,os,subprocess,sys
from datetime import datetime,UTC
from pathlib import Path
from cryptoforge.walk_forward_inputs import load_bound_candles,validate_source_rows
from cryptoforge.archive import download_archive
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources
from cryptoforge.atomic_reports import write_json_report

ROOT=Path(__file__).resolve().parents[1]


def dependencies():
    return {'loader':load_bound_candles,'validator':validate_source_rows,'download':download_archive,'client':BybitPublicClient,
            'worker':ROOT/'scripts/prepare_walk_forward_inputs.py','supervisor':Path(__file__).resolve()}


def run(path):
    status={'observed_at':datetime.now(UTC).isoformat(),'completed':False,'live_promotion_allowed':False}
    try:
        job=json.loads(path.read_bytes());deps=dependencies()
        assert_source_dependencies(job['implementation_hashes'],deps);load_runtime_sources(job['runtime_source_bundle'],job['implementation_hashes'])
        plan_raw=Path(job['plan']).read_bytes()
        if hashlib.sha256(plan_raw).hexdigest()!=job['plan_sha256']:raise ValueError('original plan changed')
        plan=json.loads(plan_raw);study=next(item for item in plan['studies'] if item['manifest']['fold_index']==job['fold'])
        deadline=datetime.fromisoformat(study['manifest']['fold']['test_start'])
        output=Path(job['output'])
        if not output.exists():
            if datetime.now(UTC)>=deadline:raise ValueError('first test began before original inputs were bound')
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/prepare_walk_forward_inputs.py'),
                '--plan',job['plan'],'--fold',str(job['fold']),'--output',job['output']],cwd=ROOT,
                capture_output=True,text=True,timeout=135,env={**os.environ,'PYTHONPATH':str(ROOT/'src'),'PYTHONDONTWRITEBYTECODE':'1'})
            if proc.returncode:
                if any(message in proc.stderr for message in ('insufficient resources:','another offline research worker')):
                    status['status']='deferred_resource_or_worker_guard'
                    write_json_report(path.with_name('status.json'),status);return status
                raise ValueError('input worker failed: '+proc.stderr[-1200:])
        binding=json.loads(output.read_bytes())
        if (binding['plan_sha256']!=job['plan_sha256'] or binding['fold_index']!=job['fold']
                or binding['test_candles_included'] is not False or set(binding['pairs'])!={'BTC/USDT','ETH/USDT'}
                or datetime.fromisoformat(binding['completed_at'])>=deadline
                or binding['end_ms_exclusive']!=int(datetime.fromisoformat(study['manifest']['selection_policy']['validation_end']).timestamp()*1000)):
            raise ValueError('input scope or completion deadline differs from original plan')
        rows=load_bound_candles(binding)
        status.update(status='completed',completed=True,candles={pair:len(values) for pair,values in rows.items()},
            binding_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),fit_performed=False)
    except Exception as exc:status.update(status='blocked_input_or_contract',error_class=type(exc).__name__,error=str(exc))
    write_json_report(path.with_name('status.json'),status);return status


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--job',type=Path,required=True)
    parser.add_argument('--freeze-plan',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--fold',type=int,default=0)
    args=parser.parse_args()
    if args.freeze_plan:
        if args.job.exists() or args.output is None:parser.error('new observed job and explicit output required')
        hashes=source_hashes(dependencies())
        write_json_report(args.job,{'observed_at':datetime.now(UTC).isoformat(),'plan':str(args.freeze_plan.resolve()),
            'plan_sha256':hashlib.sha256(args.freeze_plan.read_bytes()).hexdigest(),'fold':args.fold,'output':str(args.output.resolve()),
            'implementation_hashes':hashes,'runtime_source_bundle':save_runtime_sources(args.job.parent/'runtime',dependencies(),hashes)})
    print(json.dumps(run(args.job)))


if __name__=='__main__':main()
