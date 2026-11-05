from datetime import timedelta
from pathlib import Path
from dataclasses import asdict
import json
import pytest

from cryptoforge.paired_cash_rehearsal import PairedCashRehearsal,BoundedPaperPublicClient
from cryptoforge.local_source_provenance import canonical
from test_cash_worker_application import rules,PositiveClient
from test_reference_source_ledger import Clock,Client
from test_paper_wallet import config
from test_native_paper_archive_v2 import WORKER_POLICY
from test_paper_valuation_capture import raw_market

ENV=dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='synthetic-not-saved')


def setup(tmp_path,**changes):
    clock=Clock()
    values=dict(start=clock()+timedelta(seconds=1),end=clock()+timedelta(seconds=21),rules=rules(),
        configs={r:config() for r in ('candidate','control','stress')},worker_policy=WORKER_POLICY,
        closeout_seconds=5,backend_env=ENV,clock=clock,market=lambda pair:raw_market(clock,pair))
    values.update(changes)
    return PairedCashRehearsal.create(tmp_path/'runner',**values),clock


@pytest.mark.parametrize('positive',[False,True])
def test_whole_runner_polls_delivers_ticks_finalizes_and_independently_replays(tmp_path,positive):
    runner,clock=setup(tmp_path);ref=dict(runner.reference)
    result=runner.run(client=PositiveClient(clock) if positive else Client(clock),market=lambda pair:raw_market(clock,pair),sleeper=clock.advance)
    assert result['ticks_by_role']==dict(candidate=4,control=4,stress=4)
    assert result['missed_whole_runner_slots']==0
    for role,audit in result['independent_replays'].items():
        assert audit['full_worker_decision_replay_pass'] and audit['full_fifo_replay_pass']
        assert audit['fills_checked']==(2 if positive and role!='control' else 0)
    assert all(result[k] is False for k in ('paper_evidence_pass','economic_profitability_established','live_admission_granted'))
    reopened=PairedCashRehearsal.open(ref,clock=clock).inspect()
    assert reopened['pending_operation'] is None and reopened['terminal_exists']
    assert reopened['completed_operations']==20
    with pytest.raises(ValueError,match='single-use'):runner.run(client=Client(clock),sleeper=clock.advance)


def test_partial_component_operation_is_visible_and_never_retried(tmp_path,monkeypatch):
    from cryptoforge.reference_delivery import ReferenceDelivery
    runner,clock=setup(tmp_path)
    def fail(*a):raise OSError('unknown component commit')
    monkeypatch.setattr(ReferenceDelivery,'ingest',fail)
    with pytest.raises(OSError):runner.run(client=Client(clock),sleeper=clock.advance)
    state=runner.inspect();assert state['completed_operations']==1 and state['pending_operation']=='source_ingest'
    with pytest.raises(ValueError,match='single-use'):runner.run(client=Client(clock),sleeper=clock.advance)


@pytest.mark.parametrize('fault',['past','long','far','cloud','shared_exit'])
def test_registration_rejects_invalid_scope_before_any_namespace(tmp_path,fault):
    clock=Clock();change={}
    if fault=='past':change['start']=clock()-timedelta(seconds=1)
    if fault=='long':change['end']=clock()+timedelta(seconds=180)
    if fault=='far':change.update(start=clock()+timedelta(seconds=120),end=clock()+timedelta(seconds=140))
    if fault=='cloud':change['backend_env']=dict(SUPABASE_URL='https://example.supabase.co',SUPABASE_SERVICE_ROLE_KEY='synthetic')
    if fault=='shared_exit':change['worker_policy']={**WORKER_POLICY,'exits':{**WORKER_POLICY['exits'],'shared_exit_signal':True}}
    with pytest.raises(ValueError):setup(tmp_path,**change)
    assert not (tmp_path/'runner').exists()


def test_pins_in_memory_contract_and_journal_alias_are_rejected(tmp_path):
    runner,clock=setup(tmp_path);runner.manifest['poll_seconds']=1
    with pytest.raises(ValueError,match='registration'):runner.inspect()
    runner=PairedCashRehearsal.open(runner.reference,clock=clock)
    (runner.root/'journal').rmdir();other=tmp_path/'aliased';other.mkdir();(runner.root/'journal').symlink_to(other)
    with pytest.raises(ValueError,match='journal'):runner.run(client=Client(clock),sleeper=clock.advance)


@pytest.mark.parametrize('path,params',[
    ('/v5/order/create',dict(category='spot',symbol='BTCUSDT')),
    ('/v5/market/orderbook',dict(category='linear',symbol='BTCUSDT',limit=1)),
    ('/v5/market/instruments-info',dict(category='spot',symbol='SOLUSDT')),
])
def test_public_provider_rejects_order_nonspot_or_other_symbols_before_network(path,params):
    with pytest.raises(ValueError,match='public GET'):BoundedPaperPublicClient()._get_json(path,params)


def test_runtime_budget_and_resource_failure_do_not_start_source_poll(tmp_path,monkeypatch):
    runner,clock=setup(tmp_path)
    def unavailable(root):raise ValueError('resource reserve unavailable')
    monkeypatch.setattr('cryptoforge.paired_cash_rehearsal._resources',unavailable)
    client=Client(clock)
    with pytest.raises(ValueError,match='resource'):runner.run(client=client,sleeper=clock.advance)
    assert not client.calls and not list((runner.root/'journal').iterdir())


@pytest.mark.parametrize('fault',[None,'oversized','duplicate_json','retcode_pause','http_pause','retcode_10429'])
def test_public_reads_are_bounded_credential_free_and_rate_paused(monkeypatch,fault):
    import io
    from urllib.error import HTTPError
    import cryptoforge.paired_cash_rehearsal as module
    calls=[]
    class Response(io.BytesIO):
        status=200
        def read1(self,limit):return self.read(limit)
    raw=b'{"retCode":0}'
    if fault=='oversized':raw=b' '+b'0'*65536
    if fault=='duplicate_json':raw=b'{"retCode":0,"retCode":1}'
    if fault=='retcode_pause':raw=b'{"retCode":10006}'
    if fault=='retcode_10429':raw=b'{"retCode":10429}'
    class Opener:
        def open(self,request,timeout):
            calls.append(request.full_url);assert timeout==.6
            assert not any(k.lower() in ('authorization','apikey') for k in request.headers)
            if fault=='http_pause':raise HTTPError(request.full_url,429,'rate',{},None)
            return Response(raw)
    monkeypatch.setattr(module,'build_opener',lambda *args:Opener())
    monkeypatch.setattr(module,'_public_process',module._public_once)
    client=BoundedPaperPublicClient();args=('/v5/market/orderbook',dict(category='spot',symbol='BTCUSDT',limit=1))
    if fault in ('oversized','duplicate_json','http_pause'):
        with pytest.raises((ValueError,HTTPError)):client._get_json(*args)
    else:assert client._get_json(*args)['retCode']==(10006 if fault=='retcode_pause' else 10429 if fault=='retcode_10429' else 0)
    if fault in ('retcode_pause','http_pause','retcode_10429'):
        with pytest.raises(TimeoutError):client._get_json(*args)
        assert len(calls)==1
