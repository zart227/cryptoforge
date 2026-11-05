import base64
from copy import deepcopy
from datetime import UTC,datetime,timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from cryptoforge.local_source_provenance import canonical,digest,parse,read_file
from cryptoforge.reference_sources import INTERVAL_MS,MANDATORY,normalize_observation,request_url,source_pairs
from cryptoforge.reference_source_ledger import FLAGS,SQL,ReferenceLedger,ReferencePolicy,audit_reference_ledger,file_sha

NOW=datetime(2026,10,23,12,0,30,tzinfo=UTC)


class Clock:
    def __init__(self):self.now=NOW
    def __call__(self):return self.now
    def advance(self,seconds):self.now+=timedelta(seconds=seconds)


def observation(pair,anchor,before,after,*,code=0,status=200,revision=False):
    rows=[]
    for i in range(120):
        opened=anchor-INTERVAL_MS*(i+1)
        rows.append([str(opened),'100','102','99','100.5' if revision and i==1 else '101','10','1000'])
    response=dict(retCode=code,retMsg='OK',result=dict(category='spot',symbol=pair.replace('/',''),list=rows),
                  retExtInfo={},time=int(after.timestamp()*1000))
    raw=canonical(response)
    return dict(pair=pair,anchor_ms=anchor,url=request_url(pair,anchor),prepared_at=before.isoformat(),
                completed_at=after.isoformat(),elapsed_seconds=(after-before).total_seconds(),http_status=status,error_type=None,
                raw_body_base64=base64.b64encode(raw).decode(),raw_body_sha256=digest(raw))


def mutate(obs,change):
    obs=deepcopy(obs);value=parse(base64.b64decode(obs['raw_body_base64']));change(value)
    raw=canonical(value);obs['raw_body_base64']=base64.b64encode(raw).decode();obs['raw_body_sha256']=digest(raw)
    return obs


class Client:
    def __init__(self,clock,*,failed=None,revision=False):self.clock=clock;self.calls=[];self.failed=failed;self.revision=revision
    def fetch(self,pair,anchor):
        self.calls.append(pair);before=self.clock();self.clock.advance(.05)
        return observation(pair,anchor,before,self.clock(),code=10006 if pair==self.failed else 0,revision=self.revision)


@pytest.fixture(autouse=True)
def available_disk(monkeypatch):
    monkeypatch.setattr('cryptoforge.reference_source_ledger.shutil.disk_usage',lambda path:SimpleNamespace(free=10*1024**3))


def artifact():
    from cryptoforge.model_training import FEATURE_NAMES
    return canonical(dict(model_family='pure-python-logistic',model_version='synthetic-reference-model',
        trained_at=(NOW-timedelta(days=1)).isoformat(),pairs=['BTC/USDT','ETH/USDT','SOL/USDT'],feature_names=list(FEATURE_NAMES),
        weights=[0.0]*7,means=[0.0]*7,stds=[1.0]*7,bias=-1.0,
        config=dict(timeframe='5m',input_candle_state='closed_only',feature_calculation_contract='bounded-window-candle-v1',
                    feature_lookback_candles=120,horizon_candles=3,target_version='fixed-future-return-v1',
                    fit_information_end=(NOW-timedelta(days=2)).isoformat(),evaluation_information_end=(NOW-timedelta(days=1)).isoformat())))


def make(tmp_path,clock,*,model=False,policy=None,pairs=()):
    return ReferenceLedger.create(tmp_path/'ledger',pairs=pairs,policy=policy or ReferencePolicy(maximum_events=100,maximum_versions=1000,maximum_forecasts=30,maximum_database_bytes=4*1024**2),
                                  artifact_raw=artifact() if model else None,clock=clock)


def ref(ledger):return ledger.receipt()['reference']


def test_reference_pairs_do_not_depend_on_dynamic_selection():
    assert source_pairs([])==list(MANDATORY)
    assert source_pairs(['SOL/USDT'])==['BTC/USDT','ETH/USDT','SOL/USDT']
    assert source_pairs(['ETH/USDT','BTC/USDT','ETH/USDT'])==list(MANDATORY)
    with pytest.raises(ValueError):source_pairs(['BTC/USDT:USDT'])


