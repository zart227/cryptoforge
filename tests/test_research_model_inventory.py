from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
import stat
import pytest
from cryptoforge import research_model_inventory as m, research_model_inventory_worker as worker
from cryptoforge import research_reviewed_main_runtime as reviewed_main


def event(kind,when,trained,legacy=False):
    a={'model_family':'pure-python-logistic','model_version':'fixture-active' if kind=='model.active' else 'fixture-candidate','feature_version':'candle-v1',
      'feature_names':['return_1','return_3','range_12','volume_ratio','ema_gap','rsi_14','candle_body'],
      'weights':[.1]*7,'bias':0.,'means':[0.]*7,'stds':[1.]*7,'threshold':.6,'trained_at':trained,
      'config':{'timeframe':'5m','horizon_candles':3,'lookback_candles':500}}
    if not legacy:a['config'].update(input_candle_state='closed_only',feature_lookback_candles=120,feature_calculation_contract='bounded-window-candle-v1',target_version='fixed-future-return-v1')
    p={'artifact':a,'artifact_sha256':hashlib.sha256(json.dumps(a,indent=2,sort_keys=True).encode()).hexdigest(),'model_version':a['model_version'],'feature_version':'candle-v1','model_run_id':'id'}
    return {'id':'1' if kind=='model.active' else '2','event_type':kind,'occurred_at':when,'payload_bytes':len(json.dumps(p).encode()),'payload':p}


def reseal(row):
    row['payload']['artifact_sha256']=hashlib.sha256(json.dumps(row['payload']['artifact'],indent=2,sort_keys=True).encode()).hexdigest()
    row['payload_bytes']=len(json.dumps(row['payload']).encode())


@pytest.fixture
def snapshot():
    import cryptoforge.model_registry as registry,cryptoforge.model_training as training,cryptoforge.target_contracts as targets
    profile={k:'0'*64 for k in m.SOURCE_FILES}
    profile.update({k:hashlib.sha256(Path(v.__file__).read_bytes()).hexdigest() for k,v in [('model_registry',registry),('model_training',training),('target_contracts',targets)]})
    return {'schema_version':'research-registry-snapshot-v1','database':{'database':'cryptoforge','login':'authenticator','role':'service_role','read_only':'on','isolation':'repeatable read','login_superuser':False,'snapshot':'100:100:','read_started_at':'2026-10-22T12:00:00Z'},
      'read_completed_at':'2026-10-22T12:00:00.1Z','observed_at':'2026-10-22T12:00:00.2Z',
      'events':{'model.active':[event('model.active','2026-10-07T02:59:00Z','2026-10-07T02:58:00Z',True)],'model.candidate':[event('model.candidate','2026-10-22T11:45:00Z','2026-10-22T11:44:00Z')]},
      'source_profile':{'files':profile,'head':'a'*40,'source_worktree_dirty':True,'loaded_executor_image_attested':False},
      'service':{'unit':m.POLICY['service'],'load_state':'loaded','active_state':'inactive','sub_state':'dead','main_pid':'0','last_exit_status':'0','dropins_present':False,
        'execstart_sha256':'1'*64,'entrypoint_sha256':'2'*64,'ml_mode':'gate','ml_threshold':.5,'ml_max_age_hours':36.,'entry_model_sha256':None,'live_flag_present':True,
        'process_loaded_source_verified':False,'full_command_or_environment_copied':False}}


def replay(s):return worker.evaluate({'observed_at':s['observed_at'],'events':s['events'],'max_age_hours':s['service']['ml_max_age_hours']})


