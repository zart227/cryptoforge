from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import json

import pytest

from cryptoforge.cash_entry_contract import CashEntryRule,freeze_cash_contract,load_cash_contract,evaluate_cash_packet,_metrics
from cryptoforge.cash_worker_application import CashWorkerApplication,CashApplicationPolicy
from cryptoforge.local_source_provenance import canonical,digest,parse,stamp
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy
from cryptoforge.reference_delivery import ReferenceDelivery,DeliveryPolicy,ROLES
from cryptoforge.paper_producer_v2 import register_kernel
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from test_reference_source_ledger import Clock,Client,mutate
from test_paper_capture_v3 import lifecycle,storage
from test_native_paper_archive_v2 import policy as native_policy,WORKER_POLICY
from test_paper_worker_capture_v2 import budgets
from test_paper_wallet import config
from test_paper_valuation_capture import raw_market


def rules(cost=50):
    return [CashEntryRule(role,'cash_only' if role=='control' else 'momentum_breakout_v1',
        20,cost+10 if role=='stress' else cost,20,10000,1000) for role in ROLES]


def make_queue(tmp_path,*,batch_limit=4,clock=None):
    clock=clock or Clock();start=clock()+timedelta(seconds=60);end=start+timedelta(seconds=20)
    source=ReferenceLedger.create(tmp_path/'source',clock=clock,start=start,end=end,
        policy=ReferencePolicy(maximum_events=100,maximum_versions=1000,maximum_forecasts=10,maximum_database_bytes=4*1024**2))
    queue=ReferenceDelivery.create(tmp_path/'queue',source.receipt()['reference'],clock=clock,
        policy=DeliveryPolicy(maximum_database_bytes=8*1024**2,maximum_source_events_per_batch=batch_limit))
    return clock,source,queue


class PositiveClient(Client):
    def fetch(self,pair,anchor):
        value=super().fetch(pair,anchor)
        def change(body):
            body['result']['list'][0][1:6]=['101','106','100','105','20']
        return mutate(value,change)


def setup(tmp_path,*,cost=50,application_policy=None):
    clock,source,queue=make_queue(tmp_path)
    reference=freeze_cash_contract(tmp_path/'contract',queue,rules=rules(cost),closeout_seconds=5,clock=clock)
    contract=load_cash_contract(reference);workers={};applications={}
    for role in ROLES:
        kernel=register_kernel(tmp_path/('kernel-'+role),candidate_sha=contract['strategies'][role],
            study_protocol_sha256=reference['contract_sha256'],role=role,config=config(),worker_policy=WORKER_POLICY,
            backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY':'do-not-persist-key'},
            start=stamp(contract['start']),end=stamp(contract['end']),closeout_seconds=5,clock=clock)
        worker=CapturedPaperWorkerV2.create(tmp_path/('worker-'+role),kernel_root=kernel['root'],
            expected_kernel_contract_sha256=kernel['contract_sha256'],expected_kernel_registration_sha256=kernel['registration_sha256'],
            lifecycle=lifecycle(maximum_operations_per_poll=1),
            storage_policy=storage(maximum_events=2048,maximum_segment_events=128,maximum_record_bytes=32768,maximum_total_bytes=16*1024**2),
            native_policy=native_policy(),capture_policy=budgets(),market=lambda pair:raw_market(clock,pair),clock=clock)
        workers[role]=worker
        applications[role]=CashWorkerApplication.create(tmp_path/('application-'+role),reference,queue,worker,clock=clock,policy=application_policy)
    clock.advance(60)
    return clock,source,queue,reference,workers,applications


def poll(source,queue,clock,positive=True):
    source.poll(PositiveClient(clock) if positive else Client(clock));queue.ingest(source.receipt()['reference'])


def test_three_real_workers_apply_all_pair_decisions_and_ack_result_not_input(tmp_path):
    clock,source,queue,reference,workers,apps=setup(tmp_path);poll(source,queue,clock)
    assert len(set(load_cash_contract(reference)['strategies'].values()))==3
    for role in ROLES:
        result=apps[role].apply(queue,workers[role])
        assert result['status']=='actual_worker_application_completed' and result['opportunity_count']==2
        assert result['positive_decisions']==(0 if role=='control' else 2)
        folder=apps[role].root/'groups/00000001';raw=parse((folder/'input.json').read_bytes())
        assert [v['pair'] for v in raw['derived']['decisions']]==['BTC/USDT','ETH/USDT']
        receipt=parse((folder/'worker-result.json').read_bytes());ack=parse((folder/'ack.json').read_bytes())['acknowledgement']
        assert ack['worker_receipt_sha256']==digest((folder/'worker-result.json').read_bytes())!=digest((folder/'input.json').read_bytes())
        assert receipt['prepared_tick']['payload']['inputs']['predictions']==raw['derived']['predictions']
        assert receipt['worker_after'][0]>receipt['worker_before'][0]
        assert all(result[k] is False for k in ('paper_evidence_pass','economic_profitability_established','live_admission_granted'))
    assert queue.receipt()['role_cursors']['candidate']['cursor']==1
    assert 'do-not-persist-key' not in ''.join(p.read_text() for a in apps.values() for p in a.root.rglob('*.json'))


