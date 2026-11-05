from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import json
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

import cryptoforge.paper_worker_capture as capture
from cryptoforge.evidence_segments import canonical, digest
from cryptoforge.paper_worker_capture import CapturedPaperWorker, WorkerCapturePolicy, audit_worker_capture
from test_native_paper_archive import policy, WORKER_POLICY
from test_paper_capture_v3 import lifecycle, storage
from test_paper_wallet import START, Clock, config, market
from test_paper_valuation_capture import raw_market
from test_paper_capture_v4 import rehash


def budgets(**changes):
    return replace(WorkerCapturePolicy(maximum_predictions_per_tick=8, maximum_actions_per_tick=24,
        maximum_clock_calls_per_tick=64, maximum_market_requests_per_tick=4,
        maximum_exit_requests_per_tick=4), **changes)


def setup(tmp_path, **changes):
    clock = Clock();clock.now = START-timedelta(seconds=10)
    fields = dict(candidate_sha='a'*64, study_protocol_sha256='b'*64, role='candidate', config=config(),
        worker_policy=deepcopy(WORKER_POLICY), lifecycle=lifecycle(maximum_operations_per_poll=1),
        storage_policy=storage(maximum_events=1024, maximum_segment_events=64, maximum_record_bytes=32768,
            maximum_total_bytes=16*1024*1024), native_policy=policy(), capture_policy=budgets(),
        start=START, end=START+timedelta(seconds=20), market=lambda pair:raw_market(clock,pair), clock=clock)
    fields.update(changes)
    worker = CapturedPaperWorker.create(tmp_path/'worker-study', **fields)
    clock.now = START
    return worker, clock


def prediction(clock, opportunity='one', **changes):
    value = dict(candidate_sha256='a'*64, opportunity=opportunity, pair='AAA/USDT',
        predicted_at=clock.now.isoformat(), observed_at=clock.now.isoformat(), would_enter=True)
    value.update(changes)
    return value


def tick(worker, clock, rows=None):
    rows = [] if rows is None else rows
    return worker.tick(rows, source_id='source-batch', source_observed_at=clock.now,
        expected_source_sha256=digest(canonical(rows)))


def finish(worker, clock):
    clock.now = START+timedelta(seconds=20)
    worker.mark_endpoint({}, {})
    worker.terminate('completed')
    return worker.finalize()


def audit(worker, seal, **changes):
    fields = dict(expected_registration_sha256=worker.registration_sha256,
        expected_seal_sha256=seal['seal_sha256'], clock=lambda:START+timedelta(seconds=20))
    fields.update(changes)
    return audit_worker_capture(worker.root, **fields)


def records(worker, seal):
    return list(worker.log.iter_events(expected_head_sha256=seal['head_sha256'],expected_catalog_sha256=seal['catalog_sha256']))


def test_whole_worker_sources_actions_clocks_and_read_only_audit(tmp_path):
    worker, clock = setup(tmp_path)
    row = prediction(clock)
    assert tick(worker,clock,[row])['fills_processed'] == ['pending']
    clock.advance(5)
    assert tick(worker,clock,[row])['fills_processed'] == ['filled']
    clock.advance(5)
    worker._market = lambda pair:raw_market(clock,pair,price='95')
    assert tick(worker,clock)['new_intents'] == 0
    clock.advance(5)
    assert tick(worker,clock)['fills_processed'] == ['filled']
    seal = finish(worker,clock)
    before = {str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}
    result = audit(worker,seal)
    assert result['worker_source_trace_pass']
    assert result['ticks'] == 4 and result['endpoint_marks'] == 1
    assert result['market_requests'] == 4 and result['supplied_predictions'] == 2
    assert result['actions'] > 15
    assert all(result[k] is False for k in ('full_worker_decision_replay_pass','full_fifo_replay_pass',
        'coverage_evidence_pass','full_worker_or_host_qualified','paper_evidence_pass',
        'economic_profitability_established','live_admission_granted'))
    assert before == {str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}
    phases = {r['payload'].get('phase') for r in records(worker,seal)}
    assert {'tick','action','market','clock'} <= phases


def test_empty_cash_tick_is_captured_and_not_income(tmp_path):
    worker, clock = setup(tmp_path)
    assert tick(worker,clock)['market_observations'] == 0
    result = audit(worker,finish(worker,clock))
    assert result['ticks'] == 1 and result['market_requests'] == 0 and not result['paper_evidence_pass']


