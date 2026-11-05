"""Causal order, contract binding, atomic caps and recovery for archive v2."""
from datetime import datetime,timedelta
from decimal import Decimal as D
from fractions import Fraction as F
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from cryptoforge.evidence_segments import canonical
from cryptoforge.native_paper_archive import NativePaperArchive as FrozenArchive
from cryptoforge.native_paper_archive_v2 import NativePaperArchiveV2,SOURCES,AUXILIARY
from cryptoforge.paper_producer_v2 import register_kernel
from cryptoforge.paper_valuation_capture import _read_db as frozen_capture_db
from test_native_paper_archive_v2 import setup,policy,read,fill,WORKER_POLICY
from test_paper_wallet import START,Clock,config,market


def resume(state,clock):
    return NativePaperArchiveV2.resume(state.root,expected_manifest_sha256=state.manifest_sha256,
        expected_ready_sha256=state.ready_sha256,market=lambda pair:market(clock,pair),clock=clock)


def window(state):
    kernel=state.manifest['kernel_contract']
    return {key:datetime.fromisoformat(kernel[field]) for key,field in
            [('window_start','start'),('window_end','end'),('entry_cutoff','entry_cutoff')]}


@pytest.mark.parametrize('restart',[False,True])
def test_equal_clock_reverse_ids_preserve_fifo_through_every_compaction(tmp_path,restart):
    state,clock=setup(tmp_path)
    for identity,side in [('z-first','Buy'),('sell-one','Sell'),('a-second','Buy'),('sell-two','Sell')]:
        state.wallet.enqueue(identity,'AAA/USDT',side,created_at=clock.now)
    clock.advance();q,r=market(clock)
    for identity in ['z-first','sell-one','a-second','sell-two']:
        assert state.wallet.execute(identity,q,r)['status']=='filled'
        state.wallet.mark({'AAA/USDT':q},{'AAA/USDT':r})
        before=state.wallet.snapshot();state.compact()
        if restart:state=resume(state,clock)
        after=state.wallet.snapshot()
        assert after['cash']==before['cash'] and after['open_lots']==before['open_lots']
    orders=list(state.iter_rows('wallet.fill_order'))
    assert orders==[(1,'z-first'),(2,'sell-one'),(3,'a-second'),(4,'sell-two')]
    segments=[json.loads(row[1]) for row in state.iter_rows('wallet.closed_segments')]
    assert [row['entry_intent'] for row in segments if row['exit_intent']=='sell-two']==['z-first','a-second']
    assert list(state.iter_auxiliary_rows('wallet.fill_counter'))==[('fill_order',4)]
    snapshot=state.wallet.snapshot()
    assert F(snapshot['cash'])+sum((F(row['cost']) for row in snapshot['open_lots']),F(0))==100+sum((F(row['net_pnl']) for row in segments),F(0))


def test_global_fill_sequence_survives_closed_lot_removal_and_active_row_pressure(tmp_path):
    cfg=config(entry_fee=D(0),exit_fee=D(0),slippage=D(0))
    state,clock=setup(tmp_path,paper_config=cfg,maximum_active_rows=16)
    for number in range(12):
        assert fill(state,clock,f'z-buy-{number}','Buy')['status']=='filled'
        assert fill(state,clock,f'a-sell-{number}','Sell')['status']=='filled'
        q,r=market(clock);state.wallet.mark({'AAA/USDT':q},{'AAA/USDT':r})
        state.compact();state=resume(state,clock)
        with state.wallet._db() as db:
            assert db.execute('SELECT count(*) FROM lots').fetchone()==(0,)
            assert db.execute('SELECT count(*) FROM fills').fetchone()==(1,)
            assert db.execute('SELECT sequence FROM fill_order').fetchall()==[(2*number+2,)]
        assert D(state.wallet.snapshot()['cash'])==100
    rows=list(state.iter_rows('wallet.fill_order'))
    assert [r[0] for r in rows]==list(range(1,25))
    assert len({r[1] for r in rows})==24
    assert state.wallet.execute('z-buy-0',*market(clock))=={'status':'filled','duplicate':True}
    assert D(state.wallet.snapshot()['cash'])==100


def test_causal_latest_buy_context_remains_after_equal_clock_projection(tmp_path,monkeypatch):
    state,clock=setup(tmp_path)
    for identity,side in [('z-first','Buy'),('exit-first','Sell'),('a-second','Buy')]:
        state.wallet.enqueue(identity,'AAA/USDT',side,created_at=clock.now)
    clock.advance()
    for identity,price in [('z-first','100'),('exit-first','100'),('a-second','101')]:
        q,r=market(clock,price=price)
        assert state.wallet.execute(identity,q,r)['status']=='filled'
        state.wallet.mark({'AAA/USDT':q},{'AAA/USDT':r});state.compact();state=resume(state,clock)
    context=[]
    monkeypatch.setattr('cryptoforge.paper_worker_v2.price_time_exit',lambda **values:context.append(values))
    state.worker.tick([],**window(state))
    assert context[0]['entry_price']==D('101')*(1+config().slippage)


