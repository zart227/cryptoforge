"""Candidate v2 transport and existing-budget integration, synthetic fixtures only."""
from pathlib import Path
import sqlite3

import pytest
from test_llm_research_requests import report, Advisor
from test_llm_audited_provider import local
from test_llm_exchange_audit import response, SECRET
from test_llm_existing_advisor_cli import setup
from cryptoforge import llm_audited_provider as old
from cryptoforge import llm_audited_provider_v2 as v2
from cryptoforge import llm_existing_advisor_v2_cli as cli
from cryptoforge import llm_prompt_preflight as prompt


def candidate():
    return v2.FreeAdvisor(model=v2.CANDIDATE_MODEL, parameters=('l2', 'threshold'))


def synthetic_candidate_capture(tmp_path, monkeypatch, *, catalog_price='0', response_change=None):
    research, root = setup(tmp_path)
    adapter = candidate()
    journal = cli.ExistingResearchRequests(research.paths['proposal'])
    binding = v2._journal_binding(journal, adapter, report())
    directory = root/binding['request_key']; directory.mkdir(mode=0o700)
    prepared = adapter.preflight(report())
    v2.files._write(directory, 'attempt.json', {'binding':binding, 'implementation':v2._LOADED,
        'policy':v2.POLICY, 'request_payload_sha256':v2.digest(prepared['payload'])})
    calls = []
    def fake_http(url, payload=None, headers=None, timeout=30):
        calls.append((url,payload,headers))
        if payload is None:
            return 200, v2.canonical({'data':[{'id':adapter.model,
                'pricing':{'prompt':catalog_price,'completion':'0'}}]}).encode()
        def change(body):
            body['model'] = adapter.model
            if response_change: response_change(body)
        return 200, response(change=change)
    monkeypatch.setattr(v2, '_http', fake_http)
    data = {'report':report(), 'settings':{'provider':'openrouter','model':adapter.model,
        'ollama_url':adapter.ollama_url,'parameters':list(adapter.parameters),'timeout':3,
        'api_key':SECRET,'jobpilot_env':None}, 'wall_seconds':3, 'directory':str(directory),
        'binding':binding, 'implementation':v2._LOADED}
    return research,root,adapter,journal,binding,directory,calls,data


def test_candidate_synthetic_capture_binds_exact_model_and_old_verifier_refuses(tmp_path, monkeypatch):
    research,root,adapter,journal,binding,directory,calls,data = synthetic_candidate_capture(tmp_path,monkeypatch)
    value=v2._evaluate(data)
    v2.files._write(directory,'outcome.json',{'status':'completed'})
    checked=v2.verify_attempt(directory,expected_binding=binding)
    assert checked['validation']['status']=='proposal_schema_valid_only'
    assert len(calls)==2 and calls[1][1]['model']==v2.CANDIDATE_MODEL
    assert calls[1][1]['provider']['max_price']=={'prompt':0,'completion':0}
    assert value['requested_model']==adapter.model and value['price_receipt']['model']==adapter.model
    assert v2.implementation()!=old.implementation()
    with pytest.raises(ValueError,match='original_audited_attempt_required'): old.verify_attempt(directory)
    assert all(SECRET not in p.read_text() for p in directory.rglob('*') if p.is_file())


@pytest.mark.parametrize('price',['0.01','NaN','-1'])
def test_candidate_nonzero_or_unknown_catalog_price_refused_before_dispatch(tmp_path,monkeypatch,price):
    *_,directory,calls,data=synthetic_candidate_capture(tmp_path,monkeypatch,catalog_price=price)
    with pytest.raises(v2.AdvisorUnavailable):v2._evaluate(data)
    assert len(calls)==1 and not (directory/'dispatch.json').exists()


@pytest.mark.parametrize('change',[
    lambda body:body.update(model=old.advisor_module.DEFAULT_MODEL),
    lambda body:body['choices'][0].update(finish_reason='length'),
    lambda body:body['choices'][0]['message'].update(tool_calls=[{'name':'shell'}]),
    lambda body:body['usage'].update(cost='0.01'),
])
def test_candidate_bad_response_rejected_and_capture_retained(tmp_path,monkeypatch,change):
    *_,directory,calls,data=synthetic_candidate_capture(tmp_path,monkeypatch,response_change=change)
    with pytest.raises(v2.AdvisorUnavailable,match='response refused'):v2._evaluate(data)
    assert len(calls)==2 and v2.verify_attempt(directory,finished=False)['capture_available']


def test_strict_candidate_rejects_new_completion_before_budget_or_credential(tmp_path,monkeypatch):
    research,root=setup(tmp_path); before=research.budget.path.read_bytes(); inner=research.paths['proposal'].read_bytes()
    monkeypatch.setattr(v2,'_run_worker',lambda *a,**k:pytest.fail('no worker'))
    monkeypatch.setattr(v2.advisor_module,'jobpilot_credentials',lambda *a,**k:pytest.fail('no credentials'))
    with pytest.raises(ValueError,match=prompt.UNVERIFIED_LIMIT):
        cli.propose_existing(research,report(),audit_root=root,jobpilot_env=tmp_path/'absent')
    assert before==research.budget.path.read_bytes() and inner==research.paths['proposal'].read_bytes()
    assert not list(root.iterdir())