@pytest.mark.parametrize('role',['candidate','control','stress'])
def test_original_role_parent_and_runtime_are_bound(tmp_path,role):
    worker, clock = setup(tmp_path,role=role)
    tick(worker,clock)
    assert worker._source.manifest['source_protocol_sha256'] == worker.protocol_sha256
    assert worker.protocol['study_protocol_sha256'] == 'b'*64
    assert audit(worker,finish(worker,clock))['role'] == role


@pytest.mark.parametrize('change',['wrong_sha','future_batch','stale_batch','generator','oversize','conflict','decision_type','pair','credential'])
def test_invalid_input_batch_has_no_native_effect(tmp_path,change):
    worker, clock = setup(tmp_path)
    rows = [prediction(clock)]
    observed = clock.now
    if change == 'future_batch':observed += timedelta(seconds=1)
    if change == 'stale_batch':observed -= timedelta(seconds=31)
    if change == 'oversize':rows *= 9
    if change == 'conflict':rows.append(dict(rows[0],would_enter=False))
    if change == 'decision_type':rows[0]['would_enter'] = 'yes'
    if change == 'pair':rows[0]['pair'] = 'AAA/BTC'
    if change == 'credential':rows[0]['api_key'] = 'dummy-not-a-secret'
    pin = 'f'*64 if change == 'wrong_sha' else digest(canonical(rows))
    if change == 'generator':rows = iter(rows)
    with pytest.raises((ValueError,TypeError)):
        worker.tick(rows,source_id='source',source_observed_at=observed,expected_source_sha256=pin)
    assert worker._head()[0] == 1
    with worker._source.wallet._db() as db:assert db.execute('SELECT count(*) FROM intents').fetchone()[0] == 0


def test_native_market_error_is_retained_without_exception_message(tmp_path):
    worker, clock = setup(tmp_path)
    def unavailable(pair):raise ConnectionError('must-not-be-in-capture')
    worker._market = unavailable
    result = tick(worker,clock,[prediction(clock)])
    assert result['errors'] == {'AAA/USDT':'ConnectionError'}
    seal = finish(worker,clock)
    result = audit(worker,seal)
    assert result['failed_market_requests'] == 1
    assert 'must-not-be-in-capture' not in json.dumps(records(worker,seal))


@pytest.mark.parametrize('change',['normalized_only','wrong_pair','past_quote','future_quote','raw_forgery'])
def test_missing_or_false_raw_market_source_poison_tick(tmp_path,change):
    worker, clock = setup(tmp_path)
    def invalid(pair):
        if change == 'normalized_only':return market(clock,pair)
        if change == 'wrong_pair':return raw_market(clock,'BBB/USDT')
        original = clock.now
        if change == 'past_quote':clock.now -= timedelta(seconds=1)
        if change == 'future_quote':clock.now += timedelta(seconds=1)
        q,r = raw_market(clock,pair);clock.now = original
        if change == 'raw_forgery':q['bid'] = '999'
        return q,r
    worker._market = invalid
    with pytest.raises(ValueError):tick(worker,clock,[prediction(clock)])
    with pytest.raises(ValueError):tick(worker,clock)
    with pytest.raises(ValueError,match='unfinished'):
        CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)


def test_sealed_before_end_does_not_open_sources_or_seal(tmp_path,monkeypatch):
    worker, clock = setup(tmp_path)
    for path in [worker.root/'storage',worker.root/'native']:
        path.rename(path.with_name(path.name+'-hidden'))
    result = audit_worker_capture(worker.root,expected_registration_sha256=worker.registration_sha256,clock=clock)
    assert result['performance_hidden'] and not result['worker_source_trace_pass']


def test_resume_completed_tick_and_archived_dedup(tmp_path):
    worker, clock = setup(tmp_path)
    row = prediction(clock,would_enter=False)
    tick(worker,clock,[row]);clock.advance(5)
    worker = CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
        market=lambda pair:raw_market(clock,pair),clock=clock)
    assert tick(worker,clock,[row])['new_intents'] == 0
    result = audit(worker,finish(worker,clock))
    assert result['ticks'] == 2 and result['supplied_predictions'] == 2


