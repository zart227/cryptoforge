"""Fixed background archive audit; resource deferral never counts as completion."""
import argparse,hashlib,json,os,subprocess,sys
from datetime import UTC,datetime
from pathlib import Path
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.source_contract import net_research_sources,source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,load_runtime_sources

ROOT=Path(__file__).resolve().parents[1]


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'))


def dependencies():
    deps=net_research_sources('label_builder',build_trade_labels,runner=ROOT/'scripts/audit_trade_labels.py')
    deps['job_runner']=Path(__file__).resolve()
    return deps


def register(directory,protocol_path=None):
    protocol_path=Path(protocol_path or ROOT/'config/research-protocol-v1.json').resolve();raw=protocol_path.read_bytes();protocol=json.loads(raw)
    from cryptoforge.research_protocol import validate_protocol
    validate_protocol(protocol)
    minimum=1024 if protocol.get('resource_override',{}).get('new_minimum_mib')==1024 else 1536
    if protocol['resources']['min_available_memory_mb']<minimum or protocol['resources']['min_free_disk_mb']<2048:
        raise ValueError('original resource reserves required')
    for dataset in protocol['datasets']:
        if hashlib.sha256((ROOT/dataset['path']).read_bytes()).hexdigest()!=dataset['sha256']:
            raise ValueError('original dataset changed before audit registration')
    deps=dependencies();hashes=source_hashes(deps)
    runtime=save_runtime_sources(directory/'runtime',deps,hashes)
    manifest={'schema_version':'fixed-long-label-audit-job-v1','observed_at':datetime.now(UTC).isoformat(),
        'protocol_path':str(protocol_path),'protocol_sha256':hashlib.sha256(raw).hexdigest(),
        'datasets':protocol['datasets'],'implementation_hashes':hashes,'runtime_source_bundle':runtime,
        'pairs':['BTC/USDT','ETH/USDT'],'max_candles':25919,'parameter_search':False,
        'scope':'development_label_arithmetic_audit_not_strategy_selection','live_promotion_allowed':False}
    sha=hashlib.sha256(encode(manifest).encode()).hexdigest();path=directory/sha/'job.json'
    write_json_report(path,{'job_sha256':sha,'manifest':manifest})
    return path


def read_job(path):
    if path.stat().st_size>1024**2:raise ValueError('bounded frozen job required')
    receipt=json.loads(path.read_bytes());manifest=receipt['manifest']
    if hashlib.sha256(encode(manifest).encode()).hexdigest()!=receipt['job_sha256'] or path.parent.name!=receipt['job_sha256']:
        raise ValueError('frozen audit job identity changed')
    if manifest.get('schema_version')!='fixed-long-label-audit-job-v1' or manifest['pairs']!=['BTC/USDT','ETH/USDT'] or manifest['max_candles']!=25919 or manifest['live_promotion_allowed'] is not False:
        raise ValueError('fixed research-only audit contract required')
    load_runtime_sources(manifest['runtime_source_bundle'],manifest['implementation_hashes'])
    return receipt


def run_job(path):
    status={'observed_at':datetime.now(UTC).isoformat(),'completed':False,'live_promotion_allowed':False}
    try:
        job=read_job(path);m=job['manifest'];report_path=path.parent/'report.json'
        if report_path.exists():
            report=json.loads(report_path.read_bytes())
            if report.get('manual_review_complete') is not False or report.get('portfolio_profitability_established') is not False:
                raise ValueError('completed audit report has unsupported scope')
            expected={key:value for key,value in m['implementation_hashes'].items() if key!='job_runner'}
            if report.get('implementation_hashes')!=expected or [row['pair'] for row in report['pairs']]!=m['pairs']:
                raise ValueError('audit output differs from frozen job')
            datasets={row['pair']:row for row in m['datasets']}
            for row in report['pairs']:
                count=int(min(m['max_candles'],datasets[row['pair']]['candles'])*.7)
                if row.get('candles')!=count or row.get('scope')!='first_70_percent_development_train_only':
                    raise ValueError('partial archive report cannot complete the full job')
                samples=row.get('samples',[]);references=row.get('sample_source_references',[])
                if row.get('audited_samples',0)<20 or len(samples)!=row['audited_samples'] or len(references)!=len(samples):
                    raise ValueError('complete sampled case source coverage required')
            load_runtime_sources(report['runtime_source_bundle'],expected)
            status.update(status='completed',completed=True,report_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest())
        else:
            assert_source_dependencies(m['implementation_hashes'],dependencies())
            if hashlib.sha256(Path(m['protocol_path']).read_bytes()).hexdigest()!=m['protocol_sha256']:
                raise ValueError('original protocol changed')
            command=[sys.executable,str(ROOT/'scripts/audit_trade_labels.py'),'--pair','BTC/USDT','--pair','ETH/USDT',
                '--max-candles','25919','--output',str(report_path),'--resource-protocol',m['protocol_path']]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=135,
                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'src')})
            if result.returncode==0:
                if not report_path.exists():raise ValueError('successful process has no audit evidence')
                return run_job(path)
            elif any(message in result.stderr for message in ('insufficient resources:','another offline research worker')):
                status.update(status='deferred_resource_or_worker_guard')
            else:status.update(status='blocked_audit_failure',exit_code=result.returncode,error_tail=result.stderr[-2000:])
    except Exception as exc:
        status.update(status='blocked_contract_or_source',error_class=type(exc).__name__)
    write_json_report(path.parent/'status.json',status)
    return status


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--register',type=Path);group.add_argument('--job',type=Path)
    parser.add_argument('--resource-protocol',type=Path)
    args=parser.parse_args()
    if args.register:print(register(args.register,args.resource_protocol))
    else:print(json.dumps(run_job(args.job)))


if __name__=='__main__':main()
