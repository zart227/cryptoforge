from datetime import timedelta
import sqlite3

import pytest

from cryptoforge.cached_reference_reader_v2 import CachedReferenceReaderV2
from cryptoforge.reference_prefix_v2 import ReferencePrefixV2,PrefixPolicyV2,SourceReplay
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy
from cryptoforge.reference_delivery import ReferenceDelivery,DeliveryPolicy,ROLES
from cryptoforge.cash_entry_contract import freeze_cash_contract,load_cash_contract,evaluate_cash_packet
from cryptoforge.local_source_provenance import canonical,digest
from test_reference_source_ledger import Clock,Client
from test_cash_worker_application import PositiveClient,rules


def setup(tmp_path,*,delivery_policy=None):
    clock=Clock();start=clock()+timedelta(seconds=60);end=start+timedelta(minutes=20)
    source=ReferenceLedger.create(tmp_path/'source',clock=clock,start=start,end=end,
        policy=ReferencePolicy(maximum_events=400,maximum_versions=10000,maximum_forecasts=1,maximum_database_bytes=16*1024**2))
    queue=ReferenceDelivery.create(tmp_path/'queue',source.receipt()['reference'],clock=clock,
        policy=delivery_policy or DeliveryPolicy(maximum_database_bytes=32*1024**2,maximum_source_events_per_batch=4))
    prefix=ReferencePrefixV2.create(tmp_path/'prefix',source.receipt()['reference'],clock=clock,
        policy=PrefixPolicyV2(maximum_database_bytes=32*1024**2))
    cash=freeze_cash_contract(tmp_path/'cash',queue,rules=rules(),closeout_seconds=5,clock=clock)
    reader=CachedReferenceReaderV2.create(tmp_path/'reader',queue,prefix,clock=clock)
    clock.advance(60);return clock,source,queue,prefix,reader,cash


def poll(clock,source,queue,prefix,*,failed=False):
    source.poll(Client(clock,failed='BTC/USDT') if failed else PositiveClient(clock))
    ref=source.receipt()['reference'];prefix.ingest(ref);queue.ingest(ref)


@pytest.mark.parametrize('role',ROLES)
def test_cached_offer_packet_and_cash_decisions_match_original_reader_byte_for_byte(tmp_path,role):
    clock,source,queue,prefix,reader,cash=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next(role)['delivery']['delivery_id'];expected=queue.read(role,delivery)
    before_queue=queue.path.read_bytes();before_prefix=prefix.path.read_bytes()
    result=reader.read(queue,prefix.reference,role,delivery)
    assert canonical(result['packet'])==canonical(expected) and result['packet_sha256']==digest(canonical(expected))
    contract=load_cash_contract(cash)
    assert evaluate_cash_packet(contract,cash['contract_sha256'],result['packet'],role,observed_at=clock())==evaluate_cash_packet(contract,cash['contract_sha256'],expected,role,observed_at=clock())
    assert queue.path.read_bytes()==before_queue and prefix.path.read_bytes()==before_prefix
    assert result['source_semantic_prefix_replayed'] is False


def test_cached_read_never_calls_source_replay_feed(tmp_path,monkeypatch):
    clock,source,queue,prefix,reader,_=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id']
    def forbidden(*a,**k):pytest.fail('full source semantic replay occurred during cached read')
    monkeypatch.setattr(SourceReplay,'feed',forbidden)
    assert reader.read(queue,prefix.reference,'candidate',delivery)['packet']['closed_candles_ready']


def test_failed_source_and_negative_decisions_are_not_filtered_out_of_cached_packet(tmp_path):
    clock,source,queue,prefix,reader,cash=setup(tmp_path);poll(clock,source,queue,prefix,failed=True)
    delivery=queue.next('candidate')['delivery']['delivery_id'];packet=reader.read(queue,prefix.reference,'candidate',delivery)['packet']
    assert packet==queue.read('candidate',delivery) and packet['closed_candles_ready'] is False
    derived=evaluate_cash_packet(load_cash_contract(cash),cash['contract_sha256'],packet,'candidate',observed_at=clock())
    assert len(derived['decisions'])==2 and not any(v['would_enter'] for v in derived['decisions'])


def test_advanced_cached_prefix_cannot_replace_old_pending_batch_or_skip_queue(tmp_path):
    clock,source,queue,prefix,reader,_=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];clock.advance(300);poll(clock,source,queue,prefix)
    before=queue.path.read_bytes()
    with pytest.raises(ValueError,match='backlog blocked'):reader.read(queue,prefix.reference,'candidate',delivery)
    assert queue.path.read_bytes()==before and queue.receipt()['role_cursors']['candidate']['cursor']==0