@pytest.mark.parametrize('change',['cash','worker_event','compaction'])
def test_outside_native_mutation_blocks_before_tick(tmp_path,change):
    worker, clock = setup(tmp_path)
    if change == 'cash':
        with worker._source.wallet._db() as db:db.execute("UPDATE state SET value='101' WHERE key='cash'")
    elif change == 'worker_event':
        # Bypass only for the adversarial fixture.
        from cryptoforge.paper_worker import PaperWorker
        PaperWorker._event(worker._source.worker,{'outside':True})
    else:worker._source.compact()
    with pytest.raises(ValueError,match='uncaptured'):tick(worker,clock)
    assert worker._head()[0] == 1


def test_second_tick_same_slot_and_finalization_without_terminal_fail(tmp_path):
    worker, clock = setup(tmp_path)
    tick(worker,clock)
    with pytest.raises(ValueError,match='poll slot'):tick(worker,clock)
    with pytest.raises(ValueError,match='terminal'):worker.finalize()
    seal = finish(worker,clock)
    with pytest.raises(ValueError):CapturedPaperWorker.resume(worker.root,
        expected_registration_sha256=worker.registration_sha256,market=lambda pair:raw_market(clock,pair),clock=clock)
    assert audit(worker,seal)['worker_source_trace_pass']


@pytest.mark.parametrize('change',['capture_budget','events','lifecycle','disabled'])
def test_capacity_and_disabled_policy_rejected_before_creation(tmp_path,change):
    fields = {}
    if change == 'capture_budget':fields['capture_policy'] = budgets(maximum_predictions_per_tick=40)
    if change == 'events':fields['storage_policy'] = storage(maximum_events=512)
    if change == 'lifecycle':fields['lifecycle'] = lifecycle()
    if change == 'disabled':fields['worker_policy'] = dict(WORKER_POLICY,enabled=False)
    with pytest.raises(ValueError):setup(tmp_path,**fields)
    assert not (tmp_path/'worker-study').exists()


def test_action_failure_swallowed_by_native_worker_cannot_complete_tick(tmp_path,monkeypatch):
    worker, clock = setup(tmp_path)
    original = worker._source.wallet.execute
    def fail(*args):
        original(*args)
        raise OSError('synthetic-after-commit')
    monkeypatch.setattr(worker._source.wallet,'execute',fail)
    with pytest.raises(ValueError,match='fault|unfinished'):tick(worker,clock,[prediction(clock)])
    head = json.loads(worker._head()[2])
    assert head['phase'] == 'action' and worker._head()[1] == 'prepared'
    with pytest.raises(ValueError,match='unfinished'):
        CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)


@pytest.mark.parametrize('budget',['maximum_actions_per_tick','maximum_clock_calls_per_tick','maximum_market_requests_per_tick'])
def test_live_tick_budgets_fail_closed_without_successful_receipt(tmp_path,budget):
    change = {budget:4 if budget == 'maximum_actions_per_tick' else 1}
    worker, clock = setup(tmp_path,capture_policy=budgets(**change))
    rows = [prediction(clock,'one'),prediction(clock,'two',pair='BBB/USDT')]
    with pytest.raises(ValueError):tick(worker,clock,rows)
    with pytest.raises(ValueError):worker.terminate('operator_abort')
    with pytest.raises(ValueError,match='unfinished'):
        CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)


@pytest.mark.parametrize('case,status',[
    ('rejected','candidate_rejected'),('future','outside_window_or_future'),
    ('unobserved','unverified_prediction_observation'),('expired','source_prediction_expired'),
    ('cutoff','paper_entry_window_finished'),('wrong_candidate',None),('outside_source',None),
])
def test_original_negative_and_out_of_scope_predictions_are_retained(tmp_path,case,status):
    worker, clock = setup(tmp_path,config=config(signal_expiry_seconds=6))
    row = prediction(clock)
    if case == 'rejected':row['would_enter'] = False
    if case == 'future':row['predicted_at'] = (clock.now+timedelta(seconds=1)).isoformat()
    if case == 'unobserved':row.pop('observed_at')
    if case == 'expired':clock.advance(10)
    if case == 'cutoff':clock.advance(15);row = prediction(clock)
    if case == 'wrong_candidate':row['candidate_sha256'] = 'c'*64
    if case == 'outside_source':row['predicted_at'] = (START-timedelta(seconds=1)).isoformat()
    assert tick(worker,clock,[row])['new_intents'] == 0
    seal = finish(worker,clock)
    result = audit(worker,seal)
    assert result['supplied_predictions'] == 1 and result['worker_source_trace_pass']
    seen = list(worker._source.iter_rows('worker.seen_predictions'))
    assert ([r[1] for r in seen] == [status]) if status else not seen


