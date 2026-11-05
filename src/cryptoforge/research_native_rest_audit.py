"""Bounded local native REST precision/source-path audit; no fit or DB writes."""
import argparse
from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_value_audit as values
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.training_diagnostics import canonical,digest,exact_fields

POLICY={'schema_version':'native-local-rest-audit-policy-v1','origin':'http://127.0.0.1:54321','pairs':['BTC/USDT','ETH/USDT'],
    'timeframe':'5m','lookback_candles':144,'feature_lookback_candles':120,'horizon_candles':3,'min_label_return':'0.003',
    'maximum_local_gets':2,'maximum_body_bytes':512000,'maximum_packet_bytes':2097152,'maximum_result_bytes':2097152,
    'http_timeout_seconds':3,'worker_cpu_seconds':8,'worker_memory_bytes':536870912,'worker_wall_seconds':15,
    'credentials_file':'.local/database/api-key','database_writes_enabled':False,'training_admission_enabled':False}


def implementation():
    return {'audit':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker':hashlib.sha256(Path(__file__).with_name('research_native_rest_worker.py').read_bytes()).hexdigest(),'values':values.implementation()}


_LOADED=implementation();_POLICY_SHA=digest(POLICY)


def _guard(policy=POLICY):
    if digest(policy)!=_POLICY_SHA or implementation()!=_LOADED:raise ValueError('fixed_local_rest_audit_required')


def _limits():
    values.revisions._limits();resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def _native(project,packet,parent):
    before=values.main_profile(project)
    with tempfile.TemporaryDirectory(prefix='native-rest-',dir=parent) as temp:
        directory=Path(temp);values.files._write(directory,'packet.json',packet)
        if (directory/'packet.json').stat().st_size>2097152:raise ValueError('rest_packet_byte_limit')
        args=[sys.executable,'-B',str(Path(__file__).with_name('research_native_rest_worker.py')),'--input',str(directory/'packet.json'),'--output',str(directory/'result.json')]
        env={'PATH':'/usr/bin:/bin','PYTHONPATH':reviewed_main.worker_pythonpath(project),'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','LANG':'C.UTF-8','TZ':'UTC'}
        process=None
        with os.fdopen(os.open(directory/'worker.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
            try:
                process=subprocess.Popen(args,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True,preexec_fn=_limits)
                if process.wait(timeout=15)!=0:raise ValueError('native_local_rest_worker_refused')
                result=values.temporal._read(directory,'result.json',2097152)
            finally:
                if process is not None:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait()
    if values.main_profile(project)!=before:raise ValueError('native_rest_source_changed')
    return result


def compose(packet,result,policy=POLICY):
    _guard(policy)
    exact_fields(result,{'schema_version','mode','as_of','wires','trace','loaded_value_runtime','loaded_source_runtime','comparison',
        'local_api_requests','fit_performed','model_prediction_performed','database_writes'})
    if (result['schema_version']!='native-local-rest-worker-v1' or result['mode']!=packet['mode'] or result['as_of']!=packet['as_of']
            or result['loaded_value_runtime']!=values.REVIEWED_VALUE_RUNTIME or result['loaded_source_runtime']!=values.revisions.POLICY['reviewed_sources']
            or any(result[k] is not False for k in ('fit_performed','model_prediction_performed','database_writes'))
            or type(result['local_api_requests']) is not int or result['local_api_requests']!=(2 if packet['mode']=='local_api' else 0)
            or len(result['trace'])!=2 or [r['pair'] for r in result['trace']]!=POLICY['pairs']):raise ValueError('native_rest_worker_contract_required')
    comparison=result['comparison'];count=comparison['scalar_mismatch_count']
    if type(count) is not int or count<0 or type(comparison['scalar_fields_checked']) is not int or not 0<=count<=comparison['scalar_fields_checked']<=1440:
        raise ValueError('bounded_rest_scalar_accounting_required')
    if any(comparison[k] is not False for k in ('reader_query_contains_asof_filter','historical_first_seen_or_revisions_verified')):
        raise ValueError('native_latest_cache_is_not_historical_asof')
    core={'schema_version':'native-local-rest-audit-v1','status':'decimal_transport_mismatch' if count else ('available_scalars_match_wire' if comparison['scalar_fields_checked'] else 'no_rows_available'),
        'implementation':_LOADED,'policy_sha256':digest(policy),'packet_sha256':digest(packet),'worker_result_sha256':digest(result),
        'as_of':packet['as_of'],'actual_local_api_requests':result['local_api_requests'],'retained_wire_replay_only':packet['mode']!='local_api',
        'comparison':comparison,'request_trace':result['trace'],'operational_native_reader_exercised':packet['mode']=='local_api',
        'production_service_configuration_verified':False,'direct_postgresql_schema_or_repeatable_snapshot_verified':False,
        'historical_first_seen_or_revisions_verified':False,'current_database_state_revalidated_on_replay':False,
        'target_parameters_approved':False,'training_data_admitted':False,'fit_performed':False,'model_prediction_performed':False,
        'candidate_numeric_worker_executed':False,'provider_called':False,'production_promotion_authorized':False}
    return {**core,'audit_sha256':digest(core)}


def _prepare(directory,project,packet):
    _guard();directory=Path(directory).absolute();project=values.private._safe_directory(project);values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():raise ValueError('new_private_native_rest_pack_required')
    result=_native(project,packet,directory.parent);report=compose(packet,result)
    directory.mkdir(mode=0o700)
    for name,value in (('policy.json',POLICY),('request.json',{'project':str(project),'packet':packet}),('native.json',result),('audit.json',report)):
        values.files._write(directory,name,value)
    values.files._sync(directory);values.files._sync(directory.parent)
    return report


def prepare(directory,project,*,as_of=None):
    now=datetime.now(timezone.utc);cutoff=now if as_of is None else values.temporal._time(as_of)
    if cutoff>now:raise ValueError('future_local_reader_cutoff_forbidden')
    return _prepare(directory,project,{'mode':'local_api','as_of':cutoff.isoformat(),'wires':None})


def verify(directory):
    _guard();directory=values.private._safe_directory(directory,private=True)
    policy=values.temporal._read(directory,'policy.json',16000);_guard(policy)
    request=values.temporal._read(directory,'request.json',2097152);exact_fields(request,{'project','packet'})
    result=values.temporal._read(directory,'native.json',2097152);report=compose(request['packet'],result)
    replay={'mode':'retained_wire_replay','as_of':result['as_of'],'wires':result['wires']}
    recomputed=_native(values.private._safe_directory(request['project']),replay,directory.parent);compose(replay,recomputed)
    if any(recomputed[k]!=result[k] for k in ('as_of','wires','trace','loaded_value_runtime','loaded_source_runtime','comparison')):
        raise ValueError('retained_wire_native_replay_differs')
    if report!=values.temporal._read(directory,'audit.json',2097152):raise ValueError('native_rest_audit_changed')
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);subs=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','verify'):
        sub=subs.add_parser(name);sub.add_argument('--directory',type=Path,required=True)
        if name=='prepare':sub.add_argument('--project',type=Path,required=True);sub.add_argument('--as-of')
    args=p.parse_args(argv)
    try:report=verify(args.directory) if args.command=='verify' else prepare(args.directory,args.project,as_of=args.as_of)
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError):print('Native local REST audit refused; admission disabled');return 2
    print('Native local REST audit verified: '+report['status']+'; admission disabled');return 0


if __name__=='__main__':raise SystemExit(main())
