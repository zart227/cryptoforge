"""Read-only registry/source/service inventory; no deployment, inference or promotion."""
import argparse
import ast
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile

from cryptoforge import research_diagnostics_bridge as bridge, research_local_export as local
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge import semantic_source_collector as files
from cryptoforge.training_diagnostics import canonical,digest,exact_fields,timestamp

SOURCE_FILES={**{n:'src/cryptoforge/'+n+'.py' for n in ('model_registry','model_training','target_contracts',
 'supabase_executor','candle_contract','backend','supabase_market','runtime_approval')},
 'executor_cli':'scripts/run_supabase_live_executor.py','background_runner':'scripts/windows_background_runner.py'}
SHAPES={'model_registry:ActiveModelRegistry._latest_by_event_type',
 'model_registry:ActiveModelRegistry._latest_event','supabase_executor:SupabaseLiveExecutor._ml_entry_allows',
 'supabase_executor:SupabaseLiveExecutor._model_input_features','supabase_market:SupabaseRestClient.from_env',
 'backend:resolve_backend','background_runner:load_environment','background_runner:target'}
POLICY={'schema_version':'research-model-inventory-policy-v1','max_snapshot_bytes':1048576,
 'max_event_bytes':262144,'max_rows_per_kind':2,'service':'cryptoforge-supabase-executor.service',
 'worker_wall_seconds':15,'reviewed_function_shapes':{'model_registry:ActiveModelRegistry._latest_by_event_type': '48eed424b43a1db01b6866d8866052d69f83ad8282f0c5528871acb007f1502f', 'model_registry:ActiveModelRegistry._latest_event': '016e16fd0fb7676bf41606162626b6542faef31cfed6f4f1cba5d68f984d40c7', 'supabase_executor:SupabaseLiveExecutor._ml_entry_allows': '61134d2e7299e3fa4d3f016e5b3e54d053afac5cf0adddd9972deec0879904a5', 'supabase_executor:SupabaseLiveExecutor._model_input_features': 'a1fb508c2ba6453356f24f85b6a841efbe31e39adf6c38a03aabd5ee70c869e6', 'supabase_market:SupabaseRestClient.from_env': '459cbdecf8d9a194117e6276616ec205bf3d6fc6c3cafc14a04468b52c0864af', 'backend:resolve_backend': '4fe6c2036ddfe5be21e83ef593507b8b115c2492cc3a7f49714eedd4ea95d1e5', 'background_runner:load_environment': '92755898ffc1c122457b5fea5788d55853a0da58a53341bc7151ae5d1c40aaf7', 'background_runner:target': '2881790950c43817bfe85739fb960b841d601adf9212f5381bb4be1c99e18491'},'training_admission_enabled':False}
KINDS=('model.active','model.candidate')
META_SQL="""SELECT current_database() AS database, session_user::text AS login,current_user::text AS role,
 current_setting('transaction_read_only') AS read_only,current_setting('transaction_isolation') AS isolation,
 (SELECT rolsuper FROM pg_roles WHERE rolname=session_user) AS login_superuser,
 pg_current_snapshot()::text AS snapshot,clock_timestamp() AS read_started_at"""
EVENTS_SQL="""SELECT id::text AS id,event_type,occurred_at,octet_length(projected::text) AS payload_bytes,
 CASE WHEN octet_length(projected::text)<=%s THEN projected ELSE NULL END AS payload
 FROM (SELECT id,event_type,occurred_at,
 COALESCE((SELECT jsonb_object_agg(key,value) FROM jsonb_each(payload) WHERE key=ANY(%s)),'{}'::jsonb) AS projected
 FROM public.system_events WHERE event_type=%s ORDER BY occurred_at DESC,id DESC LIMIT 2) latest"""
PAYLOAD_KEYS=['artifact','artifact_sha256','model_run_id','model_version','feature_version','target_version']


