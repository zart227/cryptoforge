import copy
import json
from pathlib import Path
import sqlite3

import pytest

from test_typesafe_sdk_bridge import catalog, sdk_request, response
from test_llm_training_study import inputs
from cryptoforge import llm_research_coordinator as module
from cryptoforge.llm_research_advisor import FreeAdvisor, DEFAULT_MODEL, jobpilot_credentials
from cryptoforge.research_run_budget import DEFAULT_POLICY, ZERO_USAGE, BudgetTimedOut
from cryptoforge.training_experiment_planner import freeze_protocol, run_experiment
from cryptoforge.training_diagnostics import canonical


def in_process_provider_fixture(advisor, report, *, api_key=None, jobpilot_env=None, **kwargs):
    """Test only: exercise fake transports without launching network-capable workers."""
    credentials = jobpilot_credentials(jobpilot_env) if jobpilot_env else {}
    advisor.api_key = api_key if api_key is not None else credentials.get('OPENROUTER_API_KEY', '')
    return advisor.propose(report)


def coordinator(tmp_path, **kwargs):
    return module.ResearchCoordinator(tmp_path/'common.sqlite',proposal_ledger=tmp_path/'api.sqlite',
        semantic_ledger=tmp_path/'semantic.sqlite',fit_ledger=tmp_path/'fit.sqlite',**kwargs)


@pytest.fixture
def development(tmp_path):
    dataset, proposal=inputs(tmp_path)
    return dataset,freeze_protocol(dataset,version='coordinated-synthetic-v1',epochs=3),proposal


def test_full_fit_mock_proposal_candidate_and_semantic_flow_uses_common_budget(tmp_path,development,sdk_request,response):
    dataset,protocol,proposal=development; research=coordinator(tmp_path)
    baseline=research.fit(dataset,protocol)
    report=baseline['result']['reports']['validation']['diagnostics']
    advice=research.propose(report,mock=proposal)
    candidate=research.fit(dataset,protocol,proposal=advice['result']['advice']['proposal'],report=report)
    semantic=research.semantic_fixture(sdk_request,response)
    snapshot=research.budget.snapshot()
    assert snapshot['reserved_by_kind']=={'fit':2,'proposal':1,'semantic_fixture':1}
    assert snapshot['total_reserved_actions']==4 and snapshot['reserved_semantic_questions']==3
    assert snapshot['observed_completed_work']=={**ZERO_USAGE,'numeric_fits':2,'fixture_workers':1}
    assert candidate['result']['artifact']['production_compatible'] is False
    assert semantic['result']['origin']=='offline_sdk_fixture'
    assert not (tmp_path/'api.sqlite').exists()


def test_reworded_proposal_is_cached_as_same_effective_fit(tmp_path,development):
    dataset,protocol,proposal=development; research=coordinator(tmp_path)
    baseline=research.fit(dataset,protocol)
    report=baseline['result']['reports']['validation']['diagnostics']
    first=research.fit(dataset,protocol,proposal=proposal,report=report)
    changed=copy.deepcopy(proposal); changed.update(hypothesis_id='different-name',rationale='Reworded explanation.')
    repeat=research.fit(dataset,protocol,proposal=changed,report=report)
    assert repeat['coordinator_cached'] and repeat['operation_key']==first['operation_key']
    assert repeat['invocation_observed']==ZERO_USAGE
    assert repeat['original_observed']['numeric_fits']==1
    assert research.budget.snapshot()['reserved_by_kind']=={'fit':2}


def test_existing_inner_fit_history_is_reused_without_refit(tmp_path,development,monkeypatch):
    dataset,protocol,_=development
    original=run_experiment(dataset,protocol,tmp_path/'fit.sqlite')
    def forbidden(*args,**kwargs): raise AssertionError('existing fit must remain cached')
    monkeypatch.setattr('cryptoforge.training_experiment_planner.execute_fit',forbidden)
    result=coordinator(tmp_path).fit(dataset,protocol)
    assert result['result']['artifact_sha256']==original['artifact_sha256']
    assert not result['result']['training_executed'] and result['invocation_observed']==ZERO_USAGE