def test_native_registry_stale_active_never_falls_back_to_candidate(snapshot,monkeypatch):
    monkeypatch.setattr(worker.model_registry.request,'urlopen',lambda *_a,**_k:pytest.fail('no model URI'))
    n=replay(snapshot);r=m.compose(snapshot,n)
    assert not n['events']['model.active']['registry_available'] and n['events']['model.candidate']['registry_available']
    assert not r['active_registry_available_at_snapshot'] and not r['candidate_is_automatic_entry_fallback']
    assert r['gate_entry_requires_fresh_active'] and not r['entry_model_metadata_usable_at_snapshot']
    assert r['models']['model.active']['embedded_checksum_valid']
    assert r['models']['model.active']['effective_input_candle_state']=='legacy_asof_snapshot'
    assert r['models']['model.active']['target_contract']['legacy_primary_price_target_inferred'] is True
    assert r['models']['model.candidate']['declared_input_contract']['feature_lookback_candles']==120
    assert not r['training_data_admitted'] and not r['production_promotion_authorized']


def test_fresh_active_pin_and_execution_are_separate(snapshot):
    row=snapshot['events']['model.active'][0];row['occurred_at']='2026-10-22T11:50:00Z';row['payload']['artifact']['trained_at']='2026-10-22T11:49:00Z';reseal(row)
    assert m.compose(snapshot,replay(snapshot))['active_registry_available_at_snapshot']
    snapshot['service']['entry_model_sha256']='f'*64;r=m.compose(snapshot,replay(snapshot))
    assert r['configured_pin_matches'] is False and not r['entry_model_metadata_usable_at_snapshot']
    assert not r['live_process_behavior_verified'] and not r['training_executed']


def test_equal_timestamps_are_ambiguous_not_arbitrary_selection(snapshot):
    second=deepcopy(snapshot['events']['model.active'][0]);second['id']='3';snapshot['events']['model.active'].append(second)
    n=replay(snapshot);assert n['events']['model.active']['selection_ambiguous']
    assert not m.compose(snapshot,n)['active_registry_available_at_snapshot']


def test_absent_model_is_not_an_incumbent(snapshot):
    snapshot['events']={k:[] for k in m.KINDS};r=m.compose(snapshot,replay(snapshot))
    assert r['models']['model.active']['status']=='absent' and not r['active_registry_available_at_snapshot']


@pytest.mark.parametrize('change',['future_event','future_training','checksum','feature_order','family','target','vector','zero_std','short_vector','active_ineligible'])
def test_invalid_embedded_artifact_remains_explicit(snapshot,change):
    row=snapshot['events']['model.candidate'][0];a=row['payload']['artifact']
    if change=='future_event':row['occurred_at']='2026-10-23T12:00:00Z'
    if change=='future_training':a['trained_at']='2026-10-23T12:00:00Z'
    if change=='feature_order':a['feature_names'].reverse()
    if change=='family':a['model_family']='unsupported'
    if change=='target':a['config']['target_version']='spot-long-trade-net-v2'
    if change=='vector':a['weights']=[True]*7
    if change=='zero_std':a['stds']=[0.]*7
    if change=='short_vector':a.update(short_weights=[.1],short_bias=0.)
    if change=='active_ineligible':
        row=snapshot['events']['model.active'][0];row['occurred_at']='2026-10-22T11:00:00Z';a=row['payload']['artifact'];a.update(trained_at='2026-10-22T10:59:00Z',live_eligible=False)
    reseal(row)
    if change=='checksum':row['payload']['artifact_sha256']='0'*64
    target=m.compose(snapshot,replay(snapshot))['models'][row['event_type']]
    if change=='checksum':assert not target['embedded_checksum_valid']
    elif change in ('vector','zero_std','short_vector'):assert not target['numeric_vector_shape_finite']
    elif change=='feature_order':assert not target['feature_order_matches']
    else:assert not target['registry_available']


