"""Synthetic full v3 phase/API accounting with no external provider or keys."""
import sqlite3
import pytest
from test_llm_research_requests import report
from test_llm_exchange_audit import response, SECRET
from test_llm_existing_advisor_cli import setup
from cryptoforge import llm_existing_advisor_v3_cli as cli
from cryptoforge import llm_audited_provider_v3 as capture
from cryptoforge import llm_prompt_preflight as prompt


@pytest.mark.parametrize('failed',[False,True])
def test_v3_common_and_inner_accounting_share_one_synthetic_transport(tmp_path,monkeypatch,failed):
    research,root=setup(tmp_path);before=research.budget.snapshot();calls=[]
    monkeypatch.delenv('CRYPTOFORGE_OPENROUTER_API_KEY',raising=False)
    # A simulated input proof is local to this test. Public behavior without it
    # is separately tested to refuse before any reservation or credential read.
    monkeypatch.setattr(prompt,'require_verified_limit',lambda required:None)
    def fake_http(url,payload=None,headers=None,timeout=30):
        calls.append((url,payload))
        if payload is None:
            return 200,capture.canonical({'data':[{'id':capture.CANDIDATE_MODEL,
                'pricing':{'prompt':'0','completion':'0'}}]}).encode()
        def change(body):
            body['model']=capture.CANDIDATE_MODEL
            if failed:body['choices'][0]['finish_reason']='length'
        return 200,response(change=change)
    monkeypatch.setattr(capture,'_http',fake_http)
    def fake_worker(adapter,diagnostics,directory,binding,**kwargs):
        directory.mkdir(mode=0o700);prepared=adapter.preflight(diagnostics)
        capture.files._write(directory,'attempt.json',{'binding':binding,'implementation':capture._LOADED,
            'policy':capture.POLICY,'request_payload_sha256':capture.digest(prepared['payload'])})
        data={'report':diagnostics,'settings':{'provider':'openrouter','model':adapter.model,
            'ollama_url':adapter.ollama_url,'parameters':list(adapter.parameters),'timeout':3,
            'api_key':SECRET,'jobpilot_env':None},'wall_seconds':3,'directory':str(directory),
            'binding':binding,'implementation':capture._LOADED}
        try:
            result=capture._evaluate(data);status='completed';return result
        except BaseException:
            status='failed';raise
        finally:
            capture.files._write(directory,'outcome.json',{'status':status})
    monkeypatch.setattr(capture,'_run_worker',fake_worker)
    if failed:
        with pytest.raises(RuntimeError):cli.propose_existing(research,report(),audit_root=root)
        with pytest.raises(ValueError,match='no automatic retry'):cli.propose_existing(research,report(),audit_root=root)
    else:
        first=cli.propose_existing(research,report(),audit_root=root)
        second=cli.propose_existing(research,report(),audit_root=root)
        assert first['original_exchange_verified'] and not first['result']['advice']['api_cached']
        assert second['coordinator_cached'] and second['original_exchange_verified']
    after=research.budget.snapshot()
    assert after['total_reserved_actions']==before['total_reserved_actions']+1
    assert len(calls)==2 and calls[1][1]['max_completion_tokens']==2048
    assert 'max_tokens' not in calls[1][1]
    with sqlite3.connect(research.paths['proposal']) as db:
        assert db.execute('SELECT status FROM advisor_requests').fetchall()==[('failed' if failed else 'completed',)]
    assert after['statuses']['failed' if failed else 'completed']>=1
