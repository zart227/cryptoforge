from datetime import timedelta
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_reference_source_ledger import Clock, Client, artifact
from cryptoforge.local_source_provenance import canonical, digest, parse
from cryptoforge.reference_source_ledger import FLAGS, ReferenceLedger, ReferencePolicy
from cryptoforge.reference_source_reader import (
    ROLES, ReferenceMarketReader, audit_frame, capture_frame, freeze_reader, load_reader,
    inference_envelope, prepare_inference_artifact, audit_inference_artifact,
)


@pytest.fixture(autouse=True)
def enough_disk(monkeypatch):
    monkeypatch.setattr('cryptoforge.reference_source_reader.shutil.disk_usage', lambda path: SimpleNamespace(free=10*1024**3))


def source(tmp_path, clock, *, prospective=False, model=True):
    return ReferenceLedger.create(tmp_path/'source', clock=clock, artifact_raw=artifact() if model else None,
        start=clock()+timedelta(seconds=60) if prospective else None,
        end=clock()+timedelta(hours=1),
        policy=ReferencePolicy(maximum_events=100, maximum_versions=1000, maximum_forecasts=30, maximum_database_bytes=4*1024**2))


def receipt(ledger):
    return ledger.receipt()['reference']


def setup(tmp_path, *, prospective=False, model=True):
    clock=Clock();ledger=source(tmp_path, clock, prospective=prospective, model=model)
    reader=freeze_reader(tmp_path/'reader', receipt(ledger), clock=clock) if prospective else None
    if prospective:clock.advance(60)
    client=Client(clock);ledger.poll(client)
    if model:
        ledger.forecast('BTC/USDT');ledger.forecast('ETH/USDT')
    frame=capture_frame(tmp_path/'frame', receipt(ledger), reader_reference=reader, clock=clock)
    return clock,ledger,reader,frame,client


def test_three_roles_receive_identical_source_frame_and_original_feature_inputs(tmp_path):
    from cryptoforge.model_training import extract_features
    clock,ledger,contract,frame,client=setup(tmp_path, prospective=True)
    rows=[]
    for role in ROLES:
        reader=ReferenceMarketReader.open(frame, role=role, reader_reference=contract, clock=clock)
        status=reader.status()
        assert status['closed_candles_ready'] is True and status['scope']=='registered_reference_inputs_only'
        assert status['frame_sha256']==frame['frame_sha256'] and status['role']==role
        assert all(status[k] is False for k in FLAGS) and status['worker_prediction_batch_available'] is False
        candles=reader.read_candles('ETH/USDT');rows.append(candles)
        features=extract_features(candles,[r.volume for r in candles])
        forecasts=reader.original_forecasts()
        assert len(forecasts)==2 and all(f['entry_decision_available'] is False for f in forecasts)
        eth=next(f for f in forecasts if f['original']['payload']['pair']=='ETH/USDT')
        assert list(features)==eth['original']['payload']['features']
        assert eth['original']['payload']['long_probability']<.5 and eth['usable_price_input_now'] is True
        assert 'would_enter' not in eth['original']['payload']
    assert rows[0]==rows[1]==rows[2] and len(rows[0])==120
    assert client.calls==['BTC/USDT','ETH/USDT']
    assert audit_frame(frame, reader_reference=contract)['source_rows_checked']==240


def test_diagnostic_source_cannot_register_or_be_adopted(tmp_path):
    clock,ledger,_,frame,_=setup(tmp_path)
    with pytest.raises(ValueError,match='prospective'):freeze_reader(tmp_path/'bad', receipt(ledger), clock=clock)
    other=tmp_path/'other';other.mkdir();new=source(other,clock,prospective=True)
    contract=freeze_reader(other/'reader',receipt(new),clock=clock)
    with pytest.raises(ValueError,match='scope'):audit_frame(frame,reader_reference=contract)
    assert not (tmp_path/'bad').exists()


def test_missing_artifact_remains_a_source_reader_without_fake_predictions(tmp_path):
    clock,_,contract,frame,_=setup(tmp_path,model=False)
    reader=ReferenceMarketReader.open(frame,role='control',clock=clock)
    assert len(reader.read_candles('BTC/USDT'))==120 and reader.original_forecasts()==[]
    assert audit_frame(frame)['original_forecasts_checked']==0