def test_heartbeat_executes_pending_fills_without_inventing_source_opportunities(tmp_path):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    first=apps['candidate'].apply(queue,workers['candidate']);assert first['worker_result']['fills_processed']==['pending','pending']
    clock.advance(5);result=apps['candidate'].apply(queue,workers['candidate'])
    assert result['status']=='actual_worker_heartbeat_completed' and result['opportunity_count']==0
    assert result['worker_result']['fills_processed']==['filled','filled']
    folder=apps['candidate'].root/'groups/00000002'
    assert parse((folder/'ack.json').read_bytes())['acknowledgement'] is None
    assert queue.receipt()['role_cursors']['candidate']['cursor']==1


def test_negative_signals_are_retained_and_cash_control_never_enters(tmp_path):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock,False)
    result=apps['candidate'].apply(queue,workers['candidate']);assert result['positive_decisions']==0
    decisions=parse((apps['candidate'].root/'groups/00000001/input.json').read_bytes())['derived']['decisions']
    assert {v['reason'] for v in decisions}=={'momentum_below_cost_buffer'}
    assert result['worker_result']['market_observations']==0


def test_failed_reference_records_all_skips_without_dropping_the_other_pair(tmp_path):
    clock,source,queue,_,workers,apps=setup(tmp_path)
    source.poll(Client(clock,failed='BTC/USDT'));queue.ingest(source.receipt()['reference'])
    result=apps['stress'].apply(queue,workers['stress']);assert result['opportunity_count']==2 and result['positive_decisions']==0
    rows=parse((apps['stress'].root/'groups/00000001/input.json').read_bytes())['derived']['decisions']
    assert all(v['reason']=='source_unavailable' for v in rows)


def test_delayed_batch_cannot_be_retimed_into_fresh_entry(tmp_path):
    clock,source,queue,ref,workers,apps=setup(tmp_path);poll(source,queue,clock)
    # The worker window stays frozen: directly evaluate the original packet at
    # a later time in a separately widened pure derivation fixture only.
    offered=queue.next('candidate');packet=queue.read('candidate',offered['delivery']['delivery_id'])
    contract=load_cash_contract(ref);contract['end']=(clock()+timedelta(minutes=2)).isoformat();contract['entry_cutoff']=contract['end']
    result=evaluate_cash_packet(contract,ref['contract_sha256'],packet,'candidate',observed_at=clock()+timedelta(seconds=31))
    assert {v['reason'] for v in result['decisions']}=={'source_batch_expired'}
    assert not any(v['would_enter'] for v in result['predictions'])


@pytest.mark.parametrize('fault',['wrong_role','missing_pair','multi_poll','forecast','future_offer'])
def test_incomplete_or_wrong_cash_input_cannot_be_interpreted_as_decision(tmp_path,fault):
    clock,source,queue,ref,workers,apps=setup(tmp_path);poll(source,queue,clock)
    offered=queue.next('candidate');packet=queue.read('candidate',offered['delivery']['delivery_id'])
    if fault=='wrong_role':packet['delivery']['role']='control'
    if fault=='missing_pair':del packet['source_view']['windows']['ETH/USDT']
    if fault=='multi_poll':packet['source_events']+=deepcopy(packet['source_events'])
    if fault=='forecast':packet['source_events'].append(dict(kind='forecast',payload=dict(long_probability=1)))
    if fault=='future_offer':packet['delivery']['offered_at']=(clock()+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):evaluate_cash_packet(load_cash_contract(ref),ref['contract_sha256'],packet,'candidate',observed_at=clock())


def test_actual_market_failure_is_preserved_in_application_receipt(tmp_path):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    def unavailable(pair):raise ConnectionError('do-not-persist-provider-message')
    workers['candidate']._market=unavailable
    result=apps['candidate'].apply(queue,workers['candidate'])
    assert result['worker_result']['errors']=={'BTC/USDT':'ConnectionError','ETH/USDT':'ConnectionError'}
    assert queue.receipt()['role_cursors']['candidate']['cursor']==1
    assert 'do-not-persist-provider-message' not in ''.join(p.read_text() for p in apps['candidate'].root.rglob('*.json'))