def test_common_limit_blocks_fit_before_its_ledger_is_created(tmp_path,development,monkeypatch):
    dataset,protocol,proposal=development
    seed=tmp_path/'seed'; seed.mkdir(); baseline=run_experiment(dataset,protocol,seed/'fit.sqlite')
    report=baseline['reports']['validation']['diagnostics']
    research=coordinator(tmp_path,policy={**DEFAULT_POLICY,'total_actions':1})
    research.propose(report,mock=proposal)
    def forbidden(*args,**kwargs): raise AssertionError('outer budget must reject before invoking fit')
    monkeypatch.setattr(module,'run_experiment',forbidden)
    with pytest.raises(ValueError,match='common research action budget'): research.fit(dataset,protocol)
    assert not (tmp_path/'fit.sqlite').exists()


def test_existing_semantic_cache_uses_no_new_fixture_worker(tmp_path,sdk_request,response,monkeypatch):
    from cryptoforge import semantic_request_journal
    semantic_request_journal.SemanticRequests(tmp_path/'semantic.sqlite').evaluate(sdk_request,response)
    def forbidden(*args,**kwargs): raise AssertionError('inner cache must prevent a new worker')
    monkeypatch.setattr(semantic_request_journal,'run_worker',forbidden)
    research=coordinator(tmp_path)
    result=research.semantic_fixture(sdk_request,response)
    assert result['result']['semantic_cached'] and result['invocation_observed']==ZERO_USAGE
    assert research.budget.snapshot()['reserved_semantic_questions']==3


def test_existing_inner_fit_cap_is_not_overridden_by_common_budget(tmp_path,development):
    dataset,_,proposal=development
    protocol=freeze_protocol(dataset,version='limited-inner-v1',maximum=1,epochs=3)
    research=coordinator(tmp_path); first=research.fit(dataset,protocol)
    with pytest.raises(RuntimeError):
        research.fit(dataset,protocol,proposal=proposal,report=first['result']['reports']['validation']['diagnostics'])
    assert research.budget.snapshot()['statuses']=={'completed':1,'failed':1}
    assert research.budget.snapshot()['unknown_work_attempts']==1


def test_common_cache_does_not_accept_fabricated_validation_evidence(tmp_path,development):
    dataset,protocol,proposal=development; research=coordinator(tmp_path)
    baseline=research.fit(dataset,protocol); report=baseline['result']['reports']['validation']['diagnostics']
    research.fit(dataset,protocol,proposal=proposal,report=report)
    bad=copy.deepcopy(report); bad['evidence']['overall']['brier_score']=0
    with pytest.raises(ValueError): research.fit(dataset,protocol,proposal=proposal,report=bad)
    assert research.budget.snapshot()['total_reserved_actions']==2


def test_provider_adapter_journal_and_outer_cache_without_network_or_secret_leak(tmp_path,development,monkeypatch):
    dataset,protocol,proposal=development; research=coordinator(tmp_path)
    baseline=research.fit(dataset,protocol); report=baseline['result']['reports']['validation']['diagnostics']
    calls=[]
    def transport(url,payload=None,headers=None,timeout=None):
        calls.append(url)
        if url.endswith('/models'):
            return {'data':[{'id':DEFAULT_MODEL,'pricing':{'prompt':'0','completion':'0'}}]}
        assert headers=={'Authorization':'Bearer synthetic-secret'}
        return {'model':DEFAULT_MODEL,'choices':[{'finish_reason':'stop','message':{'content':canonical(proposal)}}]}
    monkeypatch.setattr(module,'FreeAdvisor',lambda **kwargs:FreeAdvisor(**kwargs,transport=transport))
    monkeypatch.setattr(module,'run_provider_worker',in_process_provider_fixture)
    env=tmp_path/'jobpilot.env'; env.write_text('OPENROUTER_API_KEY=synthetic-secret\n')
    result=research.propose(report,provider='openrouter',jobpilot_env=env)
    assert result['invocation_observed']['remote_completions']==1 and len(calls)==2
    env.unlink()
    repeat=research.propose(report,provider='openrouter',jobpilot_env=env)
    assert repeat['coordinator_cached'] and repeat['invocation_observed']==ZERO_USAGE
    assert len(calls)==2
    with sqlite3.connect(tmp_path/'common.sqlite') as db:
        assert 'synthetic-secret' not in repr(db.execute('SELECT * FROM coordinated_actions').fetchall())