@pytest.mark.parametrize('failure',[False,True])
def test_original_shared_exit_request_result_or_error_is_retained(tmp_path,failure):
    wp = deepcopy(WORKER_POLICY);wp['exits']['shared_exit_signal'] = True
    def indicator(pair):
        if failure:raise TimeoutError('do-not-store-this-message')
        return True,['rsi_exit']
    worker, clock = setup(tmp_path,worker_policy=wp,exit_indicator=indicator)
    tick(worker,clock,[prediction(clock)]);clock.advance(5)
    report = tick(worker,clock)
    if failure:assert report['errors']['exit:AAA/USDT'] == 'TimeoutError'
    seal = finish(worker,clock)
    result = audit(worker,seal)
    assert result['exit_requests'] == 1 and result['failed_exit_requests'] == int(failure)
    serialized = json.dumps(records(worker,seal))
    assert ('rsi_exit' in serialized) is not failure
    assert 'do-not-store-this-message' not in serialized


@pytest.mark.parametrize('change',['genesis','parent','clock','market_source','action_scope',
    'native_delta_key','batch_sha','source_decision','queued_deadline','worker_event_time','tick_report','wall'])
def test_rehashed_trace_cannot_override_original_sources_or_atomic_actions(tmp_path,change):
    worker, clock = setup(tmp_path)
    tick(worker,clock,[prediction(clock,'yes'),prediction(clock,'no',would_enter=False)])
    clock.advance(5);tick(worker,clock)
    seal = finish(worker,clock)
    def mutate(record):
        kind,event = record['kind'],record['payload'];phase = event.get('phase')
        if change == 'genesis' and kind == 'genesis':event['after']['sources']['wallet.marks']['count'] = 1
        if change == 'parent' and 'tick_sequence' in event:event['tick_sequence'] = 999
        if change == 'clock' and phase == 'clock':event['at'] = (START-timedelta(seconds=1)).isoformat()
        if change == 'market_source' and phase == 'market' and kind == 'complete':event['result']['quote']['bid'] = '999'
        if change == 'action_scope' and phase == 'action' and kind == 'prepared' and event['operation'] == 'mark':event['operation'] = 'compact'
        if change == 'native_delta_key' and event.get('changes'):event['changes'][0]['key'] = 'forged'
        if change == 'batch_sha' and phase == 'tick' and kind == 'prepared' and event['mode'] == 'tick':event['inputs']['source_sha256'] = 'f'*64
        if change == 'source_decision' and phase == 'tick' and kind == 'prepared' and event['mode'] == 'tick':
            for row in event['inputs']['predictions']:
                if row['opportunity'] == 'no':row['would_enter'] = True
            event['inputs']['source_sha256'] = digest(canonical(event['inputs']['predictions']))
        if change == 'queued_deadline' and phase == 'action' and kind == 'prepared' and event['operation'] == 'worker_enqueue' and event['inputs']['side'] == 'Buy':
            event['inputs']['payload']['source_deadline'] = START.isoformat()
        if change == 'worker_event_time' and phase == 'action' and kind == 'complete':
            for c in event['changes']:
                if c['source'] == 'worker.worker_events':c['after'][1] = (START-timedelta(seconds=1)).isoformat()
        if change == 'tick_report' and phase == 'tick' and kind == 'complete':event['result']['equity_known'] = False
        if change == 'wall' and phase == 'tick' and kind == 'complete':event['operation_wall_ns'] = 0
    with pytest.raises((ValueError,KeyError)):audit(worker,rehash(worker,seal,mutate))


@pytest.mark.parametrize('change',['registration','protocol','runtime','log_policy','candidate','alias'])
def test_original_identity_and_new_namespace_only(tmp_path,change,monkeypatch):
    worker, clock = setup(tmp_path)
    if change == 'registration':worker.registration_sha256 = 'f'*64
    if change == 'protocol':worker.protocol_sha256 = 'f'*64
    if change == 'runtime':monkeypatch.setattr(capture,'runtime_hashes',lambda:{})
    if change == 'log_policy':worker.log.policy = replace(worker.log.policy,maximum_total_bytes=32*1024*1024)
    if change == 'candidate':worker.candidate_sha = 'f'*64
    if change == 'alias':
        alias = tmp_path/'alias';alias.symlink_to(worker.root,target_is_directory=True);worker.root = alias
    with pytest.raises((ValueError,OSError)):tick(worker,clock)


