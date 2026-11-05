"""Sidecar v5 CLI preserves existing code pins, outer/inner quotas and failures."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import stat

import pytest
from cryptoforge import research_phase_semantic_cli as m
from cryptoforge import local_semantic_requests as journal,local_semantic_worker as worker
from cryptoforge.semantic_research_catalog import SemanticResearchCatalog
from cryptoforge.research_training_diagnostics import canonical,digest
from test_research_phase import migrated,prepared
from test_research_run_budget import bindings
from test_local_semantic import record,transport_fixture
from test_source_semantic import case,source_transport
from test_ollama_systemone import catalog,response


def setup(tmp_path,*,initialize_inner=True,**kwargs):
    budget,_,_=migrated(tmp_path,**kwargs);paths={}
    for name,value in [('semantic',budget.semantic_policy),('code',m.phase.code.POLICY),('numeric',m.phase.numeric.POLICY),('phase',m.phase.POLICY)]:
        p=tmp_path/(name+'.json');p.write_text(canonical(value));paths[name]=p
    bound=bindings(tmp_path)
    args=['--database',str(budget.path),'--proposal-ledger',str(bound['proposal']),
        '--semantic-ledger',str(bound['semantic_fixture']),'--fit-ledger',str(bound['fit']),
        '--semantic-live-ledger',str(tmp_path/'live.sqlite'),'--semantic-live-policy',str(paths['semantic']),
        '--code-policy',str(paths['code']),'--numeric-policy',str(paths['numeric']),'--phase-policy',str(paths['phase'])]
    if kwargs.get('policy') is not None:
        p=tmp_path/'common-policy.json';p.write_text(canonical(kwargs['policy']));args+=['--policy',str(p)]
    if initialize_inner:
        inner=journal.LocalSemanticRequests(tmp_path/'live.sqlite',{'common_path_sha256':digest(str(budget.path)),
            'semantic_configuration_sha256':digest(budget.semantic_configuration)})
        with inner._transaction():pass
    return budget,args


def live_args(tmp_path,catalog):
    database=tmp_path/'records.sqlite';store=SemanticResearchCatalog(database)
    with closing(store._db()) as db,db:
        value=record();db.execute('insert into semantic_records values (?,?,?)',(value['experiment_id'],digest(value),canonical(value)))
    questions=tmp_path/'questions.json';questions.write_text(canonical(catalog))
    return ['semantic-live','--catalog-database',str(database),'--experiment-id',value['experiment_id'],
        '--questions',str(questions),'--model-digest','d'*64]


def source_args(tmp_path,case):
    snapshot,bundle,packet=case
    paths=[]
    for name,value in [('snapshot',snapshot),('packet',packet)]:
        p=tmp_path/(name+'.json');p.write_text(canonical(value));paths+=['--'+name,str(p)]
    directory=tmp_path/'assets';directory.mkdir(mode=0o700)
    for name,value in bundle.items():
        p=directory/(name+'.json');p.write_text(canonical(value));p.chmod(0o600)
    return ['semantic-source',*paths,'--registry',str(directory),'--model-digest','d'*64]


@pytest.mark.parametrize('route',['live','source'])
def test_existing_phase_and_inner_journal_charge_once_and_cache_same_request(tmp_path,monkeypatch,catalog,response,case,route):
    budget,args=setup(tmp_path);calls=[]
    def run(request,**kwargs):
        calls.append(1);return source_transport(request) if route=='source' else transport_fixture(request,response)
    monkeypatch.setattr(journal,'run_worker',run)
    command=live_args(tmp_path,catalog) if route=='live' else source_args(tmp_path,case)
    original_phase=Path(m.phase.__file__).read_bytes()
    for index in (1,2):
        output=tmp_path/(str(index)+'.json')
        assert m.main([*args,'--output',str(output),*command])==0
        result=json.loads(output.read_text());assert result['status']=='completed'
        assert result['call']['coordinator_cached']==(index==2)
        assert result['budget']['total_reserved_actions']==3
        assert result['budget']['reserved_by_kind']['semantic_live']==1
        assert stat.S_IMODE(output.stat().st_mode)==0o600
        assert result['automatic_migration_or_new_journal_allowed'] is False
    assert len(calls)==1 and Path(m.phase.__file__).read_bytes()==original_phase
    assert budget.snapshot()['reserved_semantic_questions']==(6 if route=='source' else len(catalog['questions']))
    with sqlite3.connect(tmp_path/'live.sqlite') as db:assert db.execute('select count(*) from local_semantic_requests').fetchone()[0]==1


def test_missing_existing_inner_journal_is_refused_before_any_new_action_or_file(tmp_path,monkeypatch,catalog):
    budget,args=setup(tmp_path,initialize_inner=False);command=live_args(tmp_path,catalog);before=budget.path.read_bytes()
    monkeypatch.setattr(journal,'run_worker',lambda *_a,**_k:pytest.fail('no backend call'))
    output=tmp_path/'refused.json';assert m.main([*args,'--output',str(output),*command])==1
    assert json.loads(output.read_text())['safe_error']=='existing_phase_semantic_inputs_action_or_budget_rejected'
    assert budget.path.read_bytes()==before and not (tmp_path/'live.sqlite').exists()
    assert not any(p.exists() for p in bindings(tmp_path).values())


def test_common_quota_rejects_before_inner_reservation_or_backend(tmp_path,monkeypatch,catalog):
    policy=deepcopy(m.phase.common.DEFAULT_POLICY);policy['total_actions']=2
    budget,args=setup(tmp_path,policy=policy);command=live_args(tmp_path,catalog)
    common=budget.path.read_bytes();inner=(tmp_path/'live.sqlite').read_bytes()
    monkeypatch.setattr(journal,'run_worker',lambda *_a,**_k:pytest.fail('exhausted common quota'))
    assert m.main([*args,'--output',str(tmp_path/'refused.json'),*command])==1
    assert common==budget.path.read_bytes() and inner==(tmp_path/'live.sqlite').read_bytes()


@pytest.mark.parametrize('error,status,code',[(RuntimeError,'failed',1),(worker.SemanticCancelled,'cancelled',130),
    (worker.SemanticTimedOut,'timed_out',1)])
def test_failures_remain_charged_and_cannot_retry_next_cli_invocation(tmp_path,monkeypatch,catalog,error,status,code):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog)
    def fail(*a,**k):raise error('do not copy private text')
    monkeypatch.setattr(journal,'run_worker',fail)
    output=tmp_path/'first.json';assert m.main([*args,'--output',str(output),*command])==code
    assert json.loads(output.read_text())['status']==status
    assert b'do not copy private text' not in output.read_bytes()
    assert budget.snapshot()['total_reserved_actions']==3
    output=tmp_path/'second.json';assert m.main([*args,'--output',str(output),*command])==1
    assert budget.snapshot()['total_reserved_actions']==3


@pytest.mark.parametrize('endpoint',['https://ollama.com','http://example.com:11434'])
def test_cloud_or_remote_endpoint_refused_without_new_common_reservation(tmp_path,monkeypatch,catalog,endpoint):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog);before=budget.path.read_bytes()
    monkeypatch.setattr(journal,'run_worker',lambda *_a,**_k:pytest.fail('remote call forbidden'))
    assert m.main([*args,'--output',str(tmp_path/'refused.json'),*command,'--endpoint',endpoint])==1
    assert before==budget.path.read_bytes()


def test_output_collisions_and_exclusive_creation_do_not_touch_journals(tmp_path,catalog):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog);before=budget.path.read_bytes()
    with pytest.raises(SystemExit):m.main([*args,'--output',str(budget.path),*command])
    output=tmp_path/'existing.json';output.write_text('original')
    with pytest.raises(FileExistsError):m.main([*args,'--output',str(output),*command])
    assert output.read_text()=='original' and before==budget.path.read_bytes()


def test_missing_catalog_never_initializes_it_or_reserves_common_action(tmp_path,monkeypatch,catalog):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog)
    database=tmp_path/'records.sqlite';database.unlink();before=budget.path.read_bytes()
    assert m.main([*args,'--output',str(tmp_path/'refused.json'),*command])==1
    assert not database.exists() and before==budget.path.read_bytes()


def test_existing_file_symlink_and_size_guards(tmp_path):
    original=tmp_path/'original';original.write_text('abc');link=tmp_path/'link';link.symlink_to(original)
    with pytest.raises(ValueError):m.existing(link)
    with pytest.raises(ValueError):m.existing(original,2)
    assert m.existing(original)==original


def test_existing_only_inner_open_never_creates_missing_or_empty_database(tmp_path):
    binding={'common_path_sha256':'a'*64,'semantic_configuration_sha256':'b'*64}
    p=tmp_path/'missing.sqlite';inner=m.ExistingLocalSemanticRequests(p,binding)
    with pytest.raises(ValueError):
        with inner._transaction():pytest.fail('missing journal cannot open')
    assert not p.exists()
    p.write_bytes(b'');p.chmod(0o600)
    with pytest.raises(ValueError):
        with inner._transaction():pytest.fail('empty journal cannot initialize')
    assert p.read_bytes()==b''


def test_existing_only_open_handles_deletion_between_preflight_and_sqlite_open(tmp_path,monkeypatch):
    p=tmp_path/'live.sqlite';p.write_bytes(b'original');p.chmod(0o600)
    inner=m.ExistingLocalSemanticRequests(p,{'common_path_sha256':'a'*64,'semantic_configuration_sha256':'b'*64})
    original=m.sqlite3.connect
    def remove_before_connect(*a,**k):p.unlink();return original(*a,**k)
    monkeypatch.setattr(m.sqlite3,'connect',remove_before_connect)
    with pytest.raises(sqlite3.OperationalError):
        with inner._transaction():pytest.fail('deleted path cannot be recreated')
    assert not p.exists()


def test_old_api_completed_effect_is_cached_by_new_wrapper_without_identity_reset(tmp_path,monkeypatch,catalog,response):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog);bound=bindings(tmp_path)
    native=m.phase.PhaseResearchCoordinator(budget.path,proposal_ledger=bound['proposal'],semantic_ledger=bound['semantic_fixture'],
        fit_ledger=bound['fit'],semantic_live_ledger=tmp_path/'live.sqlite',semantic_live_policy=budget.semantic_policy,
        code_check_policy=budget.code_policy,phase_policy=m.phase.POLICY)
    monkeypatch.setattr(journal,'run_worker',lambda request,**k:transport_fixture(request,response))
    first=native.semantic_live(tmp_path/'records.sqlite',record()['experiment_id'],catalog,digest_pin='d'*64)
    monkeypatch.setattr(journal,'run_worker',lambda *_a,**_k:pytest.fail('must reuse original API cache'))
    output=tmp_path/'cached.json';assert m.main([*args,'--output',str(output),*command])==0
    result=json.loads(output.read_text());assert result['call']['coordinator_cached']
    assert result['call']['operation_key']==first['operation_key'] and result['budget']['total_reserved_actions']==3


def test_unmigrated_common_database_refused_without_migration(tmp_path,catalog):
    budget,_,_=prepared(tmp_path)
    # Reuse exact bound paths/policies without calling the v5 migration.
    paths={}
    for name,value in [('semantic',budget.semantic_policy),('code',m.phase.code.POLICY),('numeric',m.phase.numeric.POLICY),('phase',m.phase.POLICY)]:
        p=tmp_path/(name+'.json');p.write_text(canonical(value));paths[name]=p
    bound=bindings(tmp_path);live=tmp_path/'live.sqlite';live.write_bytes(b'existing but untouched');live.chmod(0o600)
    args=['--database',str(budget.path),'--proposal-ledger',str(bound['proposal']),
        '--semantic-ledger',str(bound['semantic_fixture']),'--fit-ledger',str(bound['fit']),
        '--semantic-live-ledger',str(live),'--semantic-live-policy',str(paths['semantic']),
        '--code-policy',str(paths['code']),'--numeric-policy',str(paths['numeric']),'--phase-policy',str(paths['phase'])]
    before=budget.path.read_bytes();command=live_args(tmp_path,catalog)
    assert m.main([*args,'--output',str(tmp_path/'refused.json'),*command])==1
    assert budget.path.read_bytes()==before and live.read_bytes()==b'existing but untouched'


@pytest.mark.parametrize('name',['numeric','phase'])
def test_changed_fixed_policy_cannot_expand_old_limits(tmp_path,catalog,name):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog);before=budget.path.read_bytes()
    path=tmp_path/(name+'.json');value=json.loads(path.read_text());value['new_limits_or_refunds']=True
    path.write_text(canonical(value))
    assert m.main([*args,'--output',str(tmp_path/'refused.json'),*command])==1
    assert before==budget.path.read_bytes()


def test_copied_common_journal_at_new_path_cannot_reset_quota(tmp_path,catalog):
    budget,args=setup(tmp_path);command=live_args(tmp_path,catalog);before=budget.path.read_bytes()
    copied=tmp_path/'copied.sqlite';copied.write_bytes(before);copied.chmod(0o600)
    args[args.index('--database')+1]=str(copied)
    assert m.main([*args,'--output',str(tmp_path/'refused.json'),*command])==1
    assert before==budget.path.read_bytes() and copied.read_bytes()==before


def test_wrapper_does_not_expose_numeric_fit_proposal_or_migration_commands(tmp_path,catalog):
    budget,args=setup(tmp_path);before=budget.path.read_bytes()
    for command in ('fit','proposal','migrate','numeric-cache'):
        output=tmp_path/(command+'.json')
        with pytest.raises(SystemExit):m.main([*args,'--output',str(output),command])
        assert not output.exists()
    assert budget.path.read_bytes()==before