@pytest.mark.parametrize('change',['readonly','isolation','clock','late_clock','schema','extra_root','extra_payload','event_order','duplicate_id','oversized','bad_profile','image_attestation','ml_age','ml_mode','raw_command'])
def test_snapshot_refusals(snapshot,change):
    row=snapshot['events']['model.active'][0]
    if change=='readonly':snapshot['database']['read_only']='off'
    if change=='isolation':snapshot['database']['isolation']='read committed'
    if change=='clock':snapshot['observed_at']='2026-10-22T11:59:59Z'
    if change=='late_clock':snapshot['observed_at']='2026-10-22T12:00:10Z'
    if change=='schema':snapshot['schema_version']='future'
    if change=='extra_root':snapshot['secret']='not-allowed'
    if change=='extra_payload':row['payload']['artifact_uri']='https://user:secret@host'
    if change=='event_order':
        second=deepcopy(row);second.update(id='3',occurred_at='2026-10-23T00:00:00Z');snapshot['events']['model.active'].append(second)
    if change=='duplicate_id':snapshot['events']['model.active'].append(deepcopy(row))
    if change=='oversized':row['payload_bytes']=262145
    if change=='bad_profile':snapshot['source_profile']['files']['model_registry']='bad'
    if change=='image_attestation':snapshot['source_profile']['loaded_executor_image_attested']=True
    if change=='ml_age':snapshot['service']['ml_max_age_hours']=float('inf')
    if change=='ml_mode':snapshot['service']['ml_mode']='unknown'
    if change=='raw_command':snapshot['service']['full_command_or_environment_copied']=True
    with pytest.raises((ValueError,KeyError)):m.validate_snapshot(snapshot)


@pytest.mark.parametrize('key,value',[('registry_available',True),('status','available'),('event_age_seconds',0),('artifact_sha256','0'*64),('embedded_checksum_valid',False),('feature_order_matches',False),('numeric_vector_shape_finite',False),('model_family_matches',False),('model_version','forged'),('artifact_threshold',.123),('declared_live_eligible',True),('effective_input_candle_state','closed_only'),('artifact_uri_read',True),('prediction_performed',True)])
def test_rehashed_native_fields_are_source_bound(snapshot,key,value):
    n=replay(snapshot);n['events']['model.active'][key]=value
    with pytest.raises(ValueError):m.compose(snapshot,n)


def test_import_profile_and_target_contract_are_checked(snapshot):
    n=replay(snapshot);n['loaded_source_hashes']['model_registry']='0'*64
    with pytest.raises(ValueError):m.compose(snapshot,n)
    n=replay(snapshot);n['events']['model.active']['target_contract']['fee_accounting']='profit'
    with pytest.raises(ValueError):m.compose(snapshot,n)


def service_response(extra='',mode='gate'):
    return 'LoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nExecMainStatus=0\nDropInPaths=\nExecStart={ path=/usr/bin/env ; argv[]=/usr/bin/env SECRET=must-not-copy /project/scripts/windows_background_runner.py executor --ml-mode '+mode+' --ml-threshold 0.50 --ml-max-age-hours 36 '+extra+' ; ignore_errors=no ; pid=0 }\n'


def test_service_extracts_only_whitelisted_model_flags(monkeypatch):
    calls=[]
    def run(argv,**kw):calls.append(argv);return SimpleNamespace(returncode=0,stdout=service_response('--live'))
    monkeypatch.setattr(m.subprocess,'run',run);v=m.service_metadata()
    assert v['ml_mode']=='gate' and v['ml_threshold']==.5 and v['ml_max_age_hours']==36
    assert v['live_flag_present'] and 'must-not-copy' not in m.canonical(v)
    assert 'Environment' not in calls[0][-1] and all(x not in calls[0] for x in ('start','restart','enable'))