@pytest.mark.parametrize('name',['memory','disk','storage'])
def test_resource_floor_stops_before_any_tick_effect(tmp_path,monkeypatch,name):
    worker, clock = setup(tmp_path)
    original = worker._resources
    key = dict(memory='available_memory_bytes',disk='free_disk_bytes',storage='storage_bytes')[name]
    monkeypatch.setattr(worker,'_resources',lambda:{**original(),key:0 if name != 'storage' else 2**62})
    with pytest.raises(ValueError,match='budget'):tick(worker,clock)
    assert worker._head()[1] == 'terminated'
    clock.now = START+timedelta(seconds=20)
    result = audit(worker,worker.finalize())
    assert result['ticks'] == 0 and result['terminal_reason'] == 'resource_budget'


@pytest.mark.parametrize('stage',['after_wallet_commit','after_worker_commit','after_archive_commit','before_projection_commit','after_projection_commit','during_tick_complete','during_action_complete'])
def test_process_death_never_adopts_partial_tick_or_repeats_effects(tmp_path,stage):
    worker, clock = setup(tmp_path)
    code = '''
from datetime import datetime
from pathlib import Path
import json,os,sys
from cryptoforge.paper_worker_capture import CapturedPaperWorker
from cryptoforge.evidence_segments import canonical,digest
root,pin,at,stage=sys.argv[1:];now=datetime.fromisoformat(at)
w=CapturedPaperWorker.resume(Path(root),expected_registration_sha256=pin,market=lambda pair:None,clock=lambda:now)
if stage=='after_wallet_commit':
    original=w._source.wallet.mark
    def killed(*args):
        original(*args);os._exit(81)
    w._source.wallet.mark=killed
elif stage=='after_worker_commit':
    original=w._worker._event
    def killed(*args):
        original(*args);os._exit(82)
    w._worker._event=killed
elif stage in {'during_tick_complete','during_action_complete'}:
    original=w.log._write_frame
    def killed(path,offset,raw):
        record=json.loads(raw)
        if record['kind']=='complete' and record['payload'].get('phase')==('tick' if stage=='during_tick_complete' else 'action'):
            with path.open('ab') as f:f.write(raw[:len(raw)//2]);f.flush();os.fsync(f.fileno())
            os._exit(83)
        return original(path,offset,raw)
    w.log._write_frame=killed
else:
    def killed(name):
        if name==stage:os._exit(84)
    w._source._stage=killed
rows=[]
w.tick(rows,source_id='empty',source_observed_at=now,expected_source_sha256=digest(canonical(rows)))
'''
    process = subprocess.run([sys.executable,'-c',code,str(worker.root),worker.registration_sha256,
        clock.now.isoformat(),stage],timeout=30)
    assert process.returncode == dict(after_wallet_commit=81,after_worker_commit=82,during_tick_complete=83,during_action_complete=83).get(stage,84)
    if stage == 'during_tick_complete':
        restored = CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)
        result = audit(restored,finish(restored,clock))
        assert result['ticks'] == 1
    else:
        with pytest.raises(ValueError,match='unfinished'):
            CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
                market=lambda pair:raw_market(clock,pair),clock=clock)


def test_cli_real_clock_no_asof_and_exclusive_output_outside_sources(tmp_path,capsys):
    spec = importlib.util.spec_from_file_location('worker_cli',Path(__file__).resolve().parents[1]/'scripts/audit_paper_worker_capture.py')
    cli = importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    worker, clock = setup(tmp_path)
    args = ['--root',str(worker.root),'--expected-registration-sha256',worker.registration_sha256]
    with pytest.raises(SystemExit):cli.main(args+['--as-of',START.isoformat()])
    assert cli.main(args+['--output',str(worker.root/'invalid')]) == 1
    tick(worker,clock);seal = finish(worker,clock)
    args += ['--expected-seal-sha256',seal['seal_sha256']]
    output = tmp_path/'audit.json'
    assert cli.main(args+['--output',str(output)]) == 0
    assert json.loads(output.read_bytes())['worker_source_trace_pass']
    before = output.read_bytes()
    assert cli.main(args+['--output',str(output)]) == 1
    assert before == output.read_bytes()