def test_stale_prefix_checkpoint_stops_before_queue_or_worker_effect(tmp_path):
    clock,source,queue,prefix,reader,_=setup(tmp_path);old=dict(prefix.reference);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];before=queue.path.read_bytes()
    with pytest.raises(ValueError,match='stale or changed'):reader.read(queue,old,'candidate',delivery)
    assert queue.path.read_bytes()==before


@pytest.mark.parametrize('fault',['wrong_role','acknowledged','unoffered'])
def test_only_original_pending_role_offer_can_be_read(tmp_path,fault):
    clock,source,queue,prefix,reader,_=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];role='candidate'
    if fault=='wrong_role':role='stress'
    if fault=='acknowledged':queue.acknowledge(role,delivery,worker_receipt_sha256='a'*64)
    if fault=='unoffered':delivery='b'*64
    before=queue.path.read_bytes()
    with pytest.raises(ValueError,match='pending'):reader.read(queue,prefix.reference,role,delivery)
    assert queue.path.read_bytes()==before


@pytest.mark.parametrize('fault',['manifest_memory','alias','extra_file','clock'])
def test_original_reader_registration_and_clock_are_required(tmp_path,fault):
    clock,source,queue,prefix,reader,_=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];reader.read(queue,prefix.reference,'candidate',delivery)
    if fault=='manifest_memory':reader.manifest['maximum_read_seconds']=30
    if fault=='alias':
        alias=tmp_path/'alias';alias.symlink_to(reader.root);reader.root=alias
    if fault=='extra_file':(reader.root/'unregistered').touch()
    if fault=='clock':clock.advance(-1)
    before=queue.path.read_bytes()
    with pytest.raises(ValueError):reader.read(queue,prefix.reference,'candidate',delivery)
    assert queue.path.read_bytes()==before


def test_delayed_cached_read_does_not_freshen_observation_or_restore_expired_signal(tmp_path):
    clock,source,queue,prefix,reader,cash=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];initial=reader.read(queue,prefix.reference,'candidate',delivery)['packet']
    clock.advance(700);late=reader.read(queue,prefix.reference,'candidate',delivery)['packet']
    assert late==queue.read('candidate',delivery) and late['closed_candles_ready'] is False
    assert late['source_view']==initial['source_view'] and late['delivery']==initial['delivery']
    derived=evaluate_cash_packet(load_cash_contract(cash),cash['contract_sha256'],late,'candidate',observed_at=clock())
    assert {v['reason'] for v in derived['decisions']}=={'source_batch_expired'}


def test_packet_byte_budget_fails_closed_without_ack_or_offer_change(tmp_path):
    policy=DeliveryPolicy(maximum_database_bytes=32*1024**2,maximum_source_events_per_batch=4,maximum_delivery_bytes=4096)
    clock,source,queue,prefix,reader,_=setup(tmp_path,delivery_policy=policy);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];before=queue.path.read_bytes()
    with pytest.raises(ValueError,match='packet byte'):reader.read(queue,prefix.reference,'candidate',delivery)
    assert queue.path.read_bytes()==before


def test_separately_registered_prefix_is_not_substituted_into_reader(tmp_path):
    clock,source,queue,prefix,reader,_=setup(tmp_path/'one');_,_,_,other,_,_=setup(tmp_path/'two')
    poll(clock,source,queue,prefix);delivery=queue.next('candidate')['delivery']['delivery_id']
    before=queue.path.read_bytes()
    with pytest.raises(ValueError,match='prefix differs'):reader.read(queue,other.reference,'candidate',delivery)
    assert queue.path.read_bytes()==before


@pytest.mark.parametrize('owner',['queue','prefix'])
def test_busy_component_lease_prevents_read_without_changing_pending_offer(tmp_path,owner):
    import fcntl
    clock,source,queue,prefix,reader,_=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];before=queue.path.read_bytes()
    root=queue.root if owner=='queue' else prefix.root
    with (root/'writer.lock').open('rb') as handle:
        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):reader.read(queue,prefix.reference,'candidate',delivery)
    assert queue.path.read_bytes()==before


def test_whole_read_wall_budget_failure_cannot_acknowledge_or_retime_signal(tmp_path,monkeypatch):
    import cryptoforge.cached_reference_reader_v2 as module
    clock,source,queue,prefix,reader,_=setup(tmp_path);poll(clock,source,queue,prefix)
    delivery=queue.next('candidate')['delivery']['delivery_id'];before=queue.path.read_bytes();times=iter([0,100])
    monkeypatch.setattr(module,'monotonic',lambda:next(times))
    with pytest.raises(ValueError,match='wall budget'):reader.read(queue,prefix.reference,'candidate',delivery)
    assert queue.path.read_bytes()==before and queue.receipt()['role_cursors']['candidate']['cursor']==0