def implementation():
    worker=Path(__file__).with_name('research_model_inventory_worker.py')
    return {'inventory':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker':hashlib.sha256(worker.read_bytes()).hexdigest(),'source_binding':bridge.implementation()}


_LOADED=implementation()


def _guard(policy):
    if canonical(policy)!=canonical(POLICY):raise ValueError('fixed_model_inventory_policy_required')
    if implementation()!=_LOADED:raise ValueError('inventory_implementation_changed_restart_required')


def _shapes(project):
    result={}
    for key in SHAPES:
        module,name=key.split(':');nodes=ast.parse((project/SOURCE_FILES[module]).read_text()).body
        for part in name.split('.'):
            found=[n for n in nodes if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name==part]
            if len(found)!=1:raise ValueError('reviewed_main_function_required')
            node=found[0];nodes=node.body
        result[key]=hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()
    return result


def source_profile(project):
    project=local._safe_directory(project);profile={}
    for key,relative in SOURCE_FILES.items():
        path=project/relative;local._safe_directory(path.parent)
        if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=512000:
            raise ValueError('bounded_regular_main_source_required')
        profile[key]=hashlib.sha256(path.read_bytes()).hexdigest()
    if _shapes(project)!=POLICY['reviewed_function_shapes']:raise ValueError('main_routing_changed_requires_review')
    head=subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True,timeout=3).strip()
    dirty=subprocess.check_output(['git','-C',str(project),'status','--porcelain=v1','--',*SOURCE_FILES.values()],text=True,timeout=3)
    return {'files':profile,'head':head,'source_worktree_dirty':bool(dirty.strip()),'loaded_executor_image_attested':False}


def service_metadata():
    props='LoadState,ActiveState,SubState,MainPID,ExecMainStatus,DropInPaths,ExecStart'
    run=subprocess.run(['systemctl','--user','show',POLICY['service'],'--property='+props],capture_output=True,text=True,timeout=4)
    if run.returncode or len(run.stdout.encode())>64000:raise ValueError('installed_service_metadata_unavailable')
    values=dict(line.split('=',1) for line in run.stdout.splitlines() if '=' in line)
    raw=values.pop('ExecStart','')
    if raw.count('argv[]=')!=1 or raw.count(' ; ignore_errors=')!=1:raise ValueError('unsupported_service_command_description')
    argv=shlex.split(raw.split('argv[]=',1)[1].split(' ; ignore_errors=',1)[0])
    positions=[i for i,v in enumerate(argv) if v.endswith('/scripts/windows_background_runner.py')]
    if len(positions)!=1 or argv[positions[0]+1:positions[0]+2]!=['executor']:
        raise ValueError('reviewed_executor_entrypoint_required')
    flags={}
    for flag in ('--ml-mode','--ml-threshold','--ml-max-age-hours','--entry-model-sha256'):
        found=[i for i,v in enumerate(argv) if v==flag]
        if len(found)>1 or found and found[0]+1>=len(argv):raise ValueError('unique_service_ml_flags_required')
        flags[flag]=argv[found[0]+1] if found else None
    if flags['--ml-mode'] not in ('off','shadow','gate'):raise ValueError('explicit_service_ml_mode_required')
    threshold=float(flags['--ml-threshold']);age=float(flags['--ml-max-age-hours'])
    if not math.isfinite(threshold) or not 0<=threshold<=1 or not math.isfinite(age) or not 0<age<=720:
        raise ValueError('bounded_explicit_service_ml_limits_required')
    pin=flags['--entry-model-sha256']
    if pin is not None:bridge._sha(pin)
    if values.get('LoadState')!='loaded':raise ValueError('installed_loaded_service_required')
    return {'unit':POLICY['service'],'load_state':values.get('LoadState'),'active_state':values.get('ActiveState'),
        'sub_state':values.get('SubState'),'main_pid':values.get('MainPID'),'last_exit_status':values.get('ExecMainStatus'),
        'dropins_present':bool(values.get('DropInPaths')),'execstart_sha256':hashlib.sha256(raw.encode()).hexdigest(),
        'entrypoint_sha256':digest(argv[positions[0]]),'ml_mode':flags['--ml-mode'],'ml_threshold':threshold,
        'ml_max_age_hours':age,'entry_model_sha256':pin,'live_flag_present':'--live' in argv,
        'process_loaded_source_verified':False,'full_command_or_environment_copied':False}