def test_reread_never_refreshes_candle_or_forecast_times(tmp_path):
    clock,_,_,frame,_=setup(tmp_path)
    reader=ReferenceMarketReader.open(frame,role='candidate',clock=clock)
    before=reader.read_candles('ETH/USDT');original=deepcopy(reader.original_forecasts())
    clock.advance(610)
    assert reader.status()['closed_candles_ready'] is False
    with pytest.raises(ValueError,match='stale'):reader.read_candles('ETH/USDT')
    later=reader.original_forecasts()
    assert [f['original'] for f in later]==[f['original'] for f in original]
    assert all(f['usable_price_input_now'] is False for f in later)
    assert before[-1].cache_observed_at<clock()-timedelta(seconds=600)


def test_failure_in_btc_blocks_fresh_eth_without_dropping_evidence(tmp_path):
    clock=Clock();ledger=source(tmp_path,clock)
    class Failed(Client):
        def fetch(self,pair,anchor):
            response=super().fetch(pair,anchor)
            if pair=='BTC/USDT':response.update(http_status=502,error_type='http_error')
            return response
    ledger.poll(Failed(clock));frame=capture_frame(tmp_path/'frame',receipt(ledger),clock=clock)
    reader=ReferenceMarketReader.open(frame,role='stress',clock=clock)
    assert reader.status()['source_status']=={'BTC/USDT':'unavailable','ETH/USDT':'ready'}
    with pytest.raises(ValueError,match='mandatory'):reader.read_candles('ETH/USDT')
    assert audit_frame(frame)['source_rows_checked']==120


def test_first_seen_versions_are_resolved_from_global_source_history(tmp_path):
    clock=Clock();ledger=source(tmp_path,clock);ledger.poll(Client(clock))
    first=parse((ledger.root/'manifest.json').read_bytes())
    clock.advance(300);ledger.poll(Client(clock,revision=True))
    frame=capture_frame(tmp_path/'frame',receipt(ledger),clock=clock)
    value=parse((Path(frame['root'])/'frame.json').read_bytes())
    rows=value['windows']['ETH/USDT']['derived']['rows']
    assert first['pairs']==['BTC/USDT','ETH/USDT']
    assert any(row['first_seen_at']<row['known_at'] for row in rows)
    assert all(row['first_seen_event_sequence']<=value['windows']['ETH/USDT']['event_seq'] for row in rows)
    assert audit_frame(frame)['source_frame_integrity_pass'] is True


@pytest.mark.parametrize('kwargs',[{'timeframe':'1m'},{'limit':119},{'limit':True},{'limit':121}])
def test_reader_cannot_change_frozen_feature_window(tmp_path,kwargs):
    clock,_,_,frame,_=setup(tmp_path)
    reader=ReferenceMarketReader.open(frame,role='candidate',clock=clock)
    with pytest.raises(ValueError,match='bounded120'):reader.read_candles('ETH/USDT',**kwargs)
    with pytest.raises(ValueError,match='frozen pair'):reader.read_candles('SOL/USDT')


@pytest.mark.parametrize('role',['live','unknown','',None])
def test_undeclared_role_is_rejected_before_reading_source(tmp_path,role):
    with pytest.raises(ValueError,match='role'):ReferenceMarketReader.open({},role=role)


def test_pending_original_poll_never_creates_a_frame(tmp_path):
    clock=Clock();ledger=source(tmp_path,clock)
    class Death:
        def fetch(self,*args):raise SystemExit(42)
    with pytest.raises(SystemExit):ledger.poll(Death())
    with pytest.raises(ValueError,match='incomplete'):capture_frame(tmp_path/'bad',receipt(ledger),clock=clock)
    assert not (tmp_path/'bad').exists()