@pytest.mark.parametrize('change',['missing_counter','counter_down','counter_up','counter_real','counter_extra','missing_order','wrong_sequence','wrong_payload_sequence','missing_entry','negative_basis'])
def test_causal_state_corruption_cannot_resume_or_silently_repair(tmp_path,change):
    state,clock=setup(tmp_path);fill(state,clock,'buy','Buy')
    with state.wallet._db() as db:
        if change=='missing_counter':db.execute('DELETE FROM sqlite_sequence')
        elif change=='counter_down':db.execute('UPDATE sqlite_sequence SET seq=0')
        elif change=='counter_up':db.execute('UPDATE sqlite_sequence SET seq=9')
        elif change=='counter_real':db.execute('UPDATE sqlite_sequence SET seq=1.0')
        elif change=='counter_extra':db.execute("INSERT INTO sqlite_sequence VALUES ('unknown',1)")
        elif change=='missing_order':db.execute('DELETE FROM fill_order')
        elif change=='wrong_sequence':db.execute('UPDATE fill_order SET sequence=9');db.execute('UPDATE sqlite_sequence SET seq=9')
        elif change=='missing_entry':db.execute('DELETE FROM lots');db.execute('DELETE FROM fills')
        elif change=='negative_basis':db.execute("UPDATE lots SET cost='-1'")
        else:
            data=json.loads(db.execute('SELECT payload FROM fills').fetchone()[0]);data['fill_sequence']=9
            db.execute('UPDATE fills SET payload=?',(json.dumps(data,sort_keys=True),))
    before={p.name:p.read_bytes() for p in state.root.glob('*.sqlite')}
    with pytest.raises(ValueError):resume(state,clock)
    assert {p.name:p.read_bytes() for p in state.root.glob('*.sqlite')}==before


def test_reset_checkpoint_and_counter_cannot_hide_archived_fill_high_water(tmp_path):
    state,clock=setup(tmp_path);fill(state,clock,'buy','Buy');state.compact()
    with state.wallet._db() as db:
        db.execute('DELETE FROM fills');db.execute('DELETE FROM fill_order');db.execute('DELETE FROM lots');db.execute('DELETE FROM sqlite_sequence')
    with sqlite3.connect(state.root/'checkpoint.sqlite') as db:db.execute("UPDATE checkpoint SET watermarks='{}'")
    with pytest.raises(ValueError,match='high-water'):resume(state,clock)


@pytest.mark.parametrize('stage',['after_archive_commit','before_projection_commit','after_projection_commit'])
def test_process_death_during_fill_order_archival_keeps_original_counter_and_lots(tmp_path,stage):
    cfg=config(entry_fee=D(0),exit_fee=D(0),slippage=D(0));state,clock=setup(tmp_path,paper_config=cfg)
    for identity,side in [('z-buy','Buy'),('a-sell','Sell')]:assert fill(state,clock,identity,side)['status']=='filled'
    code='''
import os,sys
from cryptoforge.native_paper_archive_v2 import NativePaperArchiveV2
state=NativePaperArchiveV2.resume(sys.argv[1],expected_manifest_sha256=sys.argv[2],expected_ready_sha256=sys.argv[3],market=lambda pair:None)
def killed(stage):
    if stage==sys.argv[4]:os._exit(81)
state._stage=killed
state.compact()
'''
    result=subprocess.run([sys.executable,'-c',code,str(state.root),state.manifest_sha256,state.ready_sha256,stage],timeout=30)
    assert result.returncode==81
    state=resume(state,clock);state.compact()
    assert list(state.iter_rows('wallet.fill_order'))==[(1,'z-buy'),(2,'a-sell')]
    assert list(state.iter_auxiliary_rows('wallet.fill_counter'))==[('fill_order',2)]
    assert fill(state,clock,'next-buy','Buy')['fill']['fill_sequence']==3
    assert D(state.wallet.snapshot()['cash'])==94