def _capture_registry(project):
    try:
        with local._connect(project) as db:
            with db.transaction():
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                db.execute('SET LOCAL ROLE service_role');db.execute("SET LOCAL TIME ZONE 'UTC'")
                meta=dict(db.execute(META_SQL).fetchone());meta['read_started_at']=local._stamp(meta['read_started_at'])
                if (meta['database']!='cryptoforge' or meta['login']!='authenticator' or meta['role']!='service_role'
                    or meta['read_only']!='on' or meta['isolation']!='repeatable read' or meta['login_superuser'] is not False):
                    raise ValueError('readonly_local_registry_required')
                events={}
                for kind in KINDS:
                    events[kind]=[dict(r) for r in db.execute(EVENTS_SQL,(POLICY['max_event_bytes'],PAYLOAD_KEYS,kind)).fetchmany(3)]
                    for row in events[kind]:row['occurred_at']=local._stamp(row['occurred_at'])
                end=local._stamp(db.execute('SELECT clock_timestamp() AS ended').fetchone()['ended'])
        return {'database':meta,'events':events,'read_completed_at':end,'observed_at':local._stamp(datetime.now(timezone.utc))}
    except Exception:raise ValueError('local_registry_capture_failed') from None


def validate_snapshot(snapshot):
    exact_fields(snapshot,{'schema_version','database','events','read_completed_at','observed_at','source_profile','service'})
    if snapshot['schema_version']!='research-registry-snapshot-v1' or len(canonical(snapshot).encode())>POLICY['max_snapshot_bytes']:
        raise ValueError('bounded_model_snapshot_required')
    exact_fields(snapshot['events'],set(KINDS))
    meta=snapshot['database'];exact_fields(meta,{'database','login','role','read_only','isolation','login_superuser','snapshot','read_started_at'})
    if meta['database']!='cryptoforge' or meta['login']!='authenticator' or meta['role']!='service_role' or meta['read_only']!='on' or meta['isolation']!='repeatable read' or meta['login_superuser'] is not False:raise ValueError('fixed_readonly_registry_source_required')
    start,end,now=(timestamp(v) for v in (meta['read_started_at'],snapshot['read_completed_at'],snapshot['observed_at']))
    if not start<=end<=now or (now-end).total_seconds()>5:raise ValueError('registry_observation_clock_order_required')
    exact_fields(snapshot['source_profile'],{'files','head','source_worktree_dirty','loaded_executor_image_attested'})
    exact_fields(snapshot['source_profile']['files'],set(SOURCE_FILES))
    for value in snapshot['source_profile']['files'].values():bridge._sha(value)
    profile=snapshot['source_profile']
    if type(profile['head']) is not str or re.fullmatch(r'[a-f0-9]{40}',profile['head']) is None or type(profile['source_worktree_dirty']) is not bool or profile['loaded_executor_image_attested'] is not False:
        raise ValueError('source_only_git_profile_required')
    service=snapshot['service']
    exact_fields(service,{'unit','load_state','active_state','sub_state','main_pid','last_exit_status','dropins_present','execstart_sha256','entrypoint_sha256','ml_mode','ml_threshold','ml_max_age_hours','entry_model_sha256','live_flag_present','process_loaded_source_verified','full_command_or_environment_copied'})
    if (service['unit']!=POLICY['service'] or service['load_state']!='loaded' or service['ml_mode'] not in ('off','shadow','gate')
        or type(service['ml_threshold']) not in (int,float) or not math.isfinite(service['ml_threshold']) or not 0<=service['ml_threshold']<=1
        or type(service['ml_max_age_hours']) not in (int,float) or not math.isfinite(service['ml_max_age_hours']) or not 0<service['ml_max_age_hours']<=720
        or service['process_loaded_source_verified'] is not False or service['full_command_or_environment_copied'] is not False
        or any(type(service[k]) is not bool for k in ('dropins_present','live_flag_present'))):raise ValueError('bounded_service_model_flags_required')
    for key in ('execstart_sha256','entrypoint_sha256'):bridge._sha(service[key])
    if service['entry_model_sha256'] is not None:bridge._sha(service['entry_model_sha256'])
    for key in ('active_state','sub_state','main_pid','last_exit_status'):
        if type(service[key]) is not str or re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',service[key]) is None:raise ValueError('bounded_systemd_status_required')
    for kind,rows in snapshot['events'].items():
        if type(rows) is not list or len(rows)>2:raise ValueError('two_latest_events_only')
        previous=None;ids=set()
        for row in rows:
            exact_fields(row,{'id','event_type','occurred_at','payload_bytes','payload'})
            if row['event_type']!=kind or type(row['id']) is not str or re.fullmatch(r'[a-fA-F0-9-]{1,64}',row['id']) is None or row['id'] in ids:raise ValueError('registry_event_identity_invalid')
            ids.add(row['id']);occurred=timestamp(row['occurred_at'])
            if previous is not None and occurred>previous:raise ValueError('registry_event_order_invalid')
            previous=occurred
            if type(row['payload_bytes']) is not int or not 0<row['payload_bytes']<=POLICY['max_event_bytes'] or type(row['payload']) is not dict or set(row['payload'])-set(PAYLOAD_KEYS):raise ValueError('bounded_allowlisted_registry_payload_required')
            if len(canonical(row['payload']).encode())>POLICY['max_event_bytes']:raise ValueError('registry_payload_byte_limit')
            if 'artifact_sha256' in row['payload']:bridge._sha(row['payload']['artifact_sha256'])
    return snapshot