@pytest.mark.parametrize('change',['bad_return','bad_mode','duplicate','infinite','unknown_entrypoint','multi_exec','missing_flag','unloaded'])
def test_service_unsupported_settings_refuse(monkeypatch,change):
    text=service_response()
    if change=='bad_mode':text=service_response(mode='invalid')
    if change=='duplicate':text=service_response('--ml-mode gate')
    if change=='infinite':text=text.replace('--ml-max-age-hours 36','--ml-max-age-hours inf')
    if change=='unknown_entrypoint':text=text.replace('windows_background_runner.py','other.py')
    if change=='multi_exec':text+='ExecStart={ argv[]=other ; ignore_errors=no }'
    if change=='missing_flag':text=text.replace('--ml-threshold 0.50','')
    if change=='unloaded':text=text.replace('LoadState=loaded','LoadState=not-found')
    monkeypatch.setattr(m.subprocess,'run',lambda *_a,**_k:SimpleNamespace(returncode=1 if change=='bad_return' else 0,stdout=text))
    with pytest.raises((ValueError,TypeError)):m.service_metadata()


def fake_capture(tmp_path,snapshot,monkeypatch):
    monkeypatch.setattr(m,'source_profile',lambda _:deepcopy(snapshot['source_profile']))
    monkeypatch.setattr(m,'service_metadata',lambda:deepcopy(snapshot['service']))
    monkeypatch.setattr(m,'_capture_registry',lambda _:{k:deepcopy(snapshot[k]) for k in ('database','events','read_completed_at','observed_at')})
    monkeypatch.setattr(m,'_native_replay',lambda _p,_d,s:replay(s));return tmp_path/'inventory'


def test_private_capture_and_readback_no_overwrite_or_alias(tmp_path,snapshot,monkeypatch):
    d=fake_capture(tmp_path,snapshot,monkeypatch);r=m.capture(tmp_path,d);assert m.verify(d)==r
    assert stat.S_IMODE(d.stat().st_mode)==0o700 and all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in d.iterdir())
    with pytest.raises(ValueError):m.capture(tmp_path,d)
    r['implementation']['inventory']='changed';assert m.verify(d)['implementation']==m.implementation()


@pytest.mark.parametrize('kind',['inventory','snapshot','native-replay','policy','symlink','permission'])
def test_artifacts_are_verified(tmp_path,snapshot,monkeypatch,kind):
    d=fake_capture(tmp_path,snapshot,monkeypatch);m.capture(tmp_path,d)
    if kind in ('inventory','snapshot','native-replay','policy'):(d/(kind+'.json')).write_text('{}')
    if kind=='symlink':
        p=d/'snapshot.json';p.rename(d/'original');p.symlink_to(d/'original')
    if kind=='permission':(d/'snapshot.json').chmod(0o644)
    with pytest.raises((ValueError,KeyError)):m.verify(d)


def test_source_profile_change_blocks_publication(tmp_path,snapshot,monkeypatch):
    d=fake_capture(tmp_path,snapshot,monkeypatch);calls=0
    def profile(_):
        nonlocal calls
        calls+=1;r=deepcopy(snapshot['source_profile'])
        if calls>1:r['files']['model_registry']='f'*64
        return r
    monkeypatch.setattr(m,'source_profile',profile)
    with pytest.raises(ValueError,match='changed_during_inventory'):m.capture(tmp_path,d)
    assert not d.exists()


class FakeDB:
    def __init__(self,snapshot,failure=False):self.snapshot=snapshot;self.calls=[];self.closed=False;self.failure=failure
    def __enter__(self):return self
    def __exit__(self,*_):self.closed=True
    @contextmanager
    def transaction(self):yield
    def execute(self,sql,params=None):
        self.calls.append((sql,params))
        if self.failure:raise RuntimeError('SECRET postgres://private')
        if sql==m.META_SQL:
            v=deepcopy(self.snapshot['database']);v['read_started_at']=m.timestamp(v['read_started_at'])
        elif sql==m.EVENTS_SQL:
            v=deepcopy(self.snapshot['events'][params[2]])
            for row in v:row['occurred_at']=m.timestamp(row['occurred_at'])
        else:v={'ended':m.timestamp(self.snapshot['read_completed_at'])}
        return SimpleNamespace(fetchone=lambda:v,fetchmany=lambda size:v[:size])


