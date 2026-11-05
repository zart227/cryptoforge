"""Compare actual native loader snapshots with original decision-as-of samples."""
import argparse
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_value_audit as values
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.training_diagnostics import canonical,digest,exact_fields

POLICY={'schema_version':'research-loader-audit-policy-v1','lookback_candles':512,'feature_lookback_candles':120,
    'horizon_candles':3,'maximum_source_age_seconds':600,'minimum_source_coverage':1.0,
    'maximum_sessions':2,'maximum_samples':16,'maximum_packet_bytes':2097152,'maximum_result_bytes':262144,
    'worker_wall_seconds':15,'worker_cpu_seconds':8,'worker_memory_bytes':536870912,
    'selection_rule':'latest_completed_delivery_known_at_information_cutoff',
    'operational_reader_qualification_enabled':False,'training_admission_enabled':False}
FILES=('policy.json','binding.json','selection.json','target.json','native.json','audit.json')


def implementation():
    return {'audit':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker':hashlib.sha256(Path(__file__).with_name('research_loader_worker.py').read_bytes()).hexdigest(),
        'value_audit':values.implementation()}


_LOADED=implementation()


def _guard(policy=POLICY):
    if canonical(policy)!=canonical(POLICY):raise ValueError('fixed_loader_policy_required')
    if implementation()!=_LOADED:raise ValueError('loader_implementation_changed_restart_required')


def bind(directory):
    _guard();directory=values.private._safe_directory(directory,private=True)
    values.verify(directory)
    hashes={n:hashlib.sha256(values.private._private_read(directory,n,2097152)).hexdigest() for n in FILES}
    vb=values.temporal._read(directory,'binding.json',16000)
    current,reference,selections=values.bind_source_pack(vb['directory'])
    if vb!=current:raise ValueError('original_value_source_binding_required')
    source=Path(vb['directory'])
    projection=values.temporal._read(source,'projection.json',values.revisions.POLICY['maximum_projection_bytes'])
    protocol=values.temporal._read(source,'protocol.json',64000)
    context=values.temporal._read(source,'context.json',64000)
    _,timeline=values.revisions.validate_projection(projection,protocol,context)
    index={}
    for row in timeline:index.setdefault((row['symbol'],row['open_time']),[]).append(row)
    sessions=[]
    for partition,key in (('train','fit_information_end'),('validation','validation_information_end')):
        samples=[s for s in selections if s['partition']==partition]
        pairs=sorted({s['symbol'][:-4]+'/USDT' for s in samples});rows={};cutoff=values.temporal._time(protocol[key])
        for pair in pairs:
            symbol=pair.replace('/','');chosen=[]
            for sym,opened in sorted(index):
                if sym!=symbol:continue
                row,error=values.temporal._choose(index,symbol,values.temporal._time(opened),cutoff)
                if not error:chosen.append(row)
            rows[pair]=chosen[-512:]
        sessions.append({'partition':partition,'as_of':protocol[key],'pairs':pairs,'rows':rows,
            'samples':[{'id':s['id'],'pair':s['symbol'][:-4]+'/USDT','decision_anchor':s['decision_anchor']} for s in samples]})
    target=values.temporal._read(directory,'target.json',4000)
    packet={'reference':reference,'target':target,'sessions':sessions}
    expected=values.temporal._read(directory,'native.json',262144)
    binding={'schema_version':'research-loader-binding-v1','directory':str(directory),'files':hashes,
        'source_reference':reference,'protocol_sha256':digest(protocol)}
    return binding,packet,selections,expected


