"""Exact usage, original journal binding, duplicates and explicit unknowns."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import stat

import pytest
from test_llm_research_requests import report,Advisor
from test_llm_exchange_audit import response,SECRET
from cryptoforge import research_exchange_usage as m


def legacy(tmp_path,usage=None,model=None):
    path=tmp_path/'api.sqlite';adapter=m.capture.FreeAdvisor(model=model or m.capture.advisor_module.DEFAULT_MODEL,parameters=('l2','threshold'))
    payload=Advisor().propose(report());payload.update(provider=adapter.provider,model=adapter.model)
    if usage is not None:payload['usage']=usage
    m.capture.ResearchRequests(path).propose(adapter,report(),execute=lambda:payload);return path


def captured(tmp_path,monkeypatch,*,raw=None,status=200):
    path=tmp_path/'api.sqlite';journal=m.capture.ResearchRequests(path);adapter=m.capture.FreeAdvisor(parameters=('l2','threshold'))
    binding=m.capture._journal_binding(journal,adapter,report());directory=tmp_path/'attempt';directory.mkdir(mode=0o700)
    m.capture.files._write(directory,'attempt.json',{'binding':binding,'implementation':m.capture.implementation(),'policy':m.capture.POLICY,
        'request_payload_sha256':m.digest(adapter.preflight(report())['payload'])})
    def http(url,payload=None,headers=None,timeout=30):
        if payload is None:return 200,m.canonical({'data':[{'id':adapter.model,'pricing':{'prompt':'0','completion':'0'}}]}).encode()
        return status,response() if raw is None else raw
    monkeypatch.setattr(m.capture,'_http',http)
    data={'report':report(),'settings':{'provider':adapter.provider,'model':adapter.model,'ollama_url':adapter.ollama_url,
        'parameters':list(adapter.parameters),'timeout':3,'api_key':SECRET,'jobpilot_env':None},'wall_seconds':3,
        'implementation':m.capture.implementation(),'directory':str(directory),'binding':binding}
    def execute():
        state='failed'
        try:
            result=m.capture._evaluate(data);state='completed';return result
        finally:m.capture.files._write(directory,'outcome.json',{'status':state})
    try:journal.propose(adapter,report(),execute=execute)
    except m.capture.AdvisorUnavailable:pass
    return path,directory


def test_legacy_usage_is_retained_without_inventing_original_wire_or_native_cost(tmp_path,monkeypatch):
    path=legacy(tmp_path,{'prompt_tokens':4000,'completion_tokens':73,'total_tokens':4073});before=path.read_bytes()
    monkeypatch.setattr(m.capture.subprocess,'Popen',lambda *a,**k:pytest.fail('no processes'))
    monkeypatch.setattr(m.capture.advisor_module,'jobpilot_credentials',lambda *a,**k:pytest.fail('no keys'))
    result=m.reconcile([path]);s=result['journals'][0]
    assert s['known_native_token_subtotals']['total_tokens']==4073 and s['unknown_token_attempts_by_field']['total_tokens']==0
    assert s['completed_payloads_without_provided_original_wire']==1 and s['original_exchange_captures']==0
    assert s['known_native_credit_subtotal']=='0' and s['known_credit_attempts']==0 and s['unknown_credit_attempts']==1
    assert result['cross_journal_global_total'] is None and not result['unknown_values_mean_zero']
    assert before==path.read_bytes() and not list(tmp_path.glob('*-shm'))


@pytest.mark.parametrize('usage',[None,{}, {'prompt_tokens':True,'completion_tokens':-1,'total_tokens':None}])
def test_missing_invalid_usage_remains_unknown_not_zero(tmp_path,usage):
    path=legacy(tmp_path,usage);s=m.reconcile([path])['journals'][0]
    assert s['unknown_token_attempts_by_field']=={k:1 for k in m.TOKEN_FIELDS}
    assert s['records'][0]['usage']=={k:None for k in m.TOKEN_FIELDS}


def test_rejected_nonzero_free_charge_and_usage_are_counted_once_across_copied_packs(tmp_path,monkeypatch):
    raw=response(change=lambda b:b['usage'].update(cost='0.02'));path,directory=captured(tmp_path,monkeypatch,raw=raw)
    copied=tmp_path/'copied';shutil.copytree(directory,copied)
    result=m.reconcile([path],[directory,copied]);s=result['journals'][0]
    assert s['records'][0]['API_status']=='failed' and s['known_native_token_subtotals']['total_tokens']==150
    assert s['known_native_credit_subtotal']=='0.02' and s['known_credit_attempts']==1
    assert result['duplicate_capture_copies_not_counted_twice']==1 and result['captured_attempts']==1
    assert s['original_exchange_captures']==1 and not result['native_credit_values_are_USD_invoice']


@pytest.mark.parametrize('raw',[b'bad private non-JSON response',response(change=lambda b:b['choices'][0]['message'].update(tool_calls=[{'name':'shell'}]))])
def test_failed_requests_with_outer_errors_or_tools_keep_each_known_native_field(tmp_path,monkeypatch,raw):
    path,directory=captured(tmp_path,monkeypatch,raw=raw);row=m.reconcile([path],[directory])['journals'][0]['records'][0]
    assert row['API_status']=='failed' and row['wire_capture_available']
    assert row['usage']['total_tokens']==(None if raw.startswith(b'bad') else 150)
    assert 'private non-JSON response' not in m.canonical(row)


def test_completed_normalized_counter_conflict_with_original_body_is_refused(tmp_path,monkeypatch):
    path,directory=captured(tmp_path,monkeypatch)
    with sqlite3.connect(path) as db:
        key,payload=db.execute('SELECT key,payload FROM advisor_requests').fetchone();value=json.loads(payload)
        value['usage']['total_tokens']=999
        db.execute('UPDATE advisor_requests SET payload=?,payload_sha256=? WHERE key=?',(m.canonical(value),m.digest(value),key))
    with pytest.raises(ValueError,match='usage_disagree'):m.reconcile([path],[directory])


@pytest.mark.parametrize('change',['capture_sha256','exchange_manifest_sha256','legacy_upgrade'])
def test_original_completed_cache_reference_must_bind_the_provided_wire(tmp_path,monkeypatch,change):
    path,directory=captured(tmp_path,monkeypatch)
    with sqlite3.connect(path) as db:
        payload=json.loads(db.execute('SELECT payload FROM advisor_requests').fetchone()[0])
        if change=='legacy_upgrade':payload.pop('exchange_capture')
        else:payload['exchange_capture'][change]='f'*64
        db.execute('UPDATE advisor_requests SET payload=?,payload_sha256=?',(m.canonical(payload),m.digest(payload)))
    with pytest.raises(ValueError):m.reconcile([path],[directory])


def test_SQLite_authorizer_confirms_only_five_readonly_statements_and_no_schema_mutation(tmp_path,monkeypatch):
    path=legacy(tmp_path,{'total_tokens':10});real=m.sqlite3.connect;statements=[]
    writes={sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE,sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_DROP_TABLE,sqlite3.SQLITE_ALTER_TABLE}
    def connect(database_uri,*a,**k):
        assert database_uri.endswith('?mode=ro&immutable=1') and k['uri'] is True
        db=real(database_uri,*a,**k)
        db.set_authorizer(lambda op,*rest:sqlite3.SQLITE_DENY if op in writes else sqlite3.SQLITE_OK)
        db.set_trace_callback(statements.append);return db
    monkeypatch.setattr(m.sqlite3,'connect',connect)
    result=m.reconcile([path]);assert len(statements)==5 and result['journals'][0]['explicit_SQL_statements']==5


def test_capture_from_another_API_path_cannot_be_attributed_to_a_copied_journal(tmp_path,monkeypatch):
    path,directory=captured(tmp_path,monkeypatch);copied=tmp_path/'copied.sqlite';shutil.copy2(path,copied)
    with pytest.raises(ValueError,match='original_API_journal'):m.reconcile([copied],[directory])


def test_conflicting_local_outcome_copies_are_refused(tmp_path,monkeypatch):
    path,directory=captured(tmp_path,monkeypatch);copied=tmp_path/'copy';shutil.copytree(directory,copied)
    (copied/'outcome.json').write_text(m.canonical({'status':'failed'}))
    with pytest.raises(ValueError,match='conflicting_capture'):m.reconcile([path],[directory,copied])


def test_separate_journals_have_separate_subtotals_and_no_global_sum(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    first=legacy(a,{'total_tokens':10});second=legacy(b,{'total_tokens':20})
    result=m.reconcile([first,second]);assert [s['known_native_token_subtotals']['total_tokens'] for s in result['journals']]==[10,20]
    assert result['cross_journal_global_total'] is None


@pytest.mark.parametrize('change',['key','payload','policy','sidecar','public','symlink','missing'])
def test_native_corruption_aliases_and_unstable_journals_refused_without_writes(tmp_path,change):
    path=legacy(tmp_path,{'total_tokens':10})
    if change in ('key','payload','policy'):
        with sqlite3.connect(path) as db:
            db.execute({'key':"UPDATE advisor_requests SET key='wrong'",'payload':"UPDATE advisor_requests SET payload='{}'",'policy':'DELETE FROM request_policy'}[change])
    elif change=='sidecar':Path(str(path)+'-wal').write_bytes(b'')
    elif change=='public':path.chmod(0o644)
    elif change=='symlink':
        target=tmp_path/'target.sqlite';path.rename(target);path.symlink_to(target)
    else:path.unlink()
    before=path.read_bytes() if path.exists() else None
    with pytest.raises(ValueError):m.reconcile([path])
    assert (path.read_bytes() if path.exists() else None)==before


def test_model_identifiers_and_reports_are_not_copied_as_raw_text_to_accounting(tmp_path):
    path=legacy(tmp_path,{'total_tokens':10},model=SECRET);result=m.reconcile([path])
    assert SECRET not in m.canonical(result) and 'rationale' not in m.canonical(result)
    assert result['journals'][0]['records'][0]['requested_model_sha256']==m.digest(SECRET)


def test_CLI_output_exclusive_private_and_no_raw_error_text(tmp_path,capsys):
    path=legacy(tmp_path,{'total_tokens':10});output=tmp_path/'usage.json'
    assert m.main(['--journal',str(path),'--output',str(output)])==0
    raw=output.read_bytes();assert stat.S_IMODE(output.stat().st_mode)==0o600
    assert m.main(['--journal',str(path),'--output',str(output)])==2 and output.read_bytes()==raw
    with pytest.raises(SystemExit):m.main(['--journal',str(path),'--output',str(path)])
    absent=tmp_path/'secret-name.sqlite';assert m.main(['--journal',str(absent),'--output',str(tmp_path/'absent.json')])==2
    assert 'secret-name' not in capsys.readouterr().out and not absent.exists()