def _native_replay(project,directory,snapshot):
    worker=Path(__file__).with_name('research_model_inventory_worker.py')
    packet={'events':snapshot['events'],'observed_at':snapshot['observed_at'],'max_age_hours':snapshot['service']['ml_max_age_hours']}
    files._write(directory,'packet.json',packet)
    argv=[sys.executable,'-B',str(worker),'--input',str(directory/'packet.json'),'--output',str(directory/'native.json')]
    env={'PATH':'/usr/bin:/bin','PYTHONPATH':reviewed_main.worker_pythonpath(project),'PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8','TZ':'UTC'}
    proc=None
    with os.fdopen(os.open(directory/'worker.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as out:
        try:
            proc=subprocess.Popen(argv,cwd=project,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=out,start_new_session=True,preexec_fn=bridge._export_limits)
            if proc.wait(timeout=POLICY['worker_wall_seconds'])!=0:raise ValueError('native_model_replay_refused')
            return bridge._read(directory,'native.json',32000)
        finally:
            if proc:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()


def _vectors(artifact,n):
    valid=all(type(artifact.get(k)) is list and len(artifact[k])==n and all(type(x) in (int,float) and math.isfinite(x) for x in artifact[k]) for k in ('weights','means','stds'))
    valid=valid and all(x>0 for x in artifact['stds']) and type(artifact.get('bias')) in (int,float) and math.isfinite(artifact['bias'])
    if 'short_weights' in artifact:
        valid=valid and type(artifact['short_weights']) is list and len(artifact['short_weights'])==n and all(type(x) in (int,float) and math.isfinite(x) for x in artifact['short_weights']) and type(artifact.get('short_bias')) in (int,float) and math.isfinite(artifact['short_bias'])
    return valid


def _declared(artifact):
    config=artifact.get('config') or {}
    if type(config) is not dict:raise ValueError('model_config_object_required')
    fields=('timeframe','horizon_candles','lookback_candles','feature_lookback_candles','input_candle_state','feature_calculation_contract')
    values={}
    for key in fields:
        value=config.get(key)
        values[key]=value if (type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value)) or (type(value) in (int,float) and math.isfinite(value) and abs(value)<=1e9) else None
    return values,{k:k in config for k in fields}


def compose(snapshot,native):
    _guard(POLICY);validate_snapshot(snapshot)
    exact_fields(native,{'schema_version','events','main_model_family','main_feature_version','main_feature_names','max_age_hours','loaded_source_hashes','model_or_registry_mutated','live_executor_run','prediction_performed'})
    if (native['schema_version']!='research-main-model-replay-v1' or native['main_model_family']!='pure-python-logistic'
        or native['main_feature_version']!='candle-v1' or native['main_feature_names']!=['return_1','return_3','range_12','volume_ratio','ema_gap','rsi_14','candle_body']
        or any(native[n] is not False for n in ('model_or_registry_mutated','live_executor_run','prediction_performed'))
        or native['max_age_hours']!=snapshot['service']['ml_max_age_hours']):raise ValueError('fixed_native_registry_replay_required')
    exact_fields(native['events'],set(KINDS));exact_fields(native['loaded_source_hashes'],{'model_registry','model_training','target_contracts'})
    if any(value!=snapshot['source_profile']['files'][key] for key,value in native['loaded_source_hashes'].items()):raise ValueError('main_model_import_profile_mismatch')
    active=native['events']['model.active'];candidate=native['events']['model.candidate'];service=snapshot['service']
    for kind,result in native['events'].items():
        if not snapshot['events'][kind]:
            if result!={'status':'absent','registry_available':False,'selection_ambiguous':False}:raise ValueError('absent_model_not_available')
            continue
        exact_fields(result,{'status','registry_available','selection_ambiguous','native_error_type','event_time','event_age_seconds','training_age_seconds','model_version','artifact_sha256','artifact_threshold','declared_live_eligible','embedded_checksum_valid','numeric_vector_shape_finite','feature_order_matches','model_family_matches','target_contract','declared_input_contract','declared_input_field_presence','effective_input_candle_state','actual_execution_window_verified','artifact_uri_read','prediction_performed'})
        row=snapshot['events'][kind][0];artifact=row['payload'].get('artifact') or {}
        if type(artifact) is not dict:raise ValueError('embedded_model_object_required')
        flags=('registry_available','selection_ambiguous','embedded_checksum_valid','numeric_vector_shape_finite','feature_order_matches','model_family_matches')
        if any(type(result[k]) is not bool for k in flags):raise ValueError('native_boolean_model_checks_required')
        tie=len(snapshot['events'][kind])>1 and timestamp(snapshot['events'][kind][0]['occurred_at'])==timestamp(snapshot['events'][kind][1]['occurred_at'])
        checksum=bool(artifact) and hashlib.sha256(json.dumps(artifact,indent=2,sort_keys=True).encode()).hexdigest()==row['payload'].get('artifact_sha256')
        if (result['selection_ambiguous']!=tie or result['event_time']!=row['occurred_at']
            or result['artifact_sha256']!=row['payload'].get('artifact_sha256') or result['embedded_checksum_valid']!=checksum
            or result['event_age_seconds']!=(timestamp(snapshot['observed_at'])-timestamp(row['occurred_at'])).total_seconds()
            or any(result[k] is not False for k in ('actual_execution_window_verified','artifact_uri_read','prediction_performed'))
            or result['native_error_type'] not in (None,'ValueError','TypeError','KeyError','ArithmeticError','OverflowError')):
            raise ValueError('native_model_source_checks_mismatch')
        version=artifact.get('model_version')
        version=version if type(version) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',version) else None
        threshold=artifact.get('threshold')
        threshold=threshold if type(threshold) in (int,float) and math.isfinite(threshold) and abs(threshold)<=1e9 else None
        live=artifact.get('live_eligible') if type(artifact.get('live_eligible')) is bool else None
        if result['model_version']!=version or result['artifact_threshold']!=threshold or result['declared_live_eligible'] is not live:
            raise ValueError('native_model_metadata_mismatch')
        declarations,presence=_declared(artifact)
        if (result['numeric_vector_shape_finite']!=_vectors(artifact,len(native['main_feature_names']))
            or result['feature_order_matches']!=(artifact.get('feature_names')==native['main_feature_names'])
            or result['model_family_matches']!=(artifact.get('model_family')==native['main_model_family'])
            or result['declared_input_contract']!=declarations or result['declared_input_field_presence']!=presence
            or result['effective_input_candle_state']!=(declarations['input_candle_state'] if presence['input_candle_state'] else 'legacy_asof_snapshot')):
            raise ValueError('native_feature_contract_or_vector_check_mismatch')
        target=result['target_contract']
        if target is not None:
            expected={'schema_version':'target-contract-description-v1','version':'fixed-future-return-v1','outcome_kind':'future_close_price_return','fee_accounting':'price_return_excludes_execution_fees','sample_kind':'candle_endpoint','short_labels_allowed':True,'target_migration_performed':False,
                'legacy_primary_price_target_inferred':not any('target_version' in v for v in (artifact,artifact.get('config') or {}))}
            if canonical(target)!=canonical(expected):raise ValueError('native_target_description_invalid')
        if result['registry_available'] and target is None:raise ValueError('available_model_requires_target_contract')
        expected_status='ambiguous' if tie else 'available' if result['registry_available'] else 'unavailable'
        if result['status']!=expected_status or tie and result['registry_available']:raise ValueError('ambiguous_registry_selection_not_available')
        if result['registry_available'] and (not checksum or result['event_age_seconds']<0 or result['event_age_seconds']>snapshot['service']['ml_max_age_hours']*3600):
            raise ValueError('stale_future_or_corrupt_registry_cannot_be_available')
    eligible=active['registry_available'];pin=service['entry_model_sha256']
    pin_matches=None if pin is None else eligible and active.get('artifact_sha256')==pin
    issues=[]
    if not eligible:issues.append('no_fresh_active_model_at_snapshot')
    if eligible and pin_matches is False:issues.append('configured_active_artifact_pin_mismatch')
    if not active.get('embedded_checksum_valid',False):issues.append('active_embedded_checksum_unverified')
    declared=active.get('declared_input_contract',{})
    if declared.get('feature_calculation_contract') is None or declared.get('feature_lookback_candles') is None:issues.append('active_training_runtime_feature_parity_unproven')
    if snapshot['source_profile']['loaded_executor_image_attested']:raise ValueError('loaded_process_not_attested_by_source_files')
    core={'schema_version':'research-model-inventory-v1','observed_at':snapshot['observed_at'],
        'snapshot_sha256':digest(snapshot),'native_replay_sha256':digest(native),'source_profile':deepcopy(snapshot['source_profile']),
        'service':deepcopy(service),'models':deepcopy(native['events']),'main_feature_names':native['main_feature_names'],
        'entry_registry_selector':'model.active','candidate_is_automatic_entry_fallback':False,
        'configured_pin_matches':pin_matches,'active_registry_available_at_snapshot':eligible,
        'gate_entry_requires_fresh_active':service['ml_mode']=='gate','entry_model_metadata_usable_at_snapshot':eligible and pin_matches is not False and all(active.get(k) is True for k in ('embedded_checksum_valid','numeric_vector_shape_finite','feature_order_matches','model_family_matches')),
        'issues':issues,'artifact_uris_fetched':False,'actual_execution_feature_parity_verified':False,
        'live_process_behavior_verified':False,'training_data_admitted':False,'training_executed':False,
        'model_or_registry_modified':False,'provider_called':False,'production_promotion_authorized':False,
        'implementation':deepcopy(_LOADED)}
    return {**core,'inventory_sha256':digest(core)}


def capture(project,directory,policy=POLICY):
    _guard(policy);project=local._safe_directory(project);directory=Path(directory).absolute();local._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():raise ValueError('new_inventory_directory_required')
    profile=source_profile(project);service=service_metadata();source=_capture_registry(project)
    snapshot={'schema_version':'research-registry-snapshot-v1',**source,'source_profile':profile,'service':service}
    validate_snapshot(snapshot)
    with tempfile.TemporaryDirectory(prefix='registry-native-',dir=directory.parent) as tmp:native=_native_replay(project,Path(tmp),snapshot)
    if source_profile(project)!=profile:raise ValueError('main_model_source_changed_during_inventory')
    report=compose(snapshot,native);directory.mkdir(mode=0o700)
    for name,value in (('policy.json',policy),('snapshot.json',snapshot),('native-replay.json',native),('inventory.json',report)):files._write(directory,name,value)
    files._sync(directory);files._sync(directory.parent)
    return report


def verify(directory):
    directory=local._safe_directory(directory,private=True);policy=bridge._read(directory,'policy.json',10000);_guard(policy)
    result=compose(bridge._read(directory,'snapshot.json',POLICY['max_snapshot_bytes']),bridge._read(directory,'native-replay.json',32000))
    if canonical(result)!=canonical(bridge._read(directory,'inventory.json',32000)):raise ValueError('inventory_or_implementation_changed')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for name in ('capture','verify'):
        cmd=subs.add_parser(name);cmd.add_argument('--directory',type=Path,required=True)
        if name=='capture':cmd.add_argument('--project',type=Path,required=True)
    args=parser.parse_args(argv)
    try:report=capture(args.project,args.directory) if args.command=='capture' else verify(args.directory)
    except Exception:print('Model inventory refused; no model or runtime change');return 2
    print('Model inventory verified; active_available='+str(report['active_registry_available_at_snapshot']).lower()+'; promotion disabled')
    return 0


if __name__=='__main__':raise SystemExit(main())