def test_monotonic_budget_branch_is_captured_without_global_monkeypatch(tmp_path,monkeypatch):
    from cryptoforge import paper_worker
    original = paper_worker.monotonic_time.monotonic
    worker, clock = setup(tmp_path)
    values = iter((100.0,120.0))
    monkeypatch.setattr(capture,'monotonic',lambda:next(values))
    report = tick(worker,clock,[prediction(clock)])
    assert report['errors']['AAA/USDT'] == 'paper_tick_wall_budget_exhausted'
    assert paper_worker.monotonic_time.monotonic is original
    seal = finish(worker,clock)
    assert audit(worker,seal)['market_requests'] == 0
    assert [r['payload']['value'] for r in records(worker,seal) if r['payload'].get('phase') == 'monotonic'] == [100.0,120.0]


def test_bounded_projection_and_restart_over_many_whole_ticks(tmp_path):
    worker, clock = setup(tmp_path,end=START+timedelta(seconds=65),
        native_policy=policy(maximum_active_rows=16),storage_policy=storage(maximum_events=2048,
            maximum_segment_events=64,maximum_record_bytes=32768,maximum_total_bytes=16*1024*1024))
    for n in range(13):
        clock.now = START+timedelta(seconds=n*5)
        tick(worker,clock)
        if n == 6:
            worker = CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
                market=lambda pair:raw_market(clock,pair),clock=clock)
    with worker._source.wallet._db() as db:assert db.execute('SELECT count(*) FROM marks').fetchone()[0] <= 2
    assert len(worker._cache['summary']) == 12 and len(worker._cache['heads']) == 4
    clock.now = START+timedelta(seconds=65)
    worker.mark_endpoint({},{});worker.terminate('completed');seal = worker.finalize()
    result = audit(worker,seal,clock=clock)
    assert result['ticks'] == 13 and len(list(worker._source.iter_rows('wallet.marks'))) == 14


def test_source_seal_without_capture_receipt_is_not_adopted(tmp_path,monkeypatch):
    worker, clock = setup(tmp_path)
    clock.now = START+timedelta(seconds=20);worker.terminate('completed')
    def stopped():raise OSError('no-receipt')
    monkeypatch.setattr(worker.log,'seal',stopped)
    with pytest.raises(OSError):worker.finalize()
    with pytest.raises(ValueError,match='sealed source'):
        CapturedPaperWorker.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)


@pytest.mark.parametrize('source',['wallet','worker','checkpoint','shard','extra'])
def test_missing_modified_or_extra_source_cannot_borrow_worker_trace(tmp_path,source):
    worker, clock = setup(tmp_path);tick(worker,clock);seal = finish(worker,clock)
    root = worker.root/'native'
    if source == 'shard':(root/'archive'/'00.sqlite').unlink()
    elif source == 'extra':(root/'unexpected').write_text('x')
    else:
        path = root/(source+'.sqlite');path.write_bytes(path.read_bytes()+b'changed')
    with pytest.raises((OSError,ValueError)):audit(worker,seal)


@pytest.mark.parametrize('case',['too_large','too_deep','cyclic'])
def test_input_object_is_bounded_before_json_copy(tmp_path,case):
    worker, clock = setup(tmp_path);row = prediction(clock)
    if case == 'too_large':row['extra'] = 'x'*40000
    elif case == 'cyclic':row['extra'] = row
    else:
        value = []
        for _ in range(30):value = [value]
        row['extra'] = value
    with pytest.raises(ValueError):worker.tick([row],source_id='s',source_observed_at=clock.now,expected_source_sha256='a'*64)
    assert worker._head()[0] == 1


def test_endpoint_has_its_own_small_storage_reserve(tmp_path,monkeypatch):
    worker, clock = setup(tmp_path);tick(worker,clock)
    clock.now = START+timedelta(seconds=20)
    endpoint_reserve = 8*worker.log.policy.maximum_record_bytes+65536
    monkeypatch.setattr(worker.log,'_storage',lambda db:worker.log.policy.maximum_total_bytes-endpoint_reserve)
    worker.mark_endpoint({},{});worker.terminate('completed')
    assert worker._head()[1] == 'terminated'


def test_pending_buy_after_cutoff_cannot_spend_cash_or_become_successful_tick(tmp_path):
    worker, clock = setup(tmp_path)
    clock.now = START+timedelta(seconds=14)
    tick(worker,clock,[prediction(clock)])
    clock.now = START+timedelta(seconds=15)
    with pytest.raises(ValueError):tick(worker,clock)
    with worker._source.wallet._db() as db:
        assert db.execute('SELECT count(*) FROM fills').fetchone()[0] == 0
        assert db.execute("SELECT value FROM state WHERE key='cash'").fetchone()[0] == '100'