def test_persisted_api_limit_still_counts_failed_coordinated_provider_attempt(tmp_path,development,monkeypatch):
    dataset,protocol,proposal=development; research=coordinator(tmp_path)
    report=research.fit(dataset,protocol)['result']['reports']['validation']['diagnostics']
    def fail(*args,**kwargs): raise RuntimeError('private provider failure')
    monkeypatch.setattr(module,'run_provider_worker',in_process_provider_fixture)
    monkeypatch.setenv('CRYPTOFORGE_OPENROUTER_API_KEY','synthetic-key')
    monkeypatch.setattr(module,'FreeAdvisor',lambda **kwargs:FreeAdvisor(**kwargs,transport=fail))
    with pytest.raises(RuntimeError): research.propose(report,provider='openrouter',jobpilot_env=None)
    with sqlite3.connect(tmp_path/'api.sqlite') as db:
        assert db.execute('SELECT status FROM advisor_requests').fetchone()[0]=='failed'
    assert research.budget.snapshot()['statuses']=={'completed':1,'failed':1}
    with pytest.raises(ValueError,match='no automatic retry'):
        research.propose(report,provider='openrouter',jobpilot_env=None)


def test_semantic_timeout_marks_both_journals_and_stays_offline(tmp_path,sdk_request,response):
    from cryptoforge.semantic_request_journal import DEFAULT_POLICY as semantic_policy
    research=coordinator(tmp_path)
    with pytest.raises(BudgetTimedOut):
        research.semantic_fixture(sdk_request,response,semantic_policy={**semantic_policy,'wall_seconds':0.01})
    assert research.budget.snapshot()['statuses']=={'timed_out':1}
    with sqlite3.connect(tmp_path/'semantic.sqlite') as db:
        assert db.execute('SELECT status FROM semantic_requests').fetchone()[0]=='timed_out'


def test_paid_model_and_cloud_ollama_are_rejected_without_common_reservation(tmp_path,development):
    dataset,protocol,_=development
    baseline=run_experiment(dataset,protocol,tmp_path/'fit.sqlite')
    report=baseline['reports']['validation']['diagnostics']; research=coordinator(tmp_path)
    with pytest.raises(ValueError,match='free'): research.propose(report,provider='openrouter',model='paid/model')
    with pytest.raises(ValueError,match='local Ollama'):
        research.propose(report,provider='ollama',ollama_url='https://ollama.com')
    assert not (tmp_path/'common.sqlite').exists()


def test_cli_round_trip_status_and_receipt_reuse(tmp_path,development,sdk_request,response):
    dataset,protocol,proposal=development
    protocol_path=tmp_path/'protocol.json'; protocol_path.write_text(canonical(protocol))
    proposal_path=tmp_path/'proposal.json'; proposal_path.write_text(canonical(proposal))
    common=['--database',str(tmp_path/'common.sqlite'),'--proposal-ledger',str(tmp_path/'api.sqlite'),
        '--semantic-ledger',str(tmp_path/'semantic.sqlite'),'--fit-ledger',str(tmp_path/'fit.sqlite')]
    baseline=tmp_path/'baseline.json'; advice=tmp_path/'advice.json'; candidate=tmp_path/'candidate.json'
    assert module.main([*common,'--output',str(baseline),'fit','--dataset',str(dataset),'--protocol',str(protocol_path)])==0
    assert module.main([*common,'--output',str(advice),'proposal','--experiment-receipt',str(baseline),'--mock-response',str(proposal_path)])==0
    assert module.main([*common,'--output',str(candidate),'fit','--dataset',str(dataset),'--protocol',str(protocol_path),'--advice-receipt',str(advice)])==0
    status=tmp_path/'status.json'; before=(tmp_path/'common.sqlite').read_bytes()
    assert module.main([*common,'--output',str(status),'status'])==0
    assert (tmp_path/'common.sqlite').read_bytes()==before
    assert json.loads(status.read_text())['budget']['total_reserved_actions']==3
    assert module.validation_report(json.loads(candidate.read_text()))['partition']=='validation'
    assert candidate.stat().st_mode & 0o777==0o600
    with pytest.raises(FileExistsError):
        module.main([*common,'--output',str(candidate),'status'])