def test_worker_exception_leaves_unacknowledged_pending_and_blocks_retry(tmp_path,monkeypatch):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    def crash(*args,**kwargs):raise RuntimeError('unknown partial worker effect')
    monkeypatch.setattr(workers['candidate'],'tick',crash)
    with pytest.raises(RuntimeError):apps['candidate'].apply(queue,workers['candidate'])
    assert queue.receipt()['role_cursors']['candidate']['cursor']==0
    assert (apps['candidate'].root/'groups/00000001/worker-error.json').exists()
    with pytest.raises(ValueError,match='incomplete'):CashWorkerApplication.open(apps['candidate'].reference,clock=clock)


def test_ack_failure_after_real_tick_never_automatically_repeats_worker(tmp_path,monkeypatch):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    original=queue.acknowledge
    def unavailable(*args,**kwargs):raise OSError('lost acknowledgement')
    monkeypatch.setattr(queue,'acknowledge',unavailable)
    with pytest.raises(OSError):apps['candidate'].apply(queue,workers['candidate'])
    assert (apps['candidate'].root/'groups/00000001/worker-result.json').exists()
    monkeypatch.setattr(queue,'acknowledge',original)
    with pytest.raises(ValueError,match='incomplete'):apps['candidate'].apply(queue,workers['candidate'])
    assert queue.receipt()['role_cursors']['candidate']['cursor']==0


def test_checkpoint_resume_is_exact_and_old_checkpoint_not_adopted(tmp_path):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    old=dict(apps['control'].reference);result=apps['control'].apply(queue,workers['control'])
    with pytest.raises(ValueError,match='stale cash checkpoint'):CashWorkerApplication.open(old,clock=clock)
    current=CashWorkerApplication.open(result['reference'],clock=clock)
    assert current.audit()['completed_applications']==1
    assert current.audit()['bytes']>0


def test_same_size_tampering_and_external_worker_tick_block_new_effects(tmp_path):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock)
    apps['candidate'].apply(queue,workers['candidate'])
    p=apps['candidate'].root/'groups/00000001/input.json';raw=p.read_bytes();p.write_bytes(raw.replace(b'"enter"',b'"other"',1))
    with pytest.raises(ValueError,match='receipt/files'):apps['candidate'].audit()
    apps['control'].apply(queue,workers['control']);clock.advance(5)
    workers['control'].tick([],source_id='external',source_observed_at=clock(),expected_source_sha256=digest(canonical([])))
    with pytest.raises(ValueError,match='worker head differs'):apps['control'].apply(queue,workers['control'])


def test_quota_and_disk_floor_fail_before_offering_delivery(tmp_path,monkeypatch):
    from types import SimpleNamespace
    clock,source,queue,_,workers,apps=setup(tmp_path,application_policy=CashApplicationPolicy(maximum_groups=1));poll(source,queue,clock)
    before=queue.receipt()['reference'];monkeypatch.setattr('cryptoforge.cash_worker_application._free_disk',lambda _:2048*1024**2)
    with pytest.raises(ValueError,match='disk reserve'):apps['candidate'].apply(queue,workers['candidate'])
    assert queue.receipt()['reference']==before
    monkeypatch.undo();apps['candidate'].apply(queue,workers['candidate']);clock.advance(5);before=queue.receipt()['reference']
    with pytest.raises(ValueError,match='storage budget'):apps['candidate'].apply(queue,workers['candidate'])
    assert queue.receipt()['reference']==before


def test_cost_floor_cannot_be_smaller_than_frozen_fee_slippage_assumptions(tmp_path):
    with pytest.raises(ValueError,match='cost floor'):setup(tmp_path,cost=1)


@pytest.mark.parametrize('fault',['batch_size','late','control','stress_cost','duplicate_role'])
def test_contract_registration_rejects_incompatible_or_late_sources(tmp_path,fault):
    clock,source,queue=make_queue(tmp_path,batch_limit=256 if fault=='batch_size' else 4);value=rules()
    if fault=='late':clock.advance(60)
    if fault=='control':value[1]=replace(value[1],family='momentum_breakout_v1')
    if fault=='stress_cost':value[2]=replace(value[2],round_trip_cost_bps=1)
    if fault=='duplicate_role':value[2]=replace(value[2],role='candidate')
    with pytest.raises(ValueError):freeze_cash_contract(tmp_path/'contract',queue,rules=value,closeout_seconds=5,clock=clock)
    assert not (tmp_path/'contract').exists()


