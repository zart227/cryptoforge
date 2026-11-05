from datetime import UTC,datetime
import hashlib,json
from pathlib import Path
import urllib.request

import pytest

from cryptoforge.feeder_selected_sync_observation import local_getter,observe_selected_sync
from cryptoforge.local_source_provenance import canonical,digest

NOW=datetime(2030,1,2,12,tzinfo=UTC)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    import cryptoforge.feeder_selected_sync_observation as module
    root=tmp_path/'root';cycle='cycle-'+'a'*32;folder=root/'cycles'/cycle/'run';folder.mkdir(parents=True)
    raw=canonical({'pairs':['AAA/USDT','BBB/USDT']});(folder/'selected-universe.json').write_bytes(raw)
    report={'first_missing_stage':'selected_sync','effect':'unknown_stage_effect',
            'retained_files':{'run/selected-universe.json':{'sha256':digest(raw),'bytes':len(raw)}}}
    monkeypatch.setattr(module,'inspect_incomplete_feeder',lambda *args,**kwargs:report)
    return {'root':str(root)},cycle,report,folder


def getter(table,query):
    if table=='bot_health':rows=[{'component':'supabase_market_sync','status':'ok','observed_at':'2030-01-02T11:59:00+00:00'}]
    else:
        sym=query['symbol'][3:];pair=sym[:-4]+'/USDT'
        if table=='market_tickers':rows=[{'pair':pair,'symbol':sym,'observed_at':'2030-01-02T11:59:00+00:00','updated_at':'2030-01-02T11:59:01+00:00'}]
        else:rows=[{'pair':pair,'symbol':sym,'timeframe':'5m','open_time':'2030-01-02T11:50:00+00:00',
                   'close_time':'2030-01-02T11:55:00+00:00','ingested_at':'2030-01-02T11:56:00+00:00','updated_at':'2030-01-02T11:56:00+00:00'}]
    return rows,hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def run(setup,fn=getter):
    ref,cycle,_,_=setup
    return observe_selected_sync(ref,cycle,get=fn,clock=lambda:NOW)


def test_current_observation_preserves_stage_uncertainty_and_data(setup):
    report=run(setup)
    assert report['local_rest_requests']==5 and len(report['observations'])==2
    assert report['historical_effect']=='unknown' and not report['historical_stage_execution_proved']
    assert not report['retry_authorized'] and not report['database_instance_binding_proved']
    assert report['observations'][0]['pair']=='AAA/USDT'


def test_missing_rows_are_not_interpreted_as_failed_stage(setup):
    report=run(setup,lambda *_:([],hashlib.sha256(b'[]').hexdigest()))
    assert all(not x['ticker']['rows'] and not x['latest_closed_candle']['rows'] for x in report['observations'])
    assert report['historical_effect']=='unknown'


def test_selected_snapshot_tamper_or_wrong_stage_fails(setup):
    _,_,report,folder=setup
    (folder/'selected-universe.json').write_bytes(canonical({'pairs':['CCC/USDT']}))
    with pytest.raises(ValueError,match='universe changed'):run(setup)
    report['first_missing_stage']='select'
    with pytest.raises(ValueError,match='selected-sync stage'):run(setup)


def test_row_identity_extra_fields_and_future_close_fail(setup):
    def bad_identity(table,query):
        rows,pin=getter(table,query)
        if table=='market_tickers':rows[0]['pair']='OTHER/USDT'
        return rows,pin
    with pytest.raises(ValueError,match='row identity'):run(setup,bad_identity)
    def extra(table,query):
        rows,pin=getter(table,query)
        if table=='market_tickers':rows[0]['secret']='not permitted'
        return rows,pin
    with pytest.raises(ValueError,match='unexpected ticker fields'):run(setup,extra)
    def future(table,query):
        rows,pin=getter(table,query)
        if table=='market_candles':rows[0]['close_time']='2030-01-02T12:05:00+00:00'
        return rows,pin
    with pytest.raises(ValueError,match='not closed'):run(setup,future)


def test_cycle_drift_between_before_and_after_rejected(setup,monkeypatch):
    import cryptoforge.feeder_selected_sync_observation as module
    _,_,report,_=setup;second={**report,'retained_files':{}}
    calls=iter((report,second));monkeypatch.setattr(module,'inspect_incomplete_feeder',lambda *args,**kwargs:next(calls))
    with pytest.raises(ValueError,match='changed during observation'):run(setup)


def test_loopback_origin_and_tables_are_strict(monkeypatch):
    with pytest.raises(ValueError,match='loopback'):local_getter('https://example.com','key')
    with pytest.raises(ValueError,match='loopback'):local_getter('http://user:pw@localhost:54321','key')
    get=local_getter('http://127.0.0.1:54321','private-test-token')
    with pytest.raises(ValueError,match='allowlist'):get('trade_decisions',{})


def test_getter_uses_get_no_redirect_and_does_not_return_headers(monkeypatch):
    captured=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'[]'
    class Opener:
        def open(self,req,timeout):captured.append((req,timeout));return Response()
    handlers=[]
    def make_opener(*args):handlers.extend(args);return Opener()
    monkeypatch.setattr(urllib.request,'build_opener',make_opener)
    data,pin=local_getter('http://127.0.0.1:54321','private-test-token')('market_tickers',{'limit':'1'})
    assert data==[] and pin==hashlib.sha256(b'[]').hexdigest()
    assert captured[0][0].get_method()=='GET' and captured[0][0].full_url.startswith('http://127.0.0.1:54321/')
    assert isinstance(handlers[0],urllib.request.ProxyHandler) and handlers[0].proxies=={}
    assert 'private-test-token' not in str((data,pin))


def test_getter_rejects_duplicate_json_keys(monkeypatch):
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'[{"pair":"A","pair":"B"}]'
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(ValueError,match='duplicate source JSON field'):
        local_getter('http://127.0.0.1:54321','private-test-token')('market_tickers',{'limit':'1'})


def test_unbounded_or_tampered_response_does_not_return_report(setup):
    with pytest.raises(ValueError,match='bounded local observation'):
        run(setup,lambda *_:([{},{}],'a'*64))
    with pytest.raises(ValueError,match='bounded local observation'):
        run(setup,lambda *_:([],'not-a-hash'))