def test_original_closed_source_ids_numeric_strings_and_observation_times():
    anchor=int(NOW.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
    obs=observation('BTC/USDT',anchor,NOW,NOW+timedelta(seconds=.1))
    r=normalize_observation(obs)
    assert r['status']=='ready' and len(r['rows'])==120
    assert all(row['known_at']==obs['completed_at'] for row in r['rows'])
    assert r['rows'][-1]['open_ms']==anchor-INTERVAL_MS
    assert r['rows'][0]['raw_row'][1]=='100'
    assert '?category=spot&' in obs['url'] and 'end='+str(anchor-INTERVAL_MS) in obs['url']


@pytest.mark.parametrize('change',[
    lambda j:j['result'].update(category='linear'),lambda j:j['result'].update(symbol='ETHUSDT'),
    lambda j:j.update(time=int((NOW+timedelta(days=1)).timestamp()*1000)),
    lambda j:j['result']['list'].pop(),lambda j:j['result']['list'].reverse(),
    lambda j:j['result']['list'][0].__setitem__(0,str(int(j['result']['list'][0][0])+INTERVAL_MS)),
    lambda j:j['result']['list'][1].__setitem__(0,j['result']['list'][0][0]),
    lambda j:j['result']['list'][0].__setitem__(1,'NaN'),
    lambda j:j['result']['list'][0].__setitem__(1,'0'),
    lambda j:j['result']['list'][0].__setitem__(3,'103'),
    lambda j:j['result']['list'][0].__setitem__(5,'-1'),
    lambda j:j['result']['list'][0].append('unexpected'),
])
def test_bad_public_inputs_cannot_be_used(change):
    anchor=int(NOW.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
    with pytest.raises(ValueError):normalize_observation(mutate(observation('BTC/USDT',anchor,NOW,NOW),change))


@pytest.mark.parametrize('field,value', [('url','https://api.binance.com/'),('elapsed_seconds',float('nan')),
    ('elapsed_seconds',True),('http_status',True),('raw_body_base64','!notbase64'),('raw_body_sha256','0'*64),
    ('completed_at',(NOW-timedelta(days=1)).isoformat()),('error_type','contains password=details')])
def test_bad_original_transport_metadata_rejected(field,value):
    anchor=int(NOW.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
    obs=observation('BTC/USDT',anchor,NOW,NOW);obs[field]=value
    with pytest.raises(ValueError):normalize_observation(obs)


def test_ledger_first_seen_versions_and_warm_resume(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);client=Client(clock)
    first=ledger.poll(client);assert client.calls==list(MANDATORY)
    assert first['versions']==240 and first['latest_status']==dict.fromkeys(MANDATORY,'ready')
    original=sqlite3.connect(ledger.path).execute('SELECT source_id,version,known_at,event_seq FROM versions ORDER BY source_id LIMIT 1').fetchone()
    clock.advance(300)
    resumed=ReferenceLedger.open(first['reference'],clock=clock);resumed.poll(Client(clock))
    assert resumed.receipt()['versions']==242
    db=sqlite3.connect(resumed.path)
    assert db.execute('SELECT source_id,version,known_at,event_seq FROM versions WHERE source_id=? AND version=?',original[:2]).fetchone()==original
    db.close()
    audited=audit_reference_ledger(ref(resumed),clock=clock)
    assert audited['versions_checked']==242 and audited['source_trace_integrity_pass'] is True
    assert audited['original_source_forecast_linkage_pass'] is False
    assert all(audited[k] is False for k in FLAGS)


def test_same_bar_cache_reuse_never_refetches_or_freshens_known_at(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);first=ledger.poll(Client(clock));client=Client(clock)
    clock.advance(10);second=ledger.poll(client)
    assert second['reused_original_observation'] is True and client.calls==[]
    assert second['reference']==first['reference'] and second['poll_completed_at']==first['poll_completed_at']


def test_revision_history_preserves_old_version_and_time(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);ledger.poll(Client(clock));old_ref=ref(ledger)
    clock.advance(300);ledger.poll(Client(clock,revision=True))
    assert ledger.receipt()['versions']==244
    with pytest.raises(ValueError,match='database pin'):ReferenceLedger.open(old_ref,clock=clock)
    assert audit_reference_ledger(ref(ledger),clock=clock)['versions_checked']==244


def test_failed_btc_is_retained_and_blocks_eth_forecast_and_rate_retry(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True)
    receipt=ledger.poll(Client(clock,failed='BTC/USDT'))
    assert receipt['latest_status']==dict.fromkeys(MANDATORY,'unavailable')
    assert receipt['versions']==0
    with pytest.raises(ValueError,match='mandatory'):ledger.forecast('ETH/USDT')
    clock.advance(300);client=Client(clock);receipt=ledger.poll(client)
    assert receipt['reused_original_observation'] and client.calls==[]
    assert audit_reference_ledger(ref(ledger),clock=clock)['source_trace_integrity_pass']


def test_all_declared_source_failures_are_recorded(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock)
    class Offline:
        def fetch(self,*args):raise OSError('never copy private OS/proxy error text')
    result=ledger.poll(Offline())
    assert result['latest_status']==dict.fromkeys(MANDATORY,'unavailable')
    db=sqlite3.connect(ledger.path);records=db.execute("SELECT payload FROM events WHERE kind='source_response'").fetchall();db.close()
    assert len(records)==2 and all(b'private OS' not in row[0] for row in records)
    assert audit_reference_ledger(ref(ledger),clock=clock)['versions_checked']==0


def test_forecast_is_computed_from_original_bound_windows_and_keeps_negative_predictions(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True);ledger.poll(Client(clock))
    result=ledger.forecast('ETH/USDT');p=result['payload']
    assert result['stored'] and p['long_probability']<.5
    assert len(p['features'])==7 and len(p['sources'])==2
    assert all(s['row_count']==120 and len(s['versions_sha256'])==64 for s in p['sources'])
    assert all(stamp<=p['predicted_at'] for stamp in [s['known_at'] for s in p['sources']])
    assert ledger.forecast('ETH/USDT')['stored'] is False
    audited=audit_reference_ledger(ref(ledger),clock=clock)
    assert audited['forecasts_checked']==1 and audited['original_source_forecast_linkage_pass'] is True
    assert all(audited[k] is False for k in FLAGS)


def test_stale_source_forecast_and_unfrozen_artifact_are_rejected(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True);ledger.poll(Client(clock));clock.advance(601)
    with pytest.raises(ValueError,match='stale'):ledger.forecast('BTC/USDT')
    other=make(tmp_path/'other',clock)
    with pytest.raises(ValueError,match='not frozen'):other.forecast('BTC/USDT')


def test_malformed_source_still_has_original_failed_evidence(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True)
    class Malformed(Client):
        def fetch(self,pair,anchor):return mutate(super().fetch(pair,anchor),lambda j:j['result']['list'].pop())
    result=ledger.poll(Malformed(clock))
    assert result['latest_status']==dict.fromkeys(MANDATORY,'invalid')
    with pytest.raises(ValueError):ledger.forecast('BTC/USDT')
    assert audit_reference_ledger(ref(ledger),clock=clock)['source_trace_integrity_pass']


def test_prospective_window_and_manifest_cannot_be_adopted_late(tmp_path):
    clock=Clock();start=NOW+timedelta(seconds=10)
    ledger=ReferenceLedger.create(tmp_path/'source',start=start,end=NOW+timedelta(days=1),clock=clock)
    with pytest.raises(ValueError,match='not open'):ledger.poll(Client(clock))
    clock.advance(11);ledger.poll(Client(clock))
    assert audit_reference_ledger(ref(ledger),clock=clock)['scope']=='prospective'
    with pytest.raises(ValueError):ReferenceLedger.create(tmp_path/'late',start=NOW,end=NOW+timedelta(days=1),clock=clock)


def test_original_window_can_be_audited_after_end(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);ledger.poll(Client(clock));reference=ref(ledger)
    clock.advance(32*86400)
    assert audit_reference_ledger(reference,clock=clock)['events_checked']==4


def test_partial_original_poll_cannot_be_retried_or_counted_complete(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock)
    class Death:
        def fetch(self,*args):raise SystemExit(42)
    with pytest.raises(SystemExit):ledger.poll(Death())
    reference=ref(ledger);other=ReferenceLedger.open(reference,clock=clock);client=Client(clock)
    with pytest.raises(ValueError,match='incomplete'):other.poll(client)
    assert client.calls==[]
    with pytest.raises(ValueError,match='incomplete'):audit_reference_ledger(reference,clock=clock)


def test_limits_rollback_version_writes_before_exposing_complete_source(tmp_path):
    clock=Clock();policy=ReferencePolicy(maximum_events=100,maximum_versions=100,maximum_forecasts=10,maximum_database_bytes=4*1024**2)
    ledger=make(tmp_path,clock,policy=policy)
    with pytest.raises(ValueError,match='version budget'):ledger.poll(Client(clock))
    r=ledger.receipt();assert r['versions']==0 and r['events']==1 and r['pending'] is not None


def test_hard_sqlite_page_budget_is_not_relaxed(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,policy=ReferencePolicy(maximum_database_bytes=65536))
    with pytest.raises(sqlite3.OperationalError):ledger.poll(Client(clock))
    assert ledger.path.stat().st_size<=65536


def test_disk_reserve_is_preserved_before_any_request(tmp_path,monkeypatch):
    clock=Clock();ledger=make(tmp_path,clock);client=Client(clock)
    monkeypatch.setattr('cryptoforge.reference_source_ledger.shutil.disk_usage',lambda path:SimpleNamespace(free=1024**3))
    with pytest.raises(ValueError,match='reserve'):ledger.poll(client)
    assert client.calls==[]


def test_source_bytes_cannot_be_changed_through_immutable_tables(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);ledger.poll(Client(clock))
    db=sqlite3.connect(ledger.path)
    for sql in ['UPDATE events SET kind=kind','DELETE FROM events','UPDATE versions SET known_at=known_at','DELETE FROM versions']:
        with pytest.raises(sqlite3.IntegrityError,match='immutable'):db.execute(sql)
        db.rollback()
    db.close()


def test_forged_first_seen_projection_is_detected_against_original_events(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);ledger.poll(Client(clock));reference=ref(ledger)
    db=sqlite3.connect(ledger.path);db.execute('DROP TRIGGER versions_no_update')
    db.execute('UPDATE versions SET known_at=?',((NOW-timedelta(days=1)).isoformat(),))
    db.execute(SQL['versions_no_update']);db.commit();db.close()
    reference['database_sha256']=file_sha(ledger.path,ledger.policy.maximum_database_bytes)
    with pytest.raises(ValueError,match='first-seen'):audit_reference_ledger(reference,clock=clock)


def test_rehashed_false_forecast_is_rejected_by_source_replay(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True);ledger.poll(Client(clock));ledger.forecast('ETH/USDT');reference=ref(ledger)
    db=sqlite3.connect(ledger.path);seq,raw,previous=db.execute("SELECT seq,payload,previous FROM events WHERE kind='forecast'").fetchone()
    p=parse(raw);p['payload']['long_probability']=.99
    head=digest(canonical(dict(sequence=seq,kind='forecast',payload=p,previous_sha256=previous)))
    db.execute('DROP TRIGGER events_no_update');db.execute('UPDATE events SET payload=?,sha=? WHERE seq=?',(canonical(p),head,seq));db.execute(SQL['events_no_update'])
    db.execute('UPDATE state SET head=? WHERE id=1',(head,));db.commit();db.close()
    reference.update(database_sha256=file_sha(ledger.path,ledger.policy.maximum_database_bytes),head_sha256=head)
    with pytest.raises(ValueError,match='forecast linkage'):audit_reference_ledger(reference,clock=clock)


def test_future_model_information_is_rejected_before_creating_namespace(tmp_path):
    clock=Clock();a=parse(artifact());a['trained_at']=(NOW+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError,match='information unavailable'):ReferenceLedger.create(tmp_path/'bad',artifact_raw=canonical(a),clock=clock)
    assert not (tmp_path/'bad').exists()


def test_offline_cli_audit_has_no_authentication_or_as_of_override(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);ledger.poll(Client(clock));path=tmp_path/'reference.json';path.write_bytes(canonical(ref(ledger)))
    script=Path(__file__).resolve().parents[1]/'scripts/capture_reference_sources.py'
    result=subprocess.run([sys.executable,str(script),'audit','--reference-file',str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['versions_checked']==240
    result=subprocess.run([sys.executable,str(script),'probe','--output',str(tmp_path/'bad'),'--as-of',NOW.isoformat()],capture_output=True,text=True,timeout=10)
    assert result.returncode==2 and not (tmp_path/'bad').exists()


@pytest.mark.parametrize('offset',[-1,1])
def test_source_metadata_outside_actual_request_span_is_retained_as_invalid(tmp_path,offset):
    clock=Clock();ledger=make(tmp_path,clock,model=True)
    class Foreign(Client):
        def fetch(self,pair,anchor):
            obs=super().fetch(pair,anchor)
            field='prepared_at' if offset<0 else 'completed_at'
            obs[field]=(clock()+timedelta(seconds=offset)).isoformat()
            return obs
    receipt=ledger.poll(Foreign(clock))
    assert receipt['latest_status']==dict.fromkeys(MANDATORY,'invalid') and receipt['versions']==0
    with pytest.raises(ValueError):ledger.forecast('ETH/USDT')
    assert audit_reference_ledger(ref(ledger),clock=clock)['source_trace_integrity_pass']


def test_forecast_clock_cannot_move_back_before_durable_source_completion(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True);ledger.poll(Client(clock));clock.advance(-.01)
    with pytest.raises(ValueError,match='backwards'):ledger.forecast('ETH/USDT')


def test_lock_contention_does_not_fetch_or_mutate_sources(tmp_path):
    import fcntl
    clock=Clock();ledger=make(tmp_path,clock);client=Client(clock)
    with (ledger.root/'writer.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):ledger.poll(client)
    assert client.calls==[] and ledger.receipt()['events']==0


def test_runtime_drift_during_request_leaves_an_explicit_incomplete_poll(tmp_path,monkeypatch):
    from cryptoforge import reference_source_ledger as module
    clock=Clock();ledger=make(tmp_path,clock);paths=module._runtime_paths();copy=tmp_path/'source-copy.py';copy.write_bytes(paths['reference_sources.py'].read_bytes())
    paths['reference_sources.py']=copy;monkeypatch.setattr(module,'_runtime_paths',lambda:paths)
    class Changed(Client):
        def fetch(self,pair,anchor):
            copy.write_text('source changed during request')
            return super().fetch(pair,anchor)
    with pytest.raises(ValueError,match='runtime changed'):ledger.poll(Changed(clock))
    db=sqlite3.connect(ledger.path)
    assert db.execute('SELECT pending FROM state').fetchone()[0] is not None
    assert db.execute('SELECT count(*) FROM versions').fetchone()[0]==0
    db.close()


@pytest.mark.parametrize('times',[[NOW,NOW+timedelta(seconds=11)],
                                [NOW,NOW+timedelta(seconds=1),NOW+timedelta(seconds=11)]])
def test_registration_completion_after_start_never_has_a_ready_pin(tmp_path,times):
    calls=iter(times)
    with pytest.raises(ValueError,match='missed original start'):
        ReferenceLedger.create(tmp_path/'late',start=NOW+timedelta(seconds=10),end=NOW+timedelta(days=1),clock=lambda:next(calls))
    assert not (tmp_path/'late/registered.json').exists()


def test_source_artifact_is_frozen_and_cannot_be_added_to_existing_history(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True);ledger.poll(Client(clock));reference=ref(ledger)
    a=parse(artifact());a['bias']=2.0;(ledger.root/'artifact.json').write_bytes(canonical(a))
    with pytest.raises(ValueError,match='artifact differs'):ReferenceLedger.open(reference,clock=clock)


def test_rehashed_missing_mandatory_response_is_not_a_complete_poll(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);ledger.poll(Client(clock));reference=ref(ledger)
    db=sqlite3.connect(ledger.path);seq,raw,previous=db.execute("SELECT seq,payload,previous FROM events WHERE kind='poll_complete'").fetchone()
    p=parse(raw);p['responses']=p['responses'][1:]
    head=digest(canonical(dict(sequence=seq,kind='poll_complete',payload=p,previous_sha256=previous)))
    db.execute('DROP TRIGGER events_no_update');db.execute('UPDATE events SET payload=?,sha=? WHERE seq=?',(canonical(p),head,seq));db.execute(SQL['events_no_update'])
    db.execute('UPDATE state SET head=?',(head,));db.commit();db.close()
    reference.update(database_sha256=file_sha(ledger.path,ledger.policy.maximum_database_bytes),head_sha256=head)
    with pytest.raises(ValueError,match='mandatory source response'):audit_reference_ledger(reference,clock=clock)


def test_real_process_death_before_public_reply_cannot_be_retried(tmp_path):
    script='''import json,os,sys
from pathlib import Path
from cryptoforge.reference_source_ledger import ReferenceLedger
ledger=ReferenceLedger.create(Path(sys.argv[1]))
class Death:
 def fetch(self,*args):os._exit(42)
ledger.poll(Death())
'''
    root=tmp_path/'killed'
    result=subprocess.run([sys.executable,'-c',script,str(root)],capture_output=True,text=True,timeout=10)
    assert result.returncode==42,result.stderr
    manifest=parse((root/'manifest.json').read_bytes());registration=(root/'registered.json').read_bytes()
    db=sqlite3.connect(root/'source.sqlite');head,pending=db.execute('SELECT head,pending FROM state').fetchone();db.close()
    assert pending is not None
    reference=dict(root=str(root),manifest_sha256=digest(canonical(manifest)),registration_sha256=digest(registration),
                   database_sha256=file_sha(root/'source.sqlite',manifest['policy']['maximum_database_bytes']),head_sha256=head)
    ledger=ReferenceLedger.open(reference)
    class NoRequest:
        def fetch(self,*args):raise AssertionError('retry unexpectedly reached provider')
    with pytest.raises(ValueError,match='incomplete'):ledger.poll(NoRequest())


def test_fixed_public_transport_has_a_killable_wall_and_byte_bound(monkeypatch):
    from cryptoforge.reference_sources import PublicReferenceClient
    captured=[];anchor=int(datetime.now(UTC).timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
    expected=observation('BTC/USDT',anchor,datetime.now(UTC),datetime.now(UTC))
    def bounded(command,sql,**kwargs):
        captured.append((command,sql,kwargs));return canonical(expected)
    monkeypatch.setattr('cryptoforge.local_source_observer.bounded_process',bounded)
    assert PublicReferenceClient().fetch('BTC/USDT',anchor)==expected
    command,sql,kwargs=captured[0]
    assert kwargs==dict(maximum_bytes=128*1024,maximum_seconds=5) and sql==''
    assert 'secret' not in ' '.join(command).lower() and 'authorization' not in ' '.join(command).lower()


def test_single_http_read_is_bounded_and_credential_free(monkeypatch):
    import cryptoforge.reference_sources as module
    captures=[]
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):captures.append(limit);return b'x'*(limit+100)
    class Opener:
        def open(self,request,timeout):
            assert request.full_url.startswith('https://api.bybit.com/v5/market/kline?category=spot&')
            assert not any(k.lower() in ('authorization','apikey','cookie') for k in request.headers)
            assert timeout==3
            return Response()
    monkeypatch.setattr(module,'build_opener',lambda *args:Opener())
    anchor=int(datetime.now(UTC).timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
    value=module._fetch_once('BTC/USDT',anchor)
    assert captures==[65537] and len(base64.b64decode(value['raw_body_base64']))==65536
    assert normalize_observation(value)['status']=='unavailable'


def test_public_redirects_never_follow_another_host():
    from cryptoforge.reference_sources import _NoRedirect
    from urllib.error import HTTPError
    with pytest.raises(HTTPError):
        _NoRedirect().redirect_request(SimpleNamespace(full_url=request_url('BTC/USDT',1800000000000)),None,302,'redirect',{},'https://example.com/private')


def test_recent_read_does_not_freshen_an_old_closed_bar(tmp_path):
    clock=Clock();clock.advance(260);ledger=make(tmp_path,clock,model=True)
    ledger.poll(Client(clock));clock.advance(360)
    # Observation is only six minutes old; the last closed bar is >10 minutes old.
    with pytest.raises(ValueError,match='stale'):ledger.forecast('ETH/USDT')


def test_clock_rollback_inside_request_leaves_incomplete_poll(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock);clock.advance(10)
    class Rollback(Client):
        def fetch(self,pair,anchor):
            response=super().fetch(pair,anchor);self.clock.advance(-1);return response
    with pytest.raises(ValueError,match='clock moved backwards'):ledger.poll(Rollback(clock))
    assert ledger.receipt()['pending'] is not None
    with pytest.raises(ValueError,match='incomplete'):audit_reference_ledger(ref(ledger),clock=clock)


@pytest.mark.parametrize('kind',['poll_complete','forecast'])
def test_rehashed_impossible_completion_or_stale_forecast_is_rejected(tmp_path,kind):
    clock=Clock();ledger=make(tmp_path,clock,model=True);ledger.poll(Client(clock))
    if kind=='forecast':ledger.forecast('ETH/USDT')
    reference=ref(ledger);db=sqlite3.connect(ledger.path)
    seq,raw,previous=db.execute('SELECT seq,payload,previous FROM events WHERE kind=?',(kind,)).fetchone()
    payload=parse(raw)
    if kind=='poll_complete':payload['completed_at']=NOW.isoformat()
    else:
        payload['payload']['predicted_at']=(NOW+timedelta(seconds=610)).isoformat()
        payload['recorded_at']=payload['payload']['predicted_at']
    head=digest(canonical(dict(sequence=seq,kind=kind,payload=payload,previous_sha256=previous)))
    db.execute('DROP TRIGGER events_no_update')
    db.execute('UPDATE events SET payload=?,sha=? WHERE seq=?',(canonical(payload),head,seq))
    db.execute(SQL['events_no_update']);db.execute('UPDATE state SET head=?',(head,));db.commit();db.close()
    reference.update(database_sha256=file_sha(ledger.path,ledger.policy.maximum_database_bytes),head_sha256=head)
    with pytest.raises(ValueError,match='poll time|unavailable reference'):audit_reference_ledger(reference,clock=clock)


@pytest.mark.parametrize('status',[403,429])
def test_ip_rate_limit_stops_remaining_requests_and_records_explicit_skips(tmp_path,status):
    clock=Clock();ledger=make(tmp_path,clock)
    class RateLimit(Client):
        def fetch(self,pair,anchor):
            response=super().fetch(pair,anchor);response.update(http_status=status,error_type='http_error');return response
    client=RateLimit(clock);receipt=ledger.poll(client)
    assert client.calls==['BTC/USDT'] and receipt['versions']==0
    db=sqlite3.connect(ledger.path)
    payloads=[parse(row[0]) for row in db.execute("SELECT payload FROM events WHERE kind='source_response' ORDER BY seq")];db.close()
    assert [p['request_performed'] for p in payloads]==[True,False]
    skipped=payloads[-1]['observation']
    assert skipped['error_type']=='upstream_cooldown' and skipped['raw_body_base64']=='' and skipped['http_status'] is None
    clock.advance(300);client=Client(clock)
    assert ledger.poll(client)['reused_original_observation'] is True and client.calls==[]
    assert audit_reference_ledger(ref(ledger),clock=clock)['source_trace_integrity_pass']


def test_non_rate_btc_failure_still_blocks_a_fresh_eth_forecast(tmp_path):
    clock=Clock();ledger=make(tmp_path,clock,model=True)
    class PartialFailure(Client):
        def fetch(self,pair,anchor):
            response=super().fetch(pair,anchor)
            if pair=='BTC/USDT':response.update(http_status=502,error_type='http_error')
            return response
    client=PartialFailure(clock);receipt=ledger.poll(client)
    assert client.calls==list(MANDATORY) and receipt['latest_status']=={'BTC/USDT':'unavailable','ETH/USDT':'ready'}
    with pytest.raises(ValueError,match='mandatory'):ledger.forecast('ETH/USDT')
    assert audit_reference_ledger(ref(ledger),clock=clock)['source_trace_integrity_pass']