@pytest.mark.parametrize('change',[dict(lookback_candles=True),dict(round_trip_cost_bps=0),dict(family='price_probability'),dict(maximum_last_range_bps=10001)])
def test_cash_rule_requires_explicit_bounded_non_probability_hypothesis(change):
    with pytest.raises(ValueError):replace(rules()[0],**change)


def test_exact_fraction_threshold_and_caller_decimal_context_do_not_change_decision():
    from decimal import localcontext
    rows=[dict(raw_row=['0','100','100','100','100','10','1000']) for _ in range(120)]
    rows[-1]['raw_row']=['0','100','101','100','100.5','10','1000']
    rule=replace(rules()[0],round_trip_cost_bps=30,minimum_momentum_buffer_bps=20)
    with localcontext() as ctx:
        ctx.prec=3;reason,metrics=_metrics(rule,rows)
    assert reason=='enter' and metrics['momentum_bps']==[50,1]
    rows[-1]['raw_row'][4]='100.499999999999999999999999'
    assert _metrics(rule,rows)[0]=='momentum_below_cost_buffer'


def test_true_process_death_after_real_worker_commit_leaves_no_ack_and_blocks_retry(tmp_path):
    import subprocess
    import sys
    import sqlite3
    code='''
from pathlib import Path
import json,os,sys
sys.path[:0]=['src','tests']
from test_cash_worker_application import setup,poll
root=Path(sys.argv[1]);clock,source,queue,_,workers,apps=setup(root)
poll(source,queue,clock);worker=workers['candidate'];application=apps['candidate']
(root/'outside.json').write_text(json.dumps(dict(reference=application.reference,at=clock().isoformat(),worker=str(worker.root))))
original=worker.tick
def die(*args,**kwargs):
    original(*args,**kwargs)
    os._exit(42)
worker.tick=die
application.apply(queue,worker)
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==42,result.stderr
    outside=json.loads((tmp_path/'outside.json').read_text())
    with pytest.raises(ValueError,match='incomplete'):
        CashWorkerApplication.open(outside['reference'],clock=lambda:stamp(outside['at']))
    db=__import__('sqlite3').connect((tmp_path/'queue/delivery.sqlite').as_uri()+'?mode=ro',uri=True)
    try:assert db.execute('SELECT count(*) FROM acks').fetchone()[0]==0
    finally:db.close()
    assert not (tmp_path/'application-candidate/groups/00000001/worker-result.json').exists()


def test_clock_regression_and_busy_lease_block_without_a_new_offer(tmp_path):
    import fcntl
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock);app=apps['candidate']
    before=queue.receipt()['reference']
    with (app.root/'writer.lock').open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):app.apply(queue,workers['candidate'])
    assert queue.receipt()['reference']==before
    app.audit();clock.advance(-1)
    with pytest.raises(ValueError,match='clock moved backwards'):app.audit()


@pytest.mark.parametrize('mutation',['contract','manifest','policy'])
def test_in_memory_changes_cannot_reuse_original_contract_sha(tmp_path,mutation):
    clock,source,queue,_,workers,apps=setup(tmp_path);poll(source,queue,clock);app=apps['candidate'];before=queue.receipt()['reference']
    if mutation=='contract':app.contract['rules']['candidate']['round_trip_cost_bps']=1
    elif mutation=='manifest':app.manifest['role']='control'
    else:app.policy=replace(app.policy,maximum_groups=1)
    with pytest.raises(ValueError,match='in-memory'):app.apply(queue,workers['candidate'])
    assert queue.receipt()['reference']==before


def test_cli_inspects_exact_contract_and_application_without_market_or_env(tmp_path):
    import subprocess,sys
    clock,source,queue,ref,workers,apps=setup(tmp_path);poll(source,queue,clock);apps['control'].apply(queue,workers['control'])
    for command,value in [('inspect-contract',ref),('audit-application',apps['control'].reference)]:
        path=tmp_path/(command+'.json');path.write_bytes(canonical(value))
        result=subprocess.run([sys.executable,'scripts/cash_reference_application.py',command,'--reference',str(path)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        output=json.loads(result.stdout)
        assert output['live_admission_granted'] is False
        if command=='inspect-contract':assert output['control_scope']=='hold_cash_control_not_legacy_active_model'
        else:assert output['completed_applications']==1