def test_sql_uses_readonly_transaction_fixed_projection_and_bounded_tie_detection(tmp_path,snapshot,monkeypatch):
    db=FakeDB(snapshot);monkeypatch.setattr(m.local,'_connect',lambda _:db);r=m._capture_registry(tmp_path)
    assert db.closed and len(r['events']['model.active'])==1
    assert [c[0] for c in db.calls[:3]]==['SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY','SET LOCAL ROLE service_role',"SET LOCAL TIME ZONE 'UTC'"]
    assert all(sql.startswith(('SET ','SELECT ')) for sql,_ in db.calls)
    assert [p[2] for sql,p in db.calls if sql==m.EVENTS_SQL]==list(m.KINDS)
    assert 'LIMIT 2' in m.EVENTS_SQL and 'id DESC' in m.EVENTS_SQL and 'artifact_uri' not in m.PAYLOAD_KEYS


def test_connection_errors_never_expose_private_text(tmp_path,snapshot,monkeypatch):
    db=FakeDB(snapshot,True);monkeypatch.setattr(m.local,'_connect',lambda _:db)
    with pytest.raises(ValueError) as e:m._capture_registry(tmp_path)
    assert str(e.value)=='local_registry_capture_failed' and db.closed


def test_changed_main_ast_requires_review(tmp_path,monkeypatch):
    for name in m.SOURCE_FILES.values():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture\n')
    monkeypatch.setattr(m,'_shapes',lambda _:{})
    with pytest.raises(ValueError,match='requires_review'):m.source_profile(tmp_path)


def test_native_process_has_fixed_worker_main_imports_cleared_env_and_cleanup(tmp_path,snapshot,monkeypatch):
    captured={};killed=[];n=replay(snapshot)
    class Process:
        pid=987654
        def __init__(self,argv,**kw):captured.update(argv=argv,**kw);m.files._write(tmp_path,'native.json',n)
        def wait(self,timeout=None):captured.setdefault('waits',[]).append(timeout);return 0
    monkeypatch.setattr(m.subprocess,'Popen',Process);monkeypatch.setattr(m.os,'killpg',lambda *args:killed.append(args));monkeypatch.setenv('API_SECRET','must-not-inherit')
    assert m._native_replay(tmp_path,tmp_path,snapshot)==n
    assert captured['env']['PYTHONPATH']==reviewed_main.worker_pythonpath(tmp_path) and 'API_SECRET' not in captured['env']
    assert captured['argv'][2].endswith('research_model_inventory_worker.py') and captured['waits']==[15,None] and killed


def test_cli_negative_inventory_is_successful_audit(tmp_path,snapshot,monkeypatch,capsys):
    d=fake_capture(tmp_path,snapshot,monkeypatch)
    assert m.main(['capture','--project',str(tmp_path),'--directory',str(d)])==0
    assert m.main(['verify','--directory',str(d)])==0
    assert m.main(['verify','--directory',str(tmp_path/'missing')])==2
    out=capsys.readouterr().out;assert 'active_available=false' in out and 'weights' not in out


def test_superuser_registry_snapshot_is_not_readonly_admission(snapshot):
    snapshot['database']['login_superuser']=True
    with pytest.raises(ValueError):m.validate_snapshot(snapshot)


def test_native_replay_deadline_kills_group_and_reaps(tmp_path,snapshot,monkeypatch):
    events=[]
    class Process:
        pid=987654
        def __init__(self,*a,**k):pass
        def wait(self,timeout=None):
            events.append(('wait',timeout))
            if timeout is not None:raise m.subprocess.TimeoutExpired('fixed-worker',timeout)
            return -9
    monkeypatch.setattr(m.subprocess,'Popen',Process);monkeypatch.setattr(m.os,'killpg',lambda pid,sig:events.append(('kill',pid)))
    with pytest.raises(m.subprocess.TimeoutExpired):m._native_replay(tmp_path,tmp_path,snapshot)
    assert events==[('wait',15),('kill',987654),('wait',None)]
