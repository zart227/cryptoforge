"""Existing-only journals and strict CLI; all responses and ledgers are synthetic."""
import json
from pathlib import Path
import sqlite3
import stat
from types import MappingProxyType

import pytest
from test_llm_research_requests import report, Advisor
from test_llm_audited_provider import local
from test_research_phase import migrated
from test_research_run_budget import bindings
from cryptoforge import llm_existing_advisor_cli as m


def setup(tmp_path, initialized=True):
    budget,_,_ = migrated(tmp_path);bound = bindings(tmp_path)
    research = object.__new__(m.phase.PhaseResearchCoordinator); research.paths = MappingProxyType(bound);research.budget = budget
    if initialized:
        inner = m.capture.ResearchRequests(bound['proposal'])
        db=inner._db(); db.execute('INSERT INTO request_policy VALUES(1,5)');db.commit();db.close()
    output = tmp_path/'audit';output.mkdir(mode=0o700)
    return research,output


def argv(tmp_path,research,output):
    files={}
    for name,value in [('semantic-live-policy',research.budget.semantic_policy),('code-policy',m.phase.code.POLICY),
                       ('numeric-policy',m.phase.numeric.POLICY),('phase-policy',m.phase.POLICY)]:
        p=tmp_path/(name+'.json');p.write_text(m.canonical(value));files[name]=p
    # A completed synthetic offline experiment receipt; no fitting is performed.
    artifact={'production_compatible':False};r=report()
    experiment={'status':'completed','command':'run','result':{'artifact':artifact,'artifact_sha256':m.digest(artifact),
        'dataset_sha256':r['dataset_sha256'],'reports':{'validation':{'diagnostics':r}}}}
    receipt=tmp_path/'experiment.json';receipt.write_text(m.canonical(experiment))
    return ['proposal','--database',str(research.budget.path),'--proposal-ledger',str(research.paths['proposal']),
        '--semantic-ledger',str(research.paths['semantic_fixture']),'--fit-ledger',str(research.paths['fit']),
        '--semantic-live-ledger',str(tmp_path/'live.sqlite'),
        *[arg for name,p in files.items() for arg in ('--'+name,str(p))],
        '--experiment-receipt',str(receipt),'--audit-root',str(output)]


def invoke(research,output,adapter,**kwargs):
    return m.propose_existing(research,report(),audit_root=output,provider=adapter.provider,
        model=adapter.model,ollama_url=adapter.ollama_url,require_verified_input_limit=False,**kwargs)


def test_existing_only_worker_charges_phase_once_and_reads_original_capture_on_cache(tmp_path):
    research,output=setup(tmp_path);before=research.budget.snapshot()
    with local() as (adapter,calls,_):
        first=invoke(research,output,adapter);second=invoke(research,output,adapter,jobpilot_env=tmp_path/'absent.env')
    assert first['original_exchange_verified'] and second['coordinator_cached'] and len(calls)==1
    assert research.budget.snapshot()['total_reserved_actions']==before['total_reserved_actions']+1
    assert first['existing_journals_only']
    assert not research.paths['fit'].exists() and not research.paths['semantic_fixture'].exists()


@pytest.mark.parametrize('state',['missing','empty','wrong_schema','missing_policy','wrong_policy','symlink','public'])
def test_existing_API_file_failure_never_initializes_schema_or_reserves_common(tmp_path,state,monkeypatch):
    research,output=setup(tmp_path,initialized=state not in ('missing','empty','wrong_schema'))
    path=research.paths['proposal']
    if state=='empty':path.write_bytes(b'');path.chmod(0o600)
    if state=='wrong_schema':
        with sqlite3.connect(path) as db:db.execute('CREATE TABLE wrong(x)')
        path.chmod(0o600)
    if state in ('missing_policy','wrong_policy'):
        with sqlite3.connect(path) as db:db.execute('DELETE FROM request_policy' if state=='missing_policy' else 'UPDATE request_policy SET maximum=10')
    if state=='symlink':
        original=tmp_path/'original-api.sqlite';path.rename(original);path.symlink_to(original)
    if state=='public':path.chmod(0o644)
    raw=path.read_bytes() if path.exists() else None;before=research.budget.path.read_bytes()
    monkeypatch.setattr(m.capture,'_run_worker',lambda *a,**k:pytest.fail('never launch'))
    with pytest.raises(ValueError):
        m.propose_existing(research,report(),audit_root=output,require_verified_input_limit=False)
    assert research.budget.path.read_bytes()==before and not list(output.iterdir())
    assert (path.read_bytes() if path.exists() else None)==raw