def test_oversize_fill_aborts_cash_lot_counter_and_filters_as_one_transaction(tmp_path,monkeypatch):
    state,clock=setup(tmp_path);state.wallet.enqueue('buy','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    q,r=market(clock);q['padding']='x'*state.policy.maximum_row_bytes
    # Exercise the transactional backstop even if an upstream input guard fails.
    monkeypatch.setattr('cryptoforge.native_paper_archive_v2._bounded_json',lambda value,limit:canonical(value))
    with pytest.raises(sqlite3.IntegrityError,match='byte budget'):state.wallet.execute('buy',q,r)
    snapshot=state.wallet.snapshot()
    assert snapshot['fills']==[] and snapshot['open_lots']==[] and D(snapshot['cash'])==100
    assert list(state.iter_auxiliary_rows('wallet.fill_counter'))==[]
    assert state.wallet.pending_intents()[0]['id']=='buy'
    assert state.wallet.execute('buy',*market(clock))['fill']['fill_sequence']==1


@pytest.mark.parametrize('identity',['x'*17000,'nul\x00id','control\nid','é'],ids=['too_long','nul','control','non_ascii'])
def test_native_row_representation_guard_rejects_unbounded_or_ambiguous_ids_before_commit(tmp_path,identity):
    state,clock=setup(tmp_path)
    with pytest.raises((ValueError,sqlite3.IntegrityError),match='representation|bounded'):state.wallet.enqueue(identity,'AAA/USDT','Buy',created_at=clock.now)
    assert state.wallet.pending_intents()==[] and state.wallet.snapshot()['cash']=='100'


def test_active_row_trigger_prevents_an_unwrapped_write_from_exceeding_policy(tmp_path):
    state,clock=setup(tmp_path,maximum_active_rows=16)
    with state.worker._db() as db:
        db.executemany('INSERT INTO seen_predictions VALUES (?,?,?)',[(str(i),'fixture',clock.now.isoformat()) for i in range(16)])
    with pytest.raises(sqlite3.IntegrityError,match='budget'):
        with state.worker._db() as db:db.execute('INSERT INTO seen_predictions VALUES (?,?,?)',('overflow','fixture',clock.now.isoformat()))
    state.compact()
    assert len(list(state.iter_rows('worker.seen_predictions')))==16


def test_new_schema_groups_and_read_only_auxiliary_sources_are_explicit(tmp_path,monkeypatch):
    state,clock=setup(tmp_path);fill(state,clock,'buy','Buy');seal=state.seal()
    assert len(SOURCES)+len(AUXILIARY)==14
    assert state.manifest['source_schema']['immutable']['wallet.fill_order']==['main','fill_order',['sequence','intent_id'],True]
    def forbidden(*args,**kwargs):raise AssertionError('sealed source reader must remain offline')
    monkeypatch.setattr('cryptoforge.paper_producer_v2.resolve_backend',forbidden)
    monkeypatch.setattr('cryptoforge.paper_wallet_v2.PaperWalletV2.execute',forbidden)
    before={str(p.relative_to(state.root)):p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
    reader=read(state,seal);report=reader.audit()
    assert report['native_source_integrity_pass'] and report['source_counts']['wallet.fill_order']==1
    assert report['auxiliary_counts']['wallet.fill_counter']==1
    assert all(report[key] is False for key in ['full_worker_or_host_qualified','paper_evidence_pass','economic_profitability_established','live_admission_granted'])
    assert list(reader.iter_auxiliary_rows('wallet.fill_counter'))==[('fill_order',1)]
    assert before=={str(p.relative_to(state.root)):p.read_bytes() for p in state.root.rglob('*') if p.is_file()}


def test_frozen_archive_and_capture_reject_v2_without_modifying_it(tmp_path):
    state,clock=setup(tmp_path)
    before={str(p.relative_to(state.root)):p.read_bytes() for p in state.root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):FrozenArchive.resume(state.root,expected_manifest_sha256=state.manifest_sha256,market=lambda pair:None)
    with pytest.raises(ValueError,match='triggers'):frozen_capture_db(state.wallet.path)
    assert before=={str(p.relative_to(state.root)):p.read_bytes() for p in state.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('change',['ready','kernel','environment','schema','wrong_ready_pin'])
def test_registration_and_runtime_sources_stay_pinned_on_resume(tmp_path,monkeypatch,change):
    state,clock=setup(tmp_path)
    if change=='ready':(state.root/'ready.json').write_bytes(b'{}')
    elif change=='kernel':(Path(state.manifest['kernel_root'])/'registered.json').write_bytes(b'{}')
    elif change=='environment':monkeypatch.setattr('cryptoforge.native_paper_archive_v2._environment',lambda:{'changed':True})
    elif change=='schema':
        with state.wallet._db() as db:db.execute('DROP TRIGGER guard_fills_insert')
    else:state.ready_sha256='f'*64
    with pytest.raises(ValueError):resume(state,clock)


def test_external_kernel_change_during_a_sealed_stream_is_detected(tmp_path):
    state,clock=setup(tmp_path);state.wallet.mark({},{});reader=read(state,state.seal())
    stream=reader.iter_rows('wallet.marks');assert next(stream)[0]==1
    (Path(state.manifest['kernel_root'])/'kernel-contract.json').write_bytes(b'{}')
    with pytest.raises(ValueError):list(stream)


@pytest.mark.parametrize('phase',[1,2,3])
def test_archive_setup_cannot_finish_at_or_after_original_kernel_start(tmp_path,phase):
    clock=Clock();clock.now=START-timedelta(seconds=10)
    kernel=register_kernel(tmp_path/'kernel',candidate_sha='b'*64,study_protocol_sha256='a'*64,role='candidate',
        config=config(),worker_policy=WORKER_POLICY,backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY':'fixture'},
        start=START,end=START+timedelta(hours=1),closeout_seconds=30,clock=clock)
    calls=0
    def late():
        nonlocal calls
        calls+=1;return START if calls>=phase else START-timedelta(seconds=10)
    with pytest.raises(ValueError,match='original kernel start'):
        NativePaperArchiveV2.create(tmp_path/'source',source_protocol_sha256='c'*64,kernel_root=kernel['root'],
            expected_kernel_contract_sha256=kernel['contract_sha256'],expected_kernel_registration_sha256=kernel['registration_sha256'],
            policy=policy(),market=lambda pair:None,clock=late)
    assert not (tmp_path/'source'/'ready.json').exists()


@pytest.mark.parametrize('change',['start','end','cutoff','omitted_cutoff'])
def test_worker_rejects_window_changes_instead_of_reinterpreting_the_kernel(tmp_path,change):
    state,clock=setup(tmp_path);args=window(state)
    if change=='omitted_cutoff':args.pop('entry_cutoff')
    else:args[{'start':'window_start','end':'window_end','cutoff':'entry_cutoff'}[change]]+=timedelta(seconds=1)
    with pytest.raises(ValueError,match='original v2 kernel window/cutoff'):state.worker.tick([],**args)


def test_cutoff_buy_cancellation_and_later_sell_work_through_archive_handles(tmp_path):
    state,clock=setup(tmp_path);args=window(state)
    assert fill(state,clock,'buy','Buy')['status']=='filled'
    clock.now=args['entry_cutoff']-timedelta(seconds=2)
    state.wallet.enqueue('late-buy','BBB/USDT','Buy',created_at=clock.now)
    state.wallet.enqueue('known-exit','AAA/USDT','Sell',created_at=clock.now)
    state.compact();state=resume(state,clock);clock.advance(2)
    report=state.worker.tick([],**args)
    assert report['fills_processed']==['filled']
    rows={r[0]:r for r in state.iter_rows('wallet.intents')}
    assert rows['late-buy'][5:] == ('rejected','paper_entry_window_finished')
    assert rows['known-exit'][5]=='filled'
    assert list(state.iter_rows('wallet.fill_order'))==[(1,'buy'),(2,'known-exit')]


@pytest.mark.parametrize('bad',['nonfinite','deep','bytes','credentials'])
def test_invalid_public_input_is_rejected_before_wallet_effects(tmp_path,bad):
    state,clock=setup(tmp_path);state.wallet.enqueue('buy','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    q,r=market(clock)
    if bad=='nonfinite':q['extra']=float('nan')
    elif bad=='deep':
        extra={}
        for _ in range(30):extra={'nested':extra}
        q['extra']=extra
    elif bad=='bytes':q['extra']='x'*state.policy.maximum_row_bytes
    else:q['api_key']='fixture-do-not-persist'
    with pytest.raises(ValueError):state.wallet.execute('buy',q,r)
    assert state.wallet.snapshot()['fills']==[] and state.wallet.snapshot()['cash']=='100'
    assert list(state.iter_auxiliary_rows('wallet.fill_counter'))==[]


def test_public_symbol_name_is_not_interpreted_as_a_credential_field(tmp_path):
    state,clock=setup(tmp_path);q,r=market(clock,'TOKEN/USDT')
    assert state.wallet.mark({'TOKEN/USDT':q},{'TOKEN/USDT':r})['equity']=='100'
    q['authorization']='fixture-do-not-persist'
    with pytest.raises(ValueError,match='credentials'):state.wallet.mark({'TOKEN/USDT':q})


def test_prediction_batch_bytes_include_already_archived_negative_rows(tmp_path):
    state,clock=setup(tmp_path)
    prediction=dict(candidate_sha256='b'*64,opportunity='seen',predicted_at=clock.now.isoformat(),
        observed_at=clock.now.isoformat(),would_enter=False,pair='AAA/USDT',padding='x'*1800)
    identity=hashlib.sha256(('b'*64+'|seen').encode()).hexdigest()
    state.worker._seen(identity,'candidate_rejected');state.compact()
    # Use a small batch byte budget that still fits one maximum row.
    # A new contract/root, rather than editing the already frozen policy.
    other=tmp_path/'small';other.mkdir()
    state,clock=setup(other,maximum_batch_bytes=16384)
    state.worker._seen(identity,'candidate_rejected');state.compact()
    with pytest.raises(ValueError,match='batch bytes'):state.worker.tick([prediction]*10,**window(state))
    assert state.wallet.snapshot()['fills']==[]