def test_full_frame_and_disk_budgets_fail_before_output(tmp_path,monkeypatch):
    clock=Clock();ledger=source(tmp_path,clock);ledger.poll(Client(clock));ref=receipt(ledger)
    monkeypatch.setattr('cryptoforge.reference_source_reader.MAX_FRAME_BYTES',4096)
    with pytest.raises(ValueError,match='payload budget'):capture_frame(tmp_path/'bad-size',ref,clock=clock)
    assert not (tmp_path/'bad-size').exists()
    monkeypatch.setattr('cryptoforge.reference_source_reader.MAX_FRAME_BYTES',4*1024*1024)
    monkeypatch.setattr('cryptoforge.reference_source_reader.shutil.disk_usage',lambda p:SimpleNamespace(free=2048*1024**2))
    with pytest.raises(ValueError,match='reserve'):capture_frame(tmp_path/'bad-disk',ref,clock=clock)
    assert not (tmp_path/'bad-disk').exists()


def test_registration_after_start_or_after_observations_is_rejected(tmp_path):
    clock=Clock();ledger=source(tmp_path,clock,prospective=True);clock.advance(60)
    with pytest.raises(ValueError,match='before reader registration'):freeze_reader(tmp_path/'late',receipt(ledger),clock=clock)
    ledger.poll(Client(clock))
    with pytest.raises(ValueError,match='before reader registration'):freeze_reader(tmp_path/'late-poll',receipt(ledger),clock=clock)


def test_reader_cannot_substitute_another_source_namespace(tmp_path):
    clock=Clock();ledger=source(tmp_path,clock,prospective=True)
    contract=freeze_reader(tmp_path/'reader',receipt(ledger),clock=clock)
    other=tmp_path/'other';other.mkdir();replacement=source(other,clock,prospective=True)
    clock.advance(60);replacement.poll(Client(clock))
    with pytest.raises(ValueError,match='scope'):capture_frame(tmp_path/'bad',receipt(replacement),reader_reference=contract,clock=clock)
    assert not (tmp_path/'bad').exists()


@pytest.mark.parametrize('target',['first_seen','probability','head','original_source','roles','scope','unexpected_entry'])
def test_rehashed_frame_tampering_is_rejected_by_source_replay(tmp_path,target):
    clock,_,_,reference,_=setup(tmp_path);root=Path(reference['root']);frame=parse((root/'frame.json').read_bytes())
    if target=='first_seen':frame['windows']['ETH/USDT']['derived']['rows'][0]['first_seen_at']=(clock()-timedelta(days=1)).isoformat()
    elif target=='probability':frame['forecasts'][0]['payload']['long_probability']=.99
    elif target=='head':frame['source_head_sha256']='f'*64
    elif target=='original_source':frame['windows']['ETH/USDT']['observation']['raw_body_sha256']='a'*64
    elif target=='roles':frame['roles']=['candidate']
    elif target=='unexpected_entry':frame['would_enter']=True
    else:frame['scope']='registered_reference_inputs_only'
    raw=canonical(frame);(root/'frame.json').write_bytes(raw)
    completion=parse((root/'complete.json').read_bytes());completion['frame_sha256']=digest(raw)
    completed=canonical(completion);(root/'complete.json').write_bytes(completed)
    forged=dict(reference,frame_sha256=digest(raw),completion_sha256=digest(completed))
    with pytest.raises(ValueError,match='replay differs|schema/clock/scope|cannot be adopted'):audit_frame(forged)


def test_delivered_frame_is_immutable_and_independent_of_later_source_polls(tmp_path):
    clock,ledger,_,frame,_=setup(tmp_path)
    reader=ReferenceMarketReader.open(frame,role='candidate',clock=clock);rows=reader.read_candles('ETH/USDT')
    clock.advance(300);ledger.poll(Client(clock,revision=True))
    assert reader.read_candles('ETH/USDT')==rows
    # New consumers must have the original source pin, never adopt its changed DB.
    with pytest.raises(ValueError,match='database pin'):ReferenceMarketReader.open(frame,role='control',clock=clock)
    path=Path(frame['root'])/'frame.json';path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='pin differs'):reader.status()


def test_source_window_end_blocks_consumption_but_allows_offline_audit(tmp_path):
    clock,_,contract,frame,_=setup(tmp_path,prospective=True)
    reader=ReferenceMarketReader.open(frame,role='control',reader_reference=contract,clock=clock)
    clock.advance(3600)
    assert reader.status()['source_window_open'] is False
    with pytest.raises(ValueError,match='mandatory'):reader.read_candles('BTC/USDT')
    assert audit_frame(frame,reader_reference=contract)['source_frame_integrity_pass'] is True