def _native(project,packet,directory):
    if len(canonical(packet).encode())>POLICY['maximum_packet_bytes']:raise ValueError('loader_packet_byte_limit')
    values.files._write(directory,'packet.json',packet)
    args=[sys.executable,'-B',str(Path(__file__).with_name('research_loader_worker.py')),'--input',str(directory/'packet.json'),'--output',str(directory/'result.json')]
    env={'PATH':'/usr/bin:/bin','PYTHONPATH':reviewed_main.worker_pythonpath(project),'PYTHONDONTWRITEBYTECODE':'1','PYTHONHASHSEED':'0','LANG':'C.UTF-8','TZ':'UTC'}
    process=None
    with os.fdopen(os.open(directory/'worker.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as log:
        try:
            process=subprocess.Popen(args,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                start_new_session=True,preexec_fn=values.revisions._limits)
            if process.wait(timeout=15)!=0:raise ValueError('native_loader_check_refused')
            return values.temporal._read(directory,'result.json',POLICY['maximum_result_bytes'])
        finally:
            if process is not None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()


def compose(binding,packet,selections,expected,native,policy=POLICY):
    _guard(policy)
    exact_fields(native,{'schema_version','packet_sha256','loaded_value_runtime','loaded_source_runtime','decimal_precision',
        'source_rows_read','sessions','actual_native_loader_invoked','operational_postgresql_reader_checked',
        'fit_performed','model_prediction_performed','network_request_performed','source_modified'})
    if (native['schema_version']!='research-native-loader-v1' or native['packet_sha256']!=digest(packet)
            or native['loaded_value_runtime']!=values.REVIEWED_VALUE_RUNTIME or native['loaded_source_runtime']!=values.revisions.POLICY['reviewed_sources']
            or native['decimal_precision']!=28 or native['actual_native_loader_invoked'] is not True
            or any(native[k] is not False for k in ('operational_postgresql_reader_checked','fit_performed','model_prediction_performed','network_request_performed','source_modified'))
            or len(native['sessions'])!=2):raise ValueError('fixed_native_loader_contract_required')
    samples=[];total_rows=0
    expected_by_id={s['id']:s for s in expected['samples']};causal_by_id={s['id']:s for s in selections}
    for session,result in zip(packet['sessions'],native['sessions']):
        exact_fields(result,{'partition','as_of','reader_trace','source_admission','all_native_examples','samples'})
        trace=[{'pair':p,'timeframe':'5m','limit':512,'returned':len(session['rows'][p]),'selected_rows_sha256':digest(session['rows'][p])} for p in session['pairs']]
        if result['partition']!=session['partition'] or result['as_of']!=session['as_of'] or result['reader_trace']!=trace:
            raise ValueError('original_loader_reader_trace_required')
        if type(result['all_native_examples']) is not int or not 0<=result['all_native_examples']<=2048:
            raise ValueError('bounded_native_example_count_required')
        if [s['id'] for s in result['samples']]!=[s['id'] for s in session['samples']]:raise ValueError('fixed_native_sample_order_required')
        total_rows+=sum(r['returned'] for r in trace)
        for entry in result['samples']:
            exact_fields(entry,{'id','example'});i=entry['id'];causal=causal_by_id[i];original=expected_by_id[i];actual=entry['example']
            pair=causal['symbol'][:-4]+'/USDT';available=original['training_status']=='checked';value_match=None;differences=None
            if actual is not None:
                exact_fields(actual,{'feature_hex','future_return_hex','long_label','short_label','input_end_time','label_end_time'})
                if len(actual['feature_hex'])!=7:raise ValueError('seven_native_loader_features_required')
                for v in [*actual['feature_hex'],actual['future_return_hex']]:values._hex(v)
                if any(type(actual[k]) is not int or actual[k] not in (0,1) for k in ('long_label','short_label')):
                    raise ValueError('binary_native_loader_labels_required')
                anchor=values.temporal._time(causal['decision_anchor'])
                if actual['input_end_time']!=(anchor-timedelta(minutes=5)).isoformat() or actual['label_end_time']!=(anchor+timedelta(minutes=15)).isoformat():
                    raise ValueError('fixed_native_loader_sample_times_required')
            if available and actual is not None:
                value_match=actual=={'feature_hex':original['training_feature_hex'],'future_return_hex':original['future_return_hex'],
                    'long_label':original['long_label'],'short_label':original['short_label'],
                    'input_end_time':original['training_input_end_time'],'label_end_time':original['label_end_time']}
                by_open={r['open_time']:r for r in session['rows'][pair]}
                differences={}
                for kind,key in (('feature','features'),('label','labels')):
                    differences[kind]=sum(by_open.get(r['open_time']) is None or (by_open[r['open_time']]['source_id'],by_open[r['open_time']]['revision_sha256'])!=(r['source_id'],r['revision_sha256']) for r in causal[key])
            issues=[]
            if not available:issues.append('causal_training_example_unavailable')
            if actual is None:issues.append('native_loader_example_unavailable')
            if value_match is False:issues.append('native_loader_values_differ_from_decision_asof')
            if differences and any(differences.values()):issues.append('native_loader_versions_differ_from_decision_asof')
            samples.append({'id':i,'partition':session['partition'],'symbol':causal['symbol'],'causal_example_available':available,
                'native_example_available':actual is not None,'values_match':value_match,'version_differences':differences,
                'compatible':not issues,'issues':issues})
    if type(native['source_rows_read']) is not int or native['source_rows_read']!=total_rows:raise ValueError('native_loader_row_accounting_required')
    core={'schema_version':'research-loader-audit-v1','status':'loader_matches_causal_samples' if samples and all(s['compatible'] for s in samples) else 'blocked',
        'binding_sha256':digest(binding),'packet_sha256':digest(packet),'native_sha256':digest(native),'policy_sha256':digest(policy),
        'implementation':_LOADED,'samples':samples,'sample_count':len(samples),'source_rows_read':total_rows,
        'native_loader_invocations':2,'native_reader_calls':sum(len(s['reader_trace']) for s in native['sessions']),
        'actual_native_loader_checked':True,'audit_reader_selection_rule':POLICY['selection_rule'],
        'audit_lookback_candles':512,'production_lookback_config_verified':False,'operational_postgresql_reader_checked':False,
        'value_comparisons':sum(s['values_match'] is not None for s in samples),
        'value_mismatches':sum(s['values_match'] is False for s in samples),
        'version_mismatch_samples':sum(bool(s['version_differences']) and any(s['version_differences'].values()) for s in samples),
        'training_data_admitted':False,'fit_performed':False,'model_prediction_performed':False,'provider_called':False,
        'candidate_numeric_worker_executed':False,'production_promotion_authorized':False,'statistical_validation_complete':False}
    return {**core,'audit_sha256':digest(core)}


def _run(project,packet,parent):
    before=values.main_profile(project)
    with tempfile.TemporaryDirectory(prefix='native-loader-',dir=parent) as tmp:native=_native(project,packet,Path(tmp))
    if values.main_profile(project)!=before:raise ValueError('native_loader_runtime_changed')
    return native


def prepare(directory,project,value_pack):
    _guard();directory=Path(directory).absolute();project=values.private._safe_directory(project)
    values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():raise ValueError('new_loader_audit_directory_required')
    bound=bind(value_pack);binding,packet,selections,expected=bound
    native=_run(project,packet,directory.parent)
    if bind(value_pack)!=bound:raise ValueError('original_loader_binding_changed')
    report=compose(binding,packet,selections,expected,native)
    directory.mkdir(mode=0o700)
    for name,value in (('policy.json',POLICY),('request.json',{'project':str(project),'binding':binding}),
                        ('packet.json',packet),('native.json',native),('audit.json',report)):values.files._write(directory,name,value)
    values.files._sync(directory);values.files._sync(directory.parent)
    return report


def verify(directory):
    _guard();directory=values.private._safe_directory(directory,private=True)
    policy=values.temporal._read(directory,'policy.json',16000);_guard(policy)
    request=values.temporal._read(directory,'request.json',16000);exact_fields(request,{'project','binding'})
    bound=bind(request['binding']['directory']);binding,packet,selections,expected=bound
    if binding!=request['binding'] or packet!=values.temporal._read(directory,'packet.json',2097152):raise ValueError('original_loader_binding_changed')
    native=_run(values.private._safe_directory(request['project']),packet,directory.parent)
    if native!=values.temporal._read(directory,'native.json',262144):raise ValueError('fresh_native_loader_replay_differs')
    if bind(binding['directory'])!=bound:raise ValueError('loader_source_changed_during_replay')
    report=compose(binding,packet,selections,expected,native,policy)
    if report!=values.temporal._read(directory,'audit.json',262144):raise ValueError('loader_audit_or_implementation_changed')
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for name in ('prepare','verify'):
        sub=subs.add_parser(name);sub.add_argument('--directory',type=Path,required=True)
        if name=='prepare':
            for arg in ('project','value-pack'):sub.add_argument('--'+arg,type=Path,required=True)
    args=parser.parse_args(argv)
    try:report=verify(args.directory) if args.command=='verify' else prepare(args.directory,args.project,args.value_pack)
    except Exception:print('Native loader audit refused; admission disabled');return 2
    print('Native loader audit verified: '+report['status']+'; admission disabled');return 0


if __name__=='__main__':raise SystemExit(main())
