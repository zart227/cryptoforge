"""Contracts cannot silently turn strategy outcomes into model predictions."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys

import pytest

from cryptoforge import research_diagnostics_bridge as m
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge.training_diagnostics import digest


def seal(source):
    source['report_sha256'] = digest({k:v for k,v in source.items() if k!='report_sha256'})
    return source


def change_fact(source, metric, value, role='filtered', axis=None, group=None):
    result=source['results'][0];context=[source['study_sha256'],result['configuration_sha256'],role]
    item=result['roles'][role]['metrics'][metric] if axis is None else result['roles'][role]['attribution'][axis][group][metric]
    name=metric if axis is None else axis+':'+group+':'+metric
    item['value']=value;item['evidence_id']='ev:'+digest([context,name,value,item['unit']])
    return seal(source)


@pytest.fixture
def strategy():
    candidate={'family':'support_bounce','risk':'fixed'}
    source={'schema_version':'training-diagnostics-v1','study_sha256':'1'*64,
        'source_ledger_sha256':'2'*64,'source_protocol_sha256':'3'*64,'source_runtime_bundle_sha256':'4'*64,
        'implementation_sha256':{k:'5'*64 for k in m.MAIN_FILES},
        'datasets':[{'pair':'ETH/USDT','sha256':'6'*64,'candles':180,'start':'2026-09-20T00:00:00Z','end':'2026-09-21T00:00:00Z'}],
        'results':[],'classifier_metrics':None,'original_feature_quality':None,'measured_worker_peak_memory_mb':None,
        'limitations':m.LIMITATIONS.copy(),'provider_requests':0,'fitting_performed':False,'ledger_modified':False,
        'independent_evidence':False,'live_promotion_allowed':False}
    roles={}
    for role in m.ROLES:
        ctx=[source['study_sha256'],digest(candidate),role]
        values={k:0 for k in m.COUNTS}
        values.update(executed_trades=1,negative_trades=1,generated_signals=1)
        values.update(net_pnl='-1.000000000000',total_fees='0.200000000000',final_cash='99',open_cost_basis_at_end='0',drawdown_bound='0.01')
        values.update({k:None for k in m.OPTIONAL});values['profit_factor']='0'
        metrics={}
        for metric,value in values.items():
            unit='count' if metric in m.COUNTS else 'USDT' if metric in m.AMOUNTS or metric.startswith('net_per') else 'fraction' if metric=='drawdown_bound' else 'ratio'
            metrics[metric]={'value':value,'unit':unit,'evidence_id':'ev:'+digest([ctx,metric,value,unit])}
        attribution={}
        for axis,group in [('by_pair','ETH/USDT'),('by_entry_day','2026-09-20')]:
            rows={}
            for metric,value in {'trades':1,'positive_trades':0,'net_pnl':'-1','fees':'0.2'}.items():
                unit='count' if metric in ('trades','positive_trades') else 'USDT'
                rows[metric]={'value':value,'unit':unit,'evidence_id':'ev:'+digest([ctx,axis+':'+group+':'+metric,value,unit])}
            attribution[axis]={group:rows}
        roles[role]={'metrics':metrics,'attribution':attribution,'sample_status':'development_trades_only','historical_execution_qualified':False}
    source['results']=[{'configuration_sha256':digest(candidate),'candidate':candidate,'execution_seconds':'1.25','roles':roles}]
    return seal(source)


@pytest.fixture
def selection(strategy):
    return {'schema_version':'research-diagnostics-selection-v1','kind':'strategy_outcomes','configuration_sha256':strategy['results'][0]['configuration_sha256']}


@pytest.fixture
def prediction():
    return m.predictions.build_diagnostics({'partition':'validation','dataset_sha256':'a'*64,'source_sha256':'b'*64,
        'development_end':'2026-10-01T00:10:00Z','rows':[
            {'pair':'ETH/USDT','open_time':'2026-10-01T00:00:00Z','label_end_time':'2026-10-01T00:05:00Z','probability':.4,'label':0},
            {'pair':'ETH/USDT','open_time':'2026-10-01T00:05:00Z','label_end_time':'2026-10-01T00:10:00Z','probability':.3,'label':1}]})


def pack(tmp_path,strategy,selection):
    directory=tmp_path/'pack';m.stage_pack(directory,strategy,selection);return directory


def test_strategy_keeps_four_controls_negative_decimal_null_and_evidence(strategy,selection):
    original=deepcopy(strategy);report=m.prepare(strategy,selection)
    assert strategy==original and len(report['facts'])==76
    assert {r['group'] for r in report['facts']}==set(m.ROLES)
    pnl=[f for f in report['facts'] if f['metric']=='net_pnl']
    assert all(f['value']=='-1.000000000000' and f['unit']=='USDT' for f in pnl)
    assert all(f['evidence_id']==f['source_evidence_id'] for f in report['facts'])
    assert any(f['value'] is None for f in report['facts'])
    assert report['consumer_route']=='strategy_research_review_only'
    assert not report['legacy_parameter_advisor_compatible'] and not report['training_data_admitted']
    assert report['context']['excluded_axes']==['by_pair','by_entry_day']
    assert len(m.canonical(report).encode())<24000


def test_classifier_route_preserves_native_report_without_converting_trades(tmp_path,prediction):
    selected={'schema_version':'research-diagnostics-selection-v1','kind':'classifier_predictions','evidence_group':'overall'}
    report=m.stage_pack(tmp_path/'prediction',prediction,selected)
    assert report['consumer_route']=='legacy_prediction_advisor' and len(report['facts'])==8
    assert m.legacy_advisor_input(tmp_path/'prediction')==prediction
    assert any(f['metric']=='precision' and f['value'] is None for f in report['facts'])
    from cryptoforge.llm_research_advisor import FreeAdvisor
    audit=FreeAdvisor(parameters=('l2','threshold')).preflight(m.legacy_advisor_input(tmp_path/'prediction'))
    assert audit['audit']['hard_input_token_limit_verified'] is False


def test_strategy_route_cannot_feed_legacy_advisor(tmp_path,strategy,selection):
    directory=pack(tmp_path,strategy,selection)
    with pytest.raises(ValueError,match='cannot_be_used_as_classifier'):m.legacy_advisor_input(directory)


def test_schema_versions_are_not_interchangeable(strategy,selection,prediction):
    with pytest.raises(ValueError):m.prepare(prediction,selection)
    with pytest.raises(ValueError):m.prepare(strategy,{'schema_version':'research-diagnostics-selection-v1','kind':'classifier_predictions','evidence_group':'overall'})


@pytest.mark.parametrize('key,value',[('schema_version','training-diagnostics-v2'),('classifier_metrics',{}),('original_feature_quality',{}),
 ('measured_worker_peak_memory_mb',0),('fitting_performed',True),('independent_evidence',True),('provider_requests',True),
 ('live_promotion_allowed',True),('ledger_modified',True),('source_ledger_sha256','bad'),('limitations',[])])
def test_rehashed_incompatible_strategy_reports_refuse(strategy,selection,key,value):
    strategy[key]=value;seal(strategy)
    with pytest.raises(ValueError):m.prepare(strategy,selection)


def test_native_self_hash_extra_fields_and_foreign_configuration(strategy,selection):
    strategy['report_sha256']='0'*64
    with pytest.raises(ValueError):m.prepare(strategy,selection)
    seal(strategy);strategy['raw_logs']='secret';seal(strategy)
    with pytest.raises(ValueError):m.prepare(strategy,selection)
    strategy.pop('raw_logs');seal(strategy);selection['configuration_sha256']='0'*64
    with pytest.raises(ValueError):m.prepare(strategy,selection)


@pytest.mark.parametrize('metric,value',[('executed_trades',True),('executed_trades',-1),('net_pnl',float('nan')),
 ('net_pnl','NaN'),('net_pnl','Infinity'),('net_pnl','1e100000'),('net_pnl','1000000000000000000.00000000000000001'),
 ('net_pnl',-1),('total_fees','-1'),('drawdown_bound','1.1'),('maximum_pair_trade_fraction','1.1'),('profit_factor','-1')])
def test_invalid_source_facts_not_normalized(strategy,selection,metric,value):
    if type(value) is float:
        strategy['results'][0]['roles']['filtered']['metrics'][metric]['value']=value
    else:change_fact(strategy,metric,value)
    with pytest.raises((ValueError,OverflowError)):m.prepare(strategy,selection)


@pytest.mark.parametrize('kind',['id','unit','count_conservation','sample_status','role','duplicate_configuration','candidate','dataset_pair','dataset_time','unknown_attribution','attribution_sum','attribution_id','unknown_impl'])
def test_rehashed_structure_and_evidence_mutations_refuse(strategy,selection,kind):
    result=strategy['results'][0];role=result['roles']['filtered']
    if kind=='id':role['metrics']['net_pnl']['evidence_id']='ev:'+'f'*64
    if kind=='unit':role['metrics']['net_pnl']['unit']='ratio'
    if kind=='count_conservation':change_fact(strategy,'positive_trades',1)
    if kind=='sample_status':role['sample_status']='no_closed_trades'
    if kind=='role':result['roles'].pop('stress_filtered')
    if kind=='duplicate_configuration':strategy['results'].append(deepcopy(result))
    if kind=='candidate':result['candidate']['family']='logistic'
    if kind=='dataset_pair':strategy['datasets'][0]['pair']='BTC/USDT'
    if kind=='dataset_time':strategy['datasets'][0]['end']='2026-09-19T00:00:00Z'
    if kind=='unknown_attribution':role['attribution']['other']=None
    if kind=='attribution_sum':change_fact(strategy,'net_pnl','-2',axis='by_pair',group='ETH/USDT')
    if kind=='attribution_id':role['attribution']['by_pair']['ETH/USDT']['trades']['evidence_id']='ev:'+'0'*64
    if kind=='unknown_impl':strategy['implementation_sha256']['other']='0'*64
    seal(strategy)
    with pytest.raises(ValueError):m.prepare(strategy,selection)


def test_exact_selection_and_size_guards(strategy,selection):
    bad={**selection,'role':'filtered'}
    with pytest.raises(ValueError):m.prepare(strategy,bad)
    with pytest.raises(ValueError):m.prepare(strategy,{**selection,'kind':'free_text'})
    with pytest.raises(ValueError):m.prepare(strategy,selection,{**m.POLICY,'max_source_bytes':1000000})
    strategy['extra']='x'*262145
    with pytest.raises(ValueError):m.prepare(strategy,selection)


def test_projection_does_not_carry_attribution_or_other_configurations(strategy,selection):
    other=deepcopy(strategy['results'][0]);other['candidate']['risk']='atr';other['configuration_sha256']=digest(other['candidate'])
    # Rebuild source-context IDs for the new configuration before selecting the original.
    for role in m.ROLES:
        ctx=[strategy['study_sha256'],other['configuration_sha256'],role]
        for metric,f in other['roles'][role]['metrics'].items():f['evidence_id']='ev:'+digest([ctx,metric,f['value'],f['unit']])
        for axis,rows in other['roles'][role]['attribution'].items():
            for group,fields in rows.items():
                for metric,f in fields.items():f['evidence_id']='ev:'+digest([ctx,axis+':'+group+':'+metric,f['value'],f['unit']])
    strategy['results'].append(other);seal(strategy)
    result=m.prepare(strategy,selection)
    assert result['context']['excluded_configuration_count']==1 and len(result['facts'])==76
    assert all(f['group'] in m.ROLES for f in result['facts'])
    # Even excluded structures must satisfy the closed source contract.
    strategy['results'][1]['roles']['filtered']['metrics']['net_pnl']['unit']='secret';seal(strategy)
    with pytest.raises(ValueError):m.prepare(strategy,selection)


def test_private_pack_round_trip_tampering_and_no_alias(tmp_path,strategy,selection):
    directory=pack(tmp_path,strategy,selection);result=m.read_pack(directory)
    assert stat.S_IMODE(directory.stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in directory.iterdir())
    result['implementation']['bridge']='changed'
    assert m.read_pack(directory)['implementation']==m.implementation()
    with pytest.raises(ValueError):m.stage_pack(directory,strategy,selection)
    (directory/'evidence.json').write_text('{}')
    with pytest.raises(ValueError):m.read_pack(directory)


@pytest.mark.parametrize('kind',['source','selection','policy','symlink','parent_symlink','permission'])
def test_artifact_paths_and_rebuild_refuse(tmp_path,strategy,selection,kind):
    directory=pack(tmp_path,strategy,selection)
    if kind in ('source','selection','policy'):(directory/(kind+'.json')).write_text('{}')
    if kind=='symlink':
        p=directory/'source.json';p.rename(directory/'original.json');p.symlink_to(directory/'original.json')
    if kind=='parent_symlink':
        alias=tmp_path/'alias';alias.symlink_to(tmp_path,target_is_directory=True);directory=alias/'pack'
    if kind=='permission':(directory/'source.json').chmod(0o644)
    with pytest.raises((ValueError,KeyError)):m.read_pack(directory)


def test_native_prediction_cannot_change_between_verification_and_return(tmp_path,prediction,monkeypatch):
    directory=tmp_path/'prediction';m.stage_pack(directory,prediction,{'schema_version':'research-diagnostics-selection-v1','kind':'classifier_predictions','evidence_group':'overall'})
    actual=m._read;reads=0
    def changing(path,name,maximum):
        nonlocal reads
        value=actual(path,name,maximum)
        if name=='source.json':
            reads+=1
            if reads==2:value['decision_threshold']=.6
        return value
    monkeypatch.setattr(m,'_read',changing)
    with pytest.raises(ValueError,match='changed_during_read'):m.legacy_advisor_input(directory)


def fake_binding(tmp_path,strategy,selection,monkeypatch):
    directory=pack(tmp_path,strategy,selection);ledger=tmp_path/'ledger.sqlite';ledger.write_bytes(b'not-read-by-mock')
    profile=deepcopy(strategy['implementation_sha256'])
    monkeypatch.setattr(m,'main_profile',lambda _:deepcopy(profile))
    monkeypatch.setattr(m,'_ledger_hash',lambda _:strategy['source_ledger_sha256'])
    calls=[]
    def rebuild(project,path,study,out):calls.append((project,path,study,out));assert out.is_dir();return deepcopy(strategy)
    monkeypatch.setattr(m,'_rebuild_main',rebuild)
    return directory,ledger,profile,calls


def test_main_binding_rebuild_and_readback_do_not_retry(tmp_path,strategy,selection,monkeypatch):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    receipt=m.bind_main_source(directory,tmp_path,ledger)
    assert receipt['source_rebuilt'] is True and receipt['source_ledger_unchanged'] is True
    assert len(calls)==1 and not calls[0][3].exists()
    verified=m.read_main_binding(directory,tmp_path,ledger)
    assert verified['receipt']==receipt and not verified['source_rebuilt_in_this_verification'] and len(calls)==1
    with pytest.raises(ValueError,match='no_implicit_retry'):m.bind_main_source(directory,tmp_path,ledger)


@pytest.mark.parametrize('failure',['worker','cancel','source_mismatch','late_change'])
def test_failed_or_cancelled_main_binding_is_sticky(tmp_path,strategy,selection,monkeypatch,failure):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    real=m._rebuild_main
    def broken(*args):
        if failure=='worker':raise RuntimeError('postgres://SECRET@host SQL')
        if failure=='cancel':raise KeyboardInterrupt
        result=real(*args)
        if failure=='source_mismatch':result['provider_requests']=1
        if failure=='late_change':profile['cli']='0'*64
        return result
    monkeypatch.setattr(m,'_rebuild_main',broken)
    with pytest.raises(ValueError) as error:m.bind_main_source(directory,tmp_path,ledger)
    assert str(error.value)=='main_binding_failed_no_automatic_retry'
    receipt=json.loads((directory/'main-binding.json').read_text())
    assert receipt['status']==('cancelled' if failure=='cancel' else 'failed') and not receipt['source_rebuilt']
    with pytest.raises(ValueError):m.read_main_binding(directory,tmp_path,ledger)
    with pytest.raises(ValueError):m.bind_main_source(directory,tmp_path,ledger)
    assert not list(tmp_path.glob('main-diagnostics-*'))


def test_main_profile_or_ledger_mismatch_refuses_before_export(tmp_path,strategy,selection,monkeypatch):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    profile['cli']='0'*64
    with pytest.raises(ValueError,match='binding_changed'):m.bind_main_source(directory,tmp_path,ledger)
    assert not calls and not (directory/'main-binding.json').exists()


@pytest.mark.parametrize('field,value',[('status','started'),('source_rebuilt',False),('training_data_admitted',True),
 ('source_ledger_unchanged',False),('interpreter_sha256','0'*64),('live_connection_rechecked',True),('source_sha256','0'*64)])
def test_resealed_main_receipts_do_not_bypass_binding(tmp_path,strategy,selection,monkeypatch,field,value):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    receipt=m.bind_main_source(directory,tmp_path,ledger);receipt[field]=value
    receipt['binding_sha256']=digest({k:v for k,v in receipt.items() if k!='binding_sha256'})
    (directory/'main-binding.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError):m.read_main_binding(directory,tmp_path,ledger)


def test_main_profile_checks_regular_files_and_different_contract(tmp_path):
    for relative in m.MAIN_FILES.values():
        p=tmp_path/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('trusted profile fixture\n')
    hashes=m.main_profile(tmp_path)
    assert set(hashes)==set(m.MAIN_FILES)
    source=tmp_path/m.MAIN_FILES['training_diagnostics'];source.write_bytes(Path(m.predictions.__file__).read_bytes())
    with pytest.raises(ValueError,match='strategy_producer'):m.main_profile(tmp_path)
    source.unlink();source.symlink_to(Path(m.predictions.__file__))
    with pytest.raises(ValueError):m.main_profile(tmp_path)


def test_ledger_hash_is_private_regular_quiescent_and_never_copies(tmp_path):
    path=tmp_path/'ledger.sqlite';raw=b'SQLite format 3\0'+b'\0\0\x01\x01'+b'x'*40
    path.write_bytes(raw);path.chmod(0o600)
    assert m._ledger_hash(path)==hashlib.sha256(raw).hexdigest()
    (tmp_path/'ledger.sqlite-wal').touch()
    with pytest.raises(ValueError):m._ledger_hash(path)
    (tmp_path/'ledger.sqlite-wal').unlink();path.chmod(0o644)
    with pytest.raises(ValueError):m._ledger_hash(path)


def test_trusted_main_process_has_fixed_argv_clean_env_and_kill_reap(tmp_path,strategy,monkeypatch):
    captured={};killed=[]
    class Process:
        pid=543210
        def __init__(self,argv,**kwargs):
            captured.update(argv=argv,**kwargs)
            m.files._write(tmp_path,'rebuilt.json',strategy)
        def wait(self,timeout=None):captured.setdefault('waits',[]).append(timeout);return 0
    monkeypatch.setattr(m.subprocess,'Popen',Process);monkeypatch.setattr(m.os,'killpg',lambda pid,sig:killed.append((pid,sig)))
    monkeypatch.setenv('SECRET_API_KEY','must-not-pass')
    assert m._rebuild_main(tmp_path,tmp_path/'source.sqlite','1'*64,tmp_path)==strategy
    assert captured['argv']==[sys.executable,'-B',str(tmp_path/m.MAIN_FILES['cli']),'--ledger',str(tmp_path/'source.sqlite'),'--study-sha256','1'*64,'--output',str(tmp_path/'rebuilt.json')]
    assert 'SECRET_API_KEY' not in captured['env'] and captured['env']['PYTHONPATH']==reviewed_main.worker_pythonpath(tmp_path)
    assert captured['start_new_session'] and captured['preexec_fn'] is m._export_limits
    assert captured['waits']==[15,None] and killed==[(543210,signal.SIGKILL)]


def test_worker_timeout_kills_group_and_reaps(tmp_path,monkeypatch):
    events=[]
    class Process:
        pid=543210
        def __init__(self,*args,**kwargs):pass
        def wait(self,timeout=None):
            events.append(('wait',timeout))
            if timeout is not None:raise m.subprocess.TimeoutExpired('fixed-main-export',timeout)
            return -9
    monkeypatch.setattr(m.subprocess,'Popen',Process);monkeypatch.setattr(m.os,'killpg',lambda pid,sig:events.append(('kill',pid)))
    with pytest.raises(m.subprocess.TimeoutExpired):m._rebuild_main(tmp_path,tmp_path/'source.sqlite','1'*64,tmp_path)
    assert events==[('wait',15),('kill',543210),('wait',None)]


def test_cli_and_missing_artifacts_have_safe_output(tmp_path,strategy,selection,capsys):
    src=tmp_path/'source.json';src.write_text(json.dumps(strategy))
    sel=tmp_path/'selection.json';sel.write_text(json.dumps(selection))
    policy=tmp_path/'policy.json';policy.write_text(json.dumps(m.POLICY))
    directory=tmp_path/'artifact'
    assert m.main(['prepare','--directory',str(directory),'--source',str(src),'--selection',str(sel),'--policy',str(policy)])==0
    assert m.main(['verify','--directory',str(directory)])==0
    assert m.main(['legacy-input','--directory',str(directory)])==2
    assert m.main(['verify','--directory',str(tmp_path/'missing')])==2
    out=capsys.readouterr().out
    assert '-1.000000000000' not in out and 'source.sqlite' not in out


def test_complete_evidence_size_includes_final_checksum(strategy,selection):
    baseline=m.prepare(strategy,selection)
    # Valid ISO fraction padding grows selected metadata; the previous core-only
    # byte check would accept a result whose final checksum exceeds the bound.
    padding=m.POLICY['max_evidence_bytes']-len(m.canonical(baseline).encode())+19
    strategy['datasets'][0]['start']='2026-09-20T00:00:00.'+'0'*padding+'Z'
    seal(strategy)
    with pytest.raises(ValueError,match='evidence_byte_limit'):m.prepare(strategy,selection)


def test_source_swap_between_pack_verification_and_main_binding_refuses(tmp_path,strategy,selection,monkeypatch):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    actual=m._read;count=0
    def swapped(path,name,maximum):
        nonlocal count
        value=actual(path,name,maximum)
        if name=='source.json':
            count+=1
            if count==2:value['source_protocol_sha256']='f'*64;seal(value)
        return value
    monkeypatch.setattr(m,'_read',swapped)
    with pytest.raises(ValueError,match='strategy_source_changed'):m.bind_main_source(directory,tmp_path,ledger)
    assert not calls and not (directory/'main-binding.json').exists()


def test_main_binding_readback_rejects_new_profile_without_source_rebuild(tmp_path,strategy,selection,monkeypatch):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    receipt=m.bind_main_source(directory,tmp_path,ledger)
    profile['cli']='f'*64;receipt['producer_profile']=deepcopy(profile)
    receipt['binding_sha256']=digest({k:v for k,v in receipt.items() if k!='binding_sha256'})
    (directory/'main-binding.json').write_text(json.dumps(receipt))
    with pytest.raises(ValueError):m.read_main_binding(directory,tmp_path,ledger)


def test_main_export_deadline_is_saved_as_timeout_without_implicit_retry(tmp_path,strategy,selection,monkeypatch):
    directory,ledger,profile,calls=fake_binding(tmp_path,strategy,selection,monkeypatch)
    def timeout(*args):raise m.subprocess.TimeoutExpired('fixed-main-export',15)
    monkeypatch.setattr(m,'_rebuild_main',timeout)
    with pytest.raises(ValueError):m.bind_main_source(directory,tmp_path,ledger)
    receipt=json.loads((directory/'main-binding.json').read_text())
    assert receipt['status']=='timed_out' and not receipt['source_rebuilt']
    with pytest.raises(ValueError):m.bind_main_source(directory,tmp_path,ledger)