def test_reader_cannot_move_before_original_frame_observation(tmp_path):
    clock,_,_,frame,_=setup(tmp_path)
    reader=ReferenceMarketReader.open(frame,role='candidate',clock=clock);clock.advance(-1)
    with pytest.raises(ValueError,match='backwards'):reader.status()
    with pytest.raises(ValueError,match='future source frame'):ReferenceMarketReader.open(frame,role='stress',clock=clock)


def test_cli_offline_inspection_is_source_bound_and_has_no_as_of(tmp_path):
    clock,_,_,frame,_=setup(tmp_path)
    path=tmp_path/'reference.json';path.write_bytes(canonical(frame))
    command=[sys.executable,'scripts/read_reference_sources.py','audit','--frame-reference-file',str(path)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['source_rows_checked']==240
    rejected=subprocess.run(command+['--as-of',clock().isoformat()],capture_output=True,text=True,timeout=15)
    assert rejected.returncode!=0 and 'unrecognized arguments' in rejected.stderr


def test_clock_rollback_after_a_later_read_is_detected(tmp_path):
    clock,_,_,frame,_=setup(tmp_path)
    reader=ReferenceMarketReader.open(frame,role='candidate',clock=clock)
    clock.advance(10);reader.status();clock.advance(-1)
    with pytest.raises(ValueError,match='backwards'):reader.read_candles('ETH/USDT')


def test_reader_does_not_poll_or_refresh_a_source_during_reads(tmp_path,monkeypatch):
    clock,_,_,frame,_=setup(tmp_path)
    def forbidden(*args):raise AssertionError('a read unexpectedly contacted the venue')
    monkeypatch.setattr('cryptoforge.reference_sources.PublicReferenceClient.fetch',forbidden)
    before=(Path(frame['root'])/'frame.json').read_bytes()
    for role in ROLES:
        reader=ReferenceMarketReader.open(frame,role=role,clock=clock)
        assert len(reader.read_candles('BTC/USDT'))==120
        reader.original_forecasts();reader.status()
    assert (Path(frame['root'])/'frame.json').read_bytes()==before


def test_frame_too_late_to_complete_has_no_completion_pin(tmp_path,monkeypatch):
    import cryptoforge.reference_source_reader as module
    clock=Clock();ledger=source(tmp_path,clock);ledger.poll(Client(clock))
    original=module._write_new
    def delayed(path,value):
        pin=original(path,value)
        if path.name=='frame.json':clock.advance(76)
        return pin
    monkeypatch.setattr(module,'_write_new',delayed)
    with pytest.raises(ValueError,match='completion drifted'):capture_frame(tmp_path/'late',receipt(ledger),clock=clock)
    assert (tmp_path/'late/frame.json').exists() and not (tmp_path/'late/complete.json').exists()


@pytest.mark.parametrize('late_step',['reader.json','registered.json'])
def test_reader_registration_durable_deadline_never_adopts_late_setup(tmp_path,monkeypatch,late_step):
    import cryptoforge.reference_source_reader as module
    clock=Clock();ledger=source(tmp_path,clock,prospective=True);original=module._write_new
    def late(path,value):
        pin=original(path,value)
        if path.name==late_step:clock.advance(61)
        return pin
    monkeypatch.setattr(module,'_write_new',late)
    with pytest.raises(ValueError,match='missed original source start'):freeze_reader(tmp_path/'late',receipt(ledger),clock=clock)
    assert not (tmp_path/'late/registered.json').exists()


def test_source_runtime_drift_during_frame_capture_is_not_completed(tmp_path,monkeypatch):
    import cryptoforge.reference_source_reader as module
    clock=Clock();ledger=source(tmp_path,clock);ledger.poll(Client(clock))
    paths=module._runtime_paths();copied=tmp_path/'backend.py';copied.write_bytes(paths['backend.py'].read_bytes());paths['backend.py']=copied
    monkeypatch.setattr(module,'_runtime_paths',lambda:dict(paths))
    original=module._snapshot
    def changed(*args,**kwargs):
        value=original(*args,**kwargs);copied.write_bytes(copied.read_bytes()+b'\n');return value
    monkeypatch.setattr(module,'_snapshot',changed)
    with pytest.raises(ValueError,match='runtime changed'):capture_frame(tmp_path/'drift',receipt(ledger),clock=clock)
    assert not (tmp_path/'drift/complete.json').exists()


def test_compact_artifact_preserves_original_bytes_parameters_and_probability(tmp_path):
    from cryptoforge.model_training import predict_probability
    original=parse(artifact());original['metrics']={'unused_diagnostic':'x'*300000}
    raw=canonical(original);result=prepare_inference_artifact(tmp_path/'inference',raw)
    assert result['original_bytes']>300000 and result['inference_bytes']<65536
    assert (tmp_path/'inference/original-artifact.json').read_bytes()==raw
    envelope=parse((tmp_path/'inference/artifact.json').read_bytes())
    assert envelope['inference_derivation']['original_artifact_sha256']==digest(raw)
    for name in ('weights','bias','means','stds','feature_names','pairs','model_version','trained_at'):
        assert envelope[name]==original[name]
    features=(.02,-.01,.1,1.4,.005,58.,.01)
    def probability(a):return predict_probability(features,a['weights'],a['bias'],a['means'],a['stds'])
    assert probability(original)==probability(envelope)
    assert 'metrics' not in envelope and result['live_model_publication_performed'] is False
    assert audit_inference_artifact(result)['inference_parameter_identity_pass'] is True
    with pytest.raises(FileExistsError):prepare_inference_artifact(tmp_path/'inference',raw)


@pytest.mark.parametrize('change',[
    lambda a:a['config'].update(input_candle_state='forming_allowed'),
    lambda a:a['config'].update(feature_lookback_candles=119),
    lambda a:a.update(target_version='cash_execution_v1'),
    lambda a:a['weights'].__setitem__(0,'0.1'),
    lambda a:a['stds'].__setitem__(0,0),
    lambda a:a['config'].pop('fit_information_end'),
    lambda a:a['config'].update(fit_information_end='2099-01-01T00:00:00+00:00'),
])
def test_compact_artifact_does_not_repair_unknown_or_conflicting_model_contracts(change):
    value=parse(artifact());change(value)
    with pytest.raises((ValueError,KeyError)):inference_envelope(canonical(value))


def test_compact_artifact_retains_model_pair_scope_and_generates_source_bound_forecasts(tmp_path):
    clock=Clock();original=parse(artifact());original['pairs']=['SOL/USDT'];original['metrics']={'large':'x'*100000}
    envelope=inference_envelope(canonical(original))
    ledger=ReferenceLedger.create(tmp_path/'envelope-source',pairs=['SOL/USDT'],artifact_raw=envelope,clock=clock)
    ledger.poll(Client(clock))
    with pytest.raises(ValueError,match='model scope'):ledger.forecast('BTC/USDT')
    forecast=ledger.forecast('SOL/USDT')
    frame=capture_frame(tmp_path/'envelope-frame',receipt(ledger),clock=clock)
    reader=ReferenceMarketReader.open(frame,role='control',clock=clock)
    assert len(reader.read_candles('SOL/USDT'))==120
    assert reader.original_forecasts()[0]['original']['forecast_id']==forecast['forecast_id']
    assert audit_frame(frame)['original_forecasts_checked']==1


@pytest.mark.parametrize('name',['original-artifact.json','artifact.json','complete.json'])
def test_inference_envelope_tampering_is_rejected(tmp_path,name):
    reference=prepare_inference_artifact(tmp_path/'inference',artifact())
    path=Path(reference['root'])/name;path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='derivation differs'):audit_inference_artifact(reference)


def test_reader_features_use_the_frozen_precision_without_changing_the_caller(tmp_path):
    from decimal import localcontext
    clock,_,_,frame,_=setup(tmp_path)
    reader=ReferenceMarketReader.open(frame,role='candidate',clock=clock)
    expected=next(f['original']['payload']['features'] for f in reader.original_forecasts()
        if f['original']['payload']['pair']=='ETH/USDT')
    with localcontext() as context:
        context.prec=6
        assert list(reader.features('ETH/USDT'))==expected
        assert context.prec==6