@pytest.mark.parametrize('kwargs',[{'require_verified_input_limit':False}, {'provider':'ollama'},
    {'model':old.advisor_module.DEFAULT_MODEL},{'model':'openrouter/free'}])
def test_cannot_disable_bound_or_substitute_model(tmp_path,kwargs):
    research,root=setup(tmp_path);before=research.budget.path.read_bytes();inner=research.paths['proposal'].read_bytes()
    with pytest.raises(ValueError):cli.propose_existing(research,report(),audit_root=root,**kwargs)
    assert before==research.budget.path.read_bytes() and inner==research.paths['proposal'].read_bytes()
    assert not list(root.iterdir())


def test_candidate_reads_only_own_verified_capture_and_existing_journals(tmp_path,monkeypatch):
    research,root,adapter,journal,binding,directory,calls,data=synthetic_candidate_capture(tmp_path,monkeypatch)
    advice=v2._evaluate(data);v2.files._write(directory,'outcome.json',{'status':'completed'})
    journal.propose(adapter,report(),execute=lambda:advice)
    monkeypatch.setattr(v2,'_run_worker',lambda *a,**k:pytest.fail('cache only'))
    first=cli.propose_existing(research,report(),audit_root=root)
    second=cli.propose_existing(research,report(),audit_root=root)
    assert first['original_exchange_verified'] and second['coordinator_cached'] and len(calls)==2
    assert first['result']['advice']['api_cached'] and research.budget.snapshot()['total_reserved_actions']==3
    assert not research.paths['fit'].exists() and not research.paths['semantic_fixture'].exists()
    (directory/'capture.json').write_text('{}')
    with pytest.raises((ValueError,KeyError)):cli.propose_existing(research,report(),audit_root=root)
    assert len(calls)==2


def test_candidate_legacy_cache_without_v2_wire_refused_without_common_reservation(tmp_path,monkeypatch):
    research,root=setup(tmp_path);adapter=candidate();journal=cli.ExistingResearchRequests(research.paths['proposal'])
    legacy=Advisor().propose(report());legacy.update(provider='openrouter',model=adapter.model)
    journal.propose(adapter,report(),execute=lambda:legacy); before=research.budget.path.read_bytes()
    with pytest.raises(ValueError,match='candidate_original_v2_capture_required'):
        cli.propose_existing(research,report(),audit_root=root)
    assert research.budget.path.read_bytes()==before and not list(root.iterdir())


def test_missing_existing_API_journal_never_initialized(tmp_path):
    research,root=setup(tmp_path,initialized=False); before=research.budget.path.read_bytes()
    with pytest.raises(ValueError):cli.propose_existing(research,report(),audit_root=root)
    assert research.budget.path.read_bytes()==before and not research.paths['proposal'].exists()


def test_v2_child_executes_loopback_fixture_with_separate_worker_identity(tmp_path):
    root=tmp_path/'audit';root.mkdir(mode=0o700)
    with local() as (adapter,calls,_):
        journal=v2.ResearchRequests(tmp_path/'api.sqlite');binding=v2._journal_binding(journal,adapter,report())
        result=v2._run_worker(adapter,report(),root/binding['request_key'],binding,wall_seconds=3)
    checked=v2.verify_attempt(root/binding['request_key'],expected_binding=binding)
    assert len(calls)==1 and checked['local_outcome']['child_reaped']
    assert result['exchange_capture']['capture_sha256']==checked['capture_sha256']
    with pytest.raises(ValueError):old.verify_attempt(root/binding['request_key'])


def test_cache_proposal_must_match_original_capture_even_with_recomputed_checksum(tmp_path,monkeypatch):
    research,root,adapter,journal,binding,directory,calls,data=synthetic_candidate_capture(tmp_path,monkeypatch)
    advice=v2._evaluate(data);v2.files._write(directory,'outcome.json',{'status':'completed'})
    journal.propose(adapter,report(),execute=lambda:advice)
    with sqlite3.connect(journal.path) as db:
        payload=db.execute('SELECT payload FROM advisor_requests').fetchone()[0]
        value=v2.strict_json(payload); value['proposal']['rationale']='A substituted but schema-valid rationale.'
        db.execute('UPDATE advisor_requests SET payload=?,payload_sha256=?', (v2.canonical(value),v2.digest(value)))
    before=research.budget.path.read_bytes()
    with pytest.raises(ValueError,match='candidate_original_v2_capture_required'):
        cli.propose_existing(research,report(),audit_root=root)
    assert research.budget.path.read_bytes()==before and len(calls)==2