@pytest.mark.parametrize('provider', ['openrouter', 'ollama'])
def test_provider_tokens_accounted_once_including_inner_cache(tmp_path, development, monkeypatch, provider):
    from cryptoforge.research_resource_budget import ZERO_TOKENS
    dataset, protocol, proposal = development
    report = run_experiment(dataset, protocol, tmp_path/'fit.sqlite')['reports']['validation']['diagnostics']
    calls = []; model = DEFAULT_MODEL if provider == 'openrouter' else 'local-model'
    def transport(url, payload=None, headers=None, timeout=None):
        calls.append(url)
        if url.endswith('/models'): return {'data': [{'id': model, 'pricing': {'prompt': '0', 'completion': '0'}}]}
        if provider == 'openrouter':
            return {'model': model, 'choices': [{'finish_reason': 'stop', 'message': {'content': canonical(proposal)}}],
                    'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15}}
        return {'model': model, 'done': True, 'done_reason': 'stop', 'message': {'content': canonical(proposal)},
                'prompt_eval_count': 12, 'eval_count': 3}
    monkeypatch.setenv('CRYPTOFORGE_OPENROUTER_API_KEY', 'synthetic-key')
    monkeypatch.setattr(module, 'FreeAdvisor', lambda **kwargs: FreeAdvisor(**kwargs, transport=transport))
    monkeypatch.setattr(module,'run_provider_worker',in_process_provider_fixture)
    research = coordinator(tmp_path); first = research.propose(report, provider=provider, model=model)
    expected = {'input_tokens': 12, 'output_tokens': 3, 'total_tokens': 15}
    assert first['invocation_resources']['tokens'] == expected
    assert research.budget.snapshot()['resources']['provider_tokens_known_subtotal'] == expected
    calls_before = len(calls)
    assert research.propose(report, provider=provider, model=model)['invocation_resources']['tokens'] == ZERO_TOKENS
    reuse = module.ResearchCoordinator(tmp_path/'reuse-common.sqlite', proposal_ledger=tmp_path/'api.sqlite',
        semantic_ledger=tmp_path/'semantic.sqlite', fit_ledger=tmp_path/'fit.sqlite')
    cached = reuse.propose(report, provider=provider, model=model)
    assert cached['result']['advice']['api_cached'] and cached['invocation_resources']['tokens'] == ZERO_TOKENS
    assert len(calls) == calls_before


def test_sdk_fixture_usage_is_never_external_consumption(tmp_path, sdk_request, response):
    from cryptoforge.research_resource_budget import ZERO_TOKENS
    assert response['usage']['input_tokens'] > 0
    research = coordinator(tmp_path); call = research.semantic_fixture(sdk_request, response)
    assert call['invocation_resources']['tokens'] == ZERO_TOKENS
    assert research.budget.snapshot()['resources']['provider_tokens_known_subtotal'] == ZERO_TOKENS


def test_cli_resource_policy_rejects_fit_before_inner_journal(tmp_path, development):
    from cryptoforge.research_resource_budget import DEFAULT_RESOURCES
    dataset, protocol, _ = development
    config = tmp_path/'resources.json'; config.write_text(canonical({**DEFAULT_RESOURCES, 'total_wall_ms': 1}))
    frozen = tmp_path/'protocol.json'; frozen.write_text(canonical(protocol))
    common = ['--database', str(tmp_path/'common.sqlite'), '--proposal-ledger', str(tmp_path/'api.sqlite'),
        '--semantic-ledger', str(tmp_path/'semantic.sqlite'), '--fit-ledger', str(tmp_path/'fit.sqlite'), '--resource-policy', str(config)]
    assert module.main([*common, '--output', str(tmp_path/'denied.json'), 'fit', '--dataset', str(dataset), '--protocol', str(frozen)]) == 1
    assert not (tmp_path/'fit.sqlite').exists()
    assert module.main([*common, '--output', str(tmp_path/'status.json'), 'status']) == 0
    receipt = json.loads((tmp_path/'status.json').read_text())
    assert receipt['budget']['resources']['policy']['total_wall_ms'] == 1
    assert receipt['budget']['total_reserved_actions'] == 0