def test_unlink_between_checks_and_native_propose_does_not_recreate_journal(tmp_path,monkeypatch):
    research,output=setup(tmp_path);original=research._dispatch
    def dispatch(*a,**k):
        research.paths['proposal'].unlink();return original(*a,**k)
    monkeypatch.setattr(research,'_dispatch',dispatch)
    with pytest.raises(RuntimeError):
        m.propose_existing(research,report(),audit_root=output,require_verified_input_limit=False)
    assert not research.paths['proposal'].exists() and not list(output.iterdir())
    assert research.budget.snapshot()['statuses']['failed']==1


def test_CLI_always_strict_refuses_new_completion_without_any_budget_or_key(tmp_path,monkeypatch,capsys):
    research,output=setup(tmp_path);args=argv(tmp_path,research,output);result=tmp_path/'result.json'
    before=research.budget.path.read_bytes();inner=research.paths['proposal'].read_bytes()
    monkeypatch.setattr(m.capture,'_run_worker',lambda *a,**k:pytest.fail('no worker'))
    assert m.main([*args,'--jobpilot-env',str(tmp_path/'absent.env'),'--output',str(result)])==1
    value=json.loads(result.read_text());assert value['status']=='failed' and value['require_verified_input_limit']
    assert before==research.budget.path.read_bytes() and inner==research.paths['proposal'].read_bytes()
    assert not list(output.iterdir()) and stat.S_IMODE(result.stat().st_mode)==0o600
    assert 'absent.env' not in result.read_text()


def test_CLI_legacy_completed_cache_uses_original_phase_without_new_generation(tmp_path,monkeypatch):
    research,output=setup(tmp_path);args=argv(tmp_path,research,output)
    adapter=m.capture.FreeAdvisor(parameters=('l2','threshold'));legacy=Advisor().propose(report())
    legacy.update(provider=adapter.provider,model=adapter.model)
    m.ExistingResearchRequests(research.paths['proposal']).propose(adapter,report(),execute=lambda:legacy)
    monkeypatch.setattr(m.capture,'_run_worker',lambda *a,**k:pytest.fail('cached legacy cannot generate'))
    for n in (1,2):
        result=tmp_path/(str(n)+'.json');assert m.main([*args,'--output',str(result)])==0
        value=json.loads(result.read_text());assert value['result']['coordinator_cached']==(n==2)
        assert not value['result']['original_exchange_verified']
        assert value['budget']['total_reserved_actions']==3
    assert not list(output.iterdir())


def test_CLI_has_no_flag_to_disable_strict_input_admission(tmp_path):
    research,output=setup(tmp_path);args=argv(tmp_path,research,output)
    with pytest.raises(SystemExit):m.main([*args,'--output',str(tmp_path/'result.json'),'--no-require-verified-input-limit'])
    assert not (tmp_path/'result.json').exists()


@pytest.mark.parametrize('mode',['tools','bad_json'])
def test_native_failures_are_retained_in_existing_phase_and_API_without_retry(tmp_path,mode):
    research,output=setup(tmp_path)
    with local(mode) as (adapter,calls,_):
        with pytest.raises(RuntimeError):invoke(research,output,adapter)
        with pytest.raises(ValueError,match='no automatic retry'):invoke(research,output,adapter)
    assert len(calls)==1 and research.budget.snapshot()['statuses']['failed']==1
    assert m.capture.verify_attempt(next(output.iterdir()))['local_outcome']['status']=='failed'


def test_verify_command_is_offline_exclusive_private_and_sanitizes_invalid_capture(tmp_path,monkeypatch):
    research,output=setup(tmp_path)
    with local() as (adapter,_,_):invoke(research,output,adapter)
    directory=next(output.iterdir());monkeypatch.setattr(m.capture.subprocess,'Popen',lambda *a,**k:pytest.fail('offline only'))
    result=tmp_path/'verified.json';assert m.main(['verify','--directory',str(directory),'--output',str(result)])==0
    assert json.loads(result.read_text())['result']['capture_available']
    with pytest.raises(FileExistsError):m.main(['verify','--directory',str(directory),'--output',str(result)])
    with pytest.raises(SystemExit):m.main(['verify','--directory',str(directory),'--output',str(directory/'new.json')])
    (directory/'capture.json').write_text('private invalid capture')
    failed=tmp_path/'failed.json';assert m.main(['verify','--directory',str(directory),'--output',str(failed)])==1
    assert 'private invalid capture' not in failed.read_text()


def test_missing_original_common_never_initializes_it(tmp_path):
    research,output=setup(tmp_path);research.budget.path.unlink()
    with pytest.raises(ValueError):m.propose_existing(research,report(),audit_root=output,require_verified_input_limit=False)
    assert not research.budget.path.exists() and not list(output.iterdir())
