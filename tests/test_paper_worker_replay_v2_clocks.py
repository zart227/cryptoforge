"""Adversarial nested-clock, financial and endpoint checks for replay v2."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D,Inexact,localcontext
from fractions import Fraction
import json
from pathlib import Path
import sqlite3

import pytest
from cryptoforge.evidence_segments import canonical,digest
from cryptoforge.paper_worker_replay_v2 import register_worker_replay
from test_paper_worker_replay_v2 import setup,audit,policy,LOCAL
from test_paper_worker_capture_v2 import tick,prediction,finish,audit as source_audit,setup as capture_setup
from test_paper_worker_capture_v2_clocks import arm_lock_observation
from test_paper_wallet import START,config
from test_paper_capture_v3 import storage,lifecycle
from test_paper_valuation_capture import raw_market


@pytest.mark.parametrize('case',['cutoff','expiry','fill'])
def test_independent_financial_replay_uses_post_lock_observation(tmp_path,monkeypatch,case):
    end=START+timedelta(seconds=60 if case=='expiry' else 20)
    worker,clock,registered=setup(tmp_path,end=end,storage_policy=storage(maximum_events=2048,
        maximum_segment_events=64,maximum_record_bytes=32768,maximum_total_bytes=16*1024*1024))
    tick(worker,clock,[prediction(clock)])
    clock.now=START+timedelta(seconds=29 if case=='expiry' else 10)
    at=START+timedelta(seconds={'cutoff':15,'expiry':31,'fill':11}[case])
    arm_lock_observation(worker,clock,monkeypatch,at)
    report=tick(worker,clock)
    assert report['fills_processed']==['filled' if case=='fill' else 'rejected']
    monkeypatch.undo();clock.now=end
    worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['full_worker_decision_replay_pass'] and result['full_fifo_replay_pass']
    assert result['fills_checked']==(1 if case=='fill' else 0)
    if case!='fill':assert result['final_cash']=='100'


def test_second_rejection_clock_is_used_for_intent_observed_at(tmp_path,monkeypatch):
    worker,clock,registered=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.now=START+timedelta(seconds=10)
    gate=arm_lock_observation(worker,clock,monkeypatch,START+timedelta(seconds=15))
    def actual():
        if gate['lock']:clock.now+=timedelta(milliseconds=1)
        return clock.now
    worker.clock=actual
    assert tick(worker,clock)['fills_processed']==['rejected']
    monkeypatch.undo();worker.clock=clock
    assert audit(worker,finish(worker,clock),registered)['full_fifo_replay_pass']


@pytest.mark.parametrize('kind',['wrong_net_quantity','wrong_fee_amount','wrong_fee_basis','suboptimal_sizing'])
def test_source_consistent_bad_acquisition_cannot_pass_independent_math(tmp_path,monkeypatch,kind):
    import cryptoforge.paper_wallet_v2 as native
    worker,clock,registered=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.advance(5)
    original=native.spot_acquisition
    def wrong(**kwargs):
        result=original(**kwargs)
        if kind=='wrong_net_quantity':return replace(result,net_quantity=result.net_quantity+D('.000001'))
        if kind=='wrong_fee_amount':return replace(result,fee_amount=result.fee_amount/2)
        if kind=='wrong_fee_basis':return replace(result,fee_quote_equivalent=result.fee_quote_equivalent/2)
        changed=dict(kwargs,stake=kwargs['stake']-D('.02'))
        return original(**changed)
    monkeypatch.setattr(native,'spot_acquisition',wrong)
    assert tick(worker,clock)['fills_processed']==['filled']
    monkeypatch.undo();seal=finish(worker,clock)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='independent cash/FIFO'):audit(worker,seal,registered)


def test_source_consistent_old_28_digit_allocation_is_rejected(tmp_path,monkeypatch):
    import cryptoforge.paper_wallet_v2 as native
    worker,clock,registered=setup(tmp_path)
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    worker._market=lambda pair:raw_market(clock,pair,price='95')
    clock.advance(5);tick(worker,clock)
    def old_allocation(basis,sold,quantity):
        with localcontext() as ctx:
            ctx.prec=28
            return basis*sold/quantity
    monkeypatch.setattr(native,'allocate_basis',old_allocation)
    clock.advance(5);assert tick(worker,clock)['fills_processed']==['filled']
    monkeypatch.undo();seal=finish(worker,clock)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='independent cash/FIFO'):audit(worker,seal,registered)


def test_reader_uses_neither_native_financial_code_nor_global_decimal_context(tmp_path,monkeypatch):
    import cryptoforge.paper_wallet_v2 as wallet
    import cryptoforge.paper_worker_v2 as worker_module
    import cryptoforge.spot_buy_math_v2 as math
    worker,clock,registered=setup(tmp_path,config=config(slippage=D(0),entry_fee=D(0),exit_fee=D(0)))
    worker._market=lambda pair:raw_market(clock,pair,price='17',step='1e-28')
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock);seal=finish(worker,clock)
    def forbidden(*args,**kwargs):raise AssertionError('independent replay invoked native financial execution')
    for name in ('spot_acquisition','spot_sale','allocate_basis','exact_product','sum_exact','subtract_exact','floor_quantity'):
        monkeypatch.setattr(math,name,forbidden)
        if hasattr(wallet,name):monkeypatch.setattr(wallet,name,forbidden)
    monkeypatch.setattr(wallet.PaperWalletV2,'execute',forbidden);monkeypatch.setattr(wallet.PaperWalletV2,'mark',forbidden)
    monkeypatch.setattr(worker_module.PaperWorkerV2,'tick',forbidden)
    with localcontext() as ctx:
        ctx.prec=3;ctx.traps[Inexact]=True
        result=audit(worker,seal,registered)
        assert ctx.prec==3 and ctx.traps[Inexact]
    assert result['full_fifo_replay_pass'] and result['full_worker_decision_replay_pass']


def test_post_end_endpoint_is_not_backfilled_into_unknown_window(tmp_path):
    worker,clock,registered=setup(tmp_path)
    clock.now=START+timedelta(seconds=20)
    def advancing():clock.now+=timedelta(milliseconds=1);return clock.now
    worker.clock=advancing
    worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['full_worker_decision_replay_pass']
    assert result['final_valuation_after_window'] and result['final_equity_observed_at']>worker.protocol['end']
    assert result['endpoint_observations_backfill_window'] is False
    assert result['coverage']['known_seconds']=='0' and not result['coverage_evidence_pass']


@pytest.mark.parametrize('stage',['before_freeze','after_fsync'])
def test_replay_registration_cannot_finish_late(tmp_path,monkeypatch,stage):
    import cryptoforge.paper_worker_replay_v2 as replay
    worker,clock=capture_setup(tmp_path);clock.now=START-timedelta(seconds=1)
    original_write=replay._write_new;original_resources=replay._resources
    def resources(*args):
        result=original_resources(*args)
        if stage=='before_freeze':clock.now=START
        return result
    def write(*args):
        result=original_write(*args)
        if stage=='after_fsync':clock.now=START
        return result
    monkeypatch.setattr(replay,'_resources',resources);monkeypatch.setattr(replay,'_write_new',write)
    root=tmp_path/'late'
    with pytest.raises(ValueError,match='start'):
        register_worker_replay(root,capture_root=worker.root,expected_registration_sha256=worker.registration_sha256,
            policy=policy(),backend_env=LOCAL,clock=clock)
    assert not (root/'registration.json').exists()


def test_replay_must_bind_same_local_backend_as_kernel(tmp_path):
    worker,clock=capture_setup(tmp_path);clock.now=START-timedelta(seconds=1)
    env=dict(LOCAL,CRYPTOFORGE_LOCAL_API_URL='http://127.0.0.1:54322')
    with pytest.raises(ValueError,match='original kernel'):
        register_worker_replay(tmp_path/'wrong-backend',capture_root=worker.root,
            expected_registration_sha256=worker.registration_sha256,policy=policy(),backend_env=env,clock=clock)


def alter_one_nested_clock(worker,seal,*,extra):
    """Reissue all structural references, preserving source/native rows unchanged."""
    from cryptoforge.evidence_segments import _record,_frame
    records=list(worker.log.iter_events(expected_head_sha256=seal['head_sha256'],expected_catalog_sha256=seal['catalog_sha256']))
    target=next(r['payload']['prepared_seq'] for r in records if r['kind']=='complete' and r['payload'].get('phase')=='action'
        and type(r['payload'].get('result')) is dict and r['payload']['result'].get('status')==('filled' if extra else 'rejected'))
    clocks=[r for r in records if r['payload'].get('phase')=='clock' and r['payload'].get('action_prepared_seq')==target]
    assert len(clocks)==(1 if extra else 2)
    if extra:
        index=next(i for i,r in enumerate(records) if r['kind']=='complete' and r['payload'].get('phase')=='action' and r['payload']['prepared_seq']==target)
        records.insert(index,dict(kind='complete',payload=clocks[0]['payload'],inserted=True))
    else:records=[r for r in records if r.get('sequence')!=clocks[-1]['sequence']]
    mapping={r['sequence']:i for i,r in enumerate(records,1) if not r.get('inserted')}
    previous=worker.log.manifest_sha256;frames=[]
    for i,record in enumerate(records,1):
        event=json.loads(json.dumps(record['payload']))
        if record['kind']=='complete' and event.get('phase')=='action' and event['prepared_seq']==target:
            if extra:event['native_clocks'].append(event['native_clocks'][0])
            else:event['native_clocks'].pop()
        for field in ('tick_sequence','prepared_seq','action_prepared_seq'):
            if event.get(field) is not None:event[field]=mapping[event[field]]
        current=_record(i,record['kind'],event,previous);previous=current['sha256'];frames.append(_frame(current))
    raw=b''.join(frames);worker.log._path(1).write_bytes(raw)
    catalog=worker.root/'storage'/'catalog.sqlite'
    with sqlite3.connect(catalog) as db:
        assert db.execute('SELECT count(*) FROM segments').fetchone()[0]==1
        db.execute('UPDATE segments SET first_seq=1,last_seq=?,count=?,previous=?,bytes=?,sealed_sha=?',
            (len(frames),len(frames),worker.log.manifest_sha256,len(raw),digest(raw)))
        db.execute('UPDATE head SET seq=?,sha=?',(len(frames),previous))
    changed=json.loads((worker.root/'sealed.json').read_bytes())
    changed.update(sequence=len(frames),head_sha256=previous,catalog_sha256=digest(catalog.read_bytes()))
    encoded=canonical(changed);(worker.root/'sealed.json').write_bytes(encoded)
    return {**changed,'seal_sha256':digest(encoded)}


@pytest.mark.parametrize('extra',[True,False])
def test_structurally_consistent_extra_or_missing_native_clock_is_rejected(tmp_path,monkeypatch,extra):
    worker,clock,registered=setup(tmp_path,storage_policy=storage(maximum_events=1024,
        maximum_segment_events=256,maximum_record_bytes=32768,maximum_total_bytes=16*1024*1024))
    tick(worker,clock,[prediction(clock)]);clock.now=START+timedelta(seconds=10)
    if not extra:arm_lock_observation(worker,clock,monkeypatch,START+timedelta(seconds=15))
    tick(worker,clock);monkeypatch.undo()
    seal=alter_one_nested_clock(worker,finish(worker,clock),extra=extra)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='independent native clock'):audit(worker,seal,registered)


def test_pair_identifier_token_has_independent_replay_coverage(tmp_path):
    worker,clock,registered=setup(tmp_path)
    tick(worker,clock,[prediction(clock,pair='TOKEN/USDT')]);clock.advance(5);tick(worker,clock)
    result=audit(worker,finish(worker,clock),registered)
    assert result['full_fifo_replay_pass'] and result['full_worker_decision_replay_pass']


def test_tradable_closeouts_and_counter_survive_compaction_restart_in_independent_replay(tmp_path):
    from test_native_paper_archive_v2 import policy as native_policy
    from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
    worker,clock,registered=setup(tmp_path,end=START+timedelta(seconds=65),native_policy=native_policy(maximum_active_rows=16),
        storage_policy=storage(maximum_events=2048,maximum_segment_events=64,maximum_record_bytes=32768,
            maximum_total_bytes=16*1024*1024))
    for cycle in range(3):
        clock.now=START+timedelta(seconds=cycle*20);worker._market=lambda pair:raw_market(clock,pair,price='100')
        tick(worker,clock,[prediction(clock,opportunity=str(cycle))]);clock.advance(5);tick(worker,clock)
        worker._market=lambda pair:raw_market(clock,pair,price='95');clock.advance(5);tick(worker,clock);clock.advance(5);tick(worker,clock)
        worker=CapturedPaperWorkerV2.resume(worker.root,expected_registration_sha256=worker.registration_sha256,
            market=lambda pair:raw_market(clock,pair),clock=clock)
    clock.now=START+timedelta(seconds=65);worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['full_fifo_replay_pass'] and result['full_worker_decision_replay_pass']
    assert result['fills_checked']==6 and result['segments_checked']==5
    assert result['segments_checked']==len(list(worker._source.iter_rows('wallet.closed_segments')))
    assert Fraction(D(result['final_cash']))+sum((Fraction(D(row[4])) for row in worker._source.iter_rows('wallet.lots')),Fraction(0))==100+Fraction(D(result['allocated_realized_pnl']))


def test_source_audit_has_its_own_per_record_budget_without_global_mutation(tmp_path,monkeypatch):
    import cryptoforge.paper_worker_replay_v2 as replay
    import cryptoforge.paper_worker_capture_v2 as capture
    worker,clock,registered=setup(tmp_path);tick(worker,clock,[prediction(clock)]);seal=finish(worker,clock)
    original=capture.SegmentedEventLog
    calls=[]
    def elapsed():
        calls.append(1)
        return 0 if len(calls)<=15 else 121*10**9
    def financial_replay_must_not_start(*args,**kwargs):raise AssertionError('budget checked only after source trace')
    monkeypatch.setattr(replay,'monotonic_ns',elapsed)
    monkeypatch.setattr(replay._WorkerReplay,'__init__',financial_replay_must_not_start)
    with pytest.raises(ValueError,match='wall budget'):audit(worker,seal,registered)
    assert len(calls)>15 and capture.SegmentedEventLog is original


def test_runtime_preserves_the_stricter_original_capture_memory_floor(tmp_path,monkeypatch):
    import cryptoforge.paper_wallet_replay_v2 as wallet_replay
    worker,clock,registered=setup(tmp_path,lifecycle=lifecycle(maximum_operations_per_poll=1,minimum_available_memory_bytes=1_000_000))
    tick(worker,clock);seal=finish(worker,clock)
    original=wallet_replay.measure_resources
    monkeypatch.setattr(wallet_replay,'measure_resources',lambda path:{**original(path),'available_memory_bytes':500_000})
    with pytest.raises(ValueError,match='combined capture/replay resource floor'):audit(worker,seal,registered)


@pytest.mark.parametrize('kind',['wrong_exit_fee','wrong_cash_proceeds'])
def test_source_consistent_wrong_sale_cannot_pass_independent_math(tmp_path,monkeypatch,kind):
    import cryptoforge.paper_wallet_v2 as native
    worker,clock,registered=setup(tmp_path)
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    worker._market=lambda pair:raw_market(clock,pair,price='95');clock.advance(5);tick(worker,clock)
    original=native.spot_sale
    def wrong(**kwargs):
        result=original(**kwargs)
        if kind=='wrong_exit_fee':return replace(result,fee_amount=result.fee_amount/2)
        return replace(result,cash_proceeds=result.cash_proceeds+D('.00000001'))
    monkeypatch.setattr(native,'spot_sale',wrong);clock.advance(5)
    assert tick(worker,clock)['fills_processed']==['filled']
    monkeypatch.undo();seal=finish(worker,clock)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='independent cash/FIFO'):audit(worker,seal,registered)


@pytest.mark.parametrize('field',['source_backend','kernel_contract_sha256','kernel_registration_sha256',
    'native_manifest_sha256','native_ready_sha256','precision','allocation_places'])
def test_reissued_registration_sha_cannot_override_original_binding(tmp_path,field):
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    path=Path(registered['root'])/'registration.json';value=json.loads(path.read_bytes())
    if field=='source_backend':value[field]['api_origin']='http://127.0.0.1:54322'
    elif field in {'precision','allocation_places'}:value['arithmetic_contract'][field]=28
    else:value[field]='f'*64
    raw=canonical(value);path.write_bytes(raw)
    registered=dict(registered,replay_registration_sha256=digest(raw))
    with pytest.raises(ValueError,match='binding differs'):audit(worker,seal,registered)


def test_frozen_replay_rejects_new_source_schema_without_mutation(tmp_path):
    from cryptoforge.paper_worker_replay import audit_worker_replay as frozen
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    before={str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}
    with pytest.raises((ValueError,KeyError)):
        frozen(worker.root,expected_registration_sha256=worker.registration_sha256,expected_seal_sha256=seal['seal_sha256'],
            replay_root=registered['root'],expected_replay_registration_sha256=registered['replay_registration_sha256'],clock=clock)
    assert before=={str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}


def test_post_end_dust_classification_cannot_hide_material_inventory_at_window_end(tmp_path):
    worker,clock,registered=setup(tmp_path,end=START+timedelta(seconds=30),
        lifecycle=lifecycle(maximum_operations_per_poll=1,maximum_mark_gap_seconds=15))
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    worker._market=lambda pair:raw_market(clock,pair,price='95')
    clock.advance(5);tick(worker,clock);clock.advance(5);tick(worker,clock)
    worker._market=lambda pair:raw_market(clock,pair,price='1000000',step='1e-8');clock.advance(5);tick(worker,clock)
    assert worker._source.wallet.snapshot()['open_lots']
    clock.now=START+timedelta(seconds=31);q,r=raw_market(clock,price='1',step='1e-8')
    marked=worker.mark_endpoint({q['pair']:q},{r['pair']:r})
    assert marked['nontradable_small_basis_pairs']==['AAA/USDT']
    worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['full_fifo_replay_pass'] and result['full_worker_decision_replay_pass']
    assert result['final_valuation_after_window']
    assert result['material_inventory_pairs']==['AAA/USDT']
    assert not result['lifecycle_checks']['closeout_no_material_inventory']
    assert not result['coverage_evidence_pass']
    assert result['last_in_window_equity_observed_at']==(START+timedelta(seconds=20)).isoformat()


def test_a_post_end_only_mark_does_not_create_an_in_window_valuation(tmp_path):
    worker,clock,registered=setup(tmp_path);clock.now=START+timedelta(seconds=21)
    worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['final_equity']=='100' and result['final_valuation_after_window']
    assert result['last_in_window_equity'] is None
    assert not result['lifecycle_checks']['window_valuation_source_verified']
    assert not result['coverage_evidence_pass']


def test_registration_cannot_write_inside_original_kernel_root(tmp_path):
    worker,clock=capture_setup(tmp_path);clock.now=START-timedelta(seconds=1)
    kernel=Path(worker.protocol['kernel_root']);before={str(p):p.read_bytes() for p in kernel.iterdir()}
    with pytest.raises(ValueError,match='namespace|outside'):
        register_worker_replay(kernel/'new-replay',capture_root=worker.root,
            expected_registration_sha256=worker.registration_sha256,policy=policy(),backend_env=LOCAL,clock=clock)
    assert before=={str(p):p.read_bytes() for p in kernel.iterdir()}


def test_scratch_cannot_use_original_kernel_root(tmp_path):
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    kernel=Path(worker.protocol['kernel_root']);before={str(p):p.read_bytes() for p in kernel.iterdir()}
    with pytest.raises(ValueError,match='private scratch parent'):
        audit(worker,seal,registered,scratch_parent=kernel)
    assert before=={str(p):p.read_bytes() for p in kernel.iterdir()}


@pytest.mark.parametrize('sealed',[False,True])
def test_cli_output_cannot_enter_original_kernel_namespace(tmp_path,monkeypatch,sealed):
    import importlib.util
    spec=importlib.util.spec_from_file_location('v2_cli',Path(__file__).resolve().parents[1]/'scripts/audit_paper_worker_replay_v2.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    worker,clock,registered=setup(tmp_path)
    args=['--root',str(worker.root),'--expected-registration-sha256',worker.registration_sha256,
        '--replay-root',registered['root'],'--expected-replay-registration-sha256',registered['replay_registration_sha256']]
    if sealed:
        tick(worker,clock);seal=finish(worker,clock);args+=['--expected-seal-sha256',seal['seal_sha256']]
    else:monkeypatch.setattr(cli,'audit_worker_replay',lambda *args,**kwargs:dict(status='sealed_until_capture_end',performance_hidden=True))
    kernel=Path(worker.protocol['kernel_root']);before={str(p):p.read_bytes() for p in kernel.iterdir()}
    assert cli.main(args+['--output',str(kernel/'audit.json')])==1
    assert before=={str(p):p.read_bytes() for p in kernel.iterdir()}
