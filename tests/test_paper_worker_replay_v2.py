from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

import cryptoforge.paper_worker_replay_v2 as replay
from cryptoforge.paper_worker_replay_v2 import register_worker_replay,audit_worker_replay
from cryptoforge.paper_wallet_replay_v2 import ReplayPolicyV2 as ReplayPolicy
from test_paper_worker_capture_v2 import setup as capture_setup, tick, prediction, finish, audit as source_audit
from test_paper_capture_v4 import rehash
from test_paper_wallet import START,config
from test_paper_valuation_capture import raw_market
from test_native_paper_archive_v2 import WORKER_POLICY
from test_paper_capture_v3 import lifecycle

LOCAL = dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='synthetic-key-must-not-be-retained')


def policy(**changes):
    return replace(ReplayPolicy(maximum_scratch_bytes=16*1024*1024,maximum_state_rows=10000,
        maximum_active_rows=128,maximum_active_bytes=1024*1024,maximum_wall_seconds=120,
        minimum_available_memory_bytes=1,minimum_free_disk_bytes=16*1024*1024),**changes)


def setup(tmp_path, *, replay_policy=None, **changes):
    worker,clock = capture_setup(tmp_path,**changes)
    clock.now = START-timedelta(seconds=1)
    registered = register_worker_replay(tmp_path/'replay',capture_root=worker.root,
        expected_registration_sha256=worker.registration_sha256,policy=replay_policy or policy(),backend_env=LOCAL,clock=clock)
    clock.now = START
    return worker,clock,registered


def audit(worker,seal,registered,**changes):
    fields = dict(expected_registration_sha256=worker.registration_sha256,expected_seal_sha256=seal['seal_sha256'],
        replay_root=registered['root'],expected_replay_registration_sha256=registered['replay_registration_sha256'],
        clock=lambda:START+timedelta(seconds=20))
    fields.update(changes)
    return audit_worker_replay(worker.root,**fields)


def test_cash_only_controller_and_coverage_are_not_profit(tmp_path):
    worker,clock,registered = setup(tmp_path)
    for n in range(4):clock.now = START+timedelta(seconds=5*n);tick(worker,clock)
    seal = finish(worker,clock)
    before = {str(p):p.read_bytes() for root in (worker.root,Path(registered['root'])) for p in root.rglob('*') if p.is_file()}
    result = audit(worker,seal,registered)
    assert result['full_worker_decision_replay_pass'] and result['full_fifo_replay_pass'] and result['coverage_evidence_pass']
    assert result['ticks_checked']==4 and result['final_cash']=='100' and result['fills_checked']==0
    assert result['source_backend']==dict(name='local',api_origin='http://127.0.0.1:54321')
    for flag in ['source_poll_completeness_verified','paper_evidence_pass','economic_profitability_established','live_admission_granted','full_worker_or_host_qualified']:
        assert result[flag] is False
    assert before == {str(p):p.read_bytes() for root in (worker.root,Path(registered['root'])) for p in root.rglob('*') if p.is_file()}


def test_full_buy_stop_sell_and_loss_with_original_fee_math(tmp_path):
    worker,clock,registered = setup(tmp_path)
    row = prediction(clock)
    tick(worker,clock,[row]);clock.advance(5);tick(worker,clock,[row])
    worker._market = lambda pair:raw_market(clock,pair,price='95')
    clock.advance(5);tick(worker,clock);clock.advance(5);tick(worker,clock)
    q,r = raw_market(clock,price='95');clock.now = START+timedelta(seconds=20)
    # Use an actual original final observation at the endpoint.
    q,r = raw_market(clock,price='95');worker.mark_endpoint({q['pair']:q},{r['pair']:r})
    worker.terminate('completed');seal = worker.finalize()
    result = audit(worker,seal,registered)
    assert result['full_worker_decision_replay_pass'] and result['full_fifo_replay_pass'] and result['coverage_evidence_pass']
    assert result['fills_checked']==2 and result['segments_checked']==1
    assert D(result['allocated_realized_pnl'])<0 and D(result['final_cash'])<100


@pytest.mark.parametrize('case',['rejected','future','missing_observation','expired','wrong_candidate','old_forecast','cutoff'])
def test_independent_negative_prediction_paths(tmp_path,case):
    worker,clock,registered = setup(tmp_path,config=config(signal_expiry_seconds=6))
    row = prediction(clock)
    if case=='rejected':row['would_enter']=False
    if case=='future':row['predicted_at']=(START+timedelta(seconds=1)).isoformat()
    if case=='missing_observation':row.pop('observed_at')
    if case=='expired':clock.advance(10)
    if case=='wrong_candidate':row['candidate_sha256']='c'*64
    if case=='old_forecast':row['predicted_at']=(START-timedelta(seconds=1)).isoformat()
    if case=='cutoff':clock.advance(15);row=prediction(clock)
    tick(worker,clock,[row]);result=audit(worker,finish(worker,clock),registered)
    assert result['full_worker_decision_replay_pass'] and result['fills_checked']==0


@pytest.mark.parametrize('failure',[False,True])
def test_shared_exit_original_response_or_failure(tmp_path,failure):
    wp=deepcopy(WORKER_POLICY);wp['exits']['shared_exit_signal']=True
    def indicator(pair):
        if failure:raise TimeoutError('not-retained')
        return True,['test-rsi']
    worker,clock,registered=setup(tmp_path,worker_policy=wp,exit_indicator=indicator)
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    result=audit(worker,finish(worker,clock),registered)
    assert result['full_worker_decision_replay_pass']
    assert not result['coverage_evidence_pass']  # original window ended with inventory/pending exit


@pytest.mark.parametrize('failure',['market','wall'])
def test_market_failure_and_original_monotonic_wall_branch(tmp_path,monkeypatch,failure):
    import cryptoforge.paper_worker_capture_v2 as capture
    worker,clock,registered=setup(tmp_path)
    if failure=='market':
        def unavailable(pair):raise ConnectionError('not-retained')
        worker._market=unavailable
    else:
        values=iter((100.0,120.0));monkeypatch.setattr(capture,'monotonic',lambda:next(values))
    tick(worker,clock,[prediction(clock)])
    result=audit(worker,finish(worker,clock),registered)
    assert result['full_worker_decision_replay_pass'] and result['pending_intents']==1 and not result['coverage_evidence_pass']


def test_source_trace_passes_false_indicator_but_independent_controller_rejects(tmp_path):
    wp=deepcopy(WORKER_POLICY);wp['exits']['shared_exit_signal']=True
    worker,clock,registered=setup(tmp_path,worker_policy=wp,exit_indicator=lambda pair:(False,[]))
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    seal=finish(worker,clock)
    def mutate(record):
        event=record['payload']
        if record['kind']=='complete' and event.get('phase')=='exit':event['result']['exits']=True
    seal=rehash(worker,seal,mutate)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='independent controller'):audit(worker,seal,registered)


def test_source_trace_passes_false_monotonic_branch_but_independent_controller_rejects(tmp_path):
    worker,clock,registered=setup(tmp_path)
    tick(worker,clock,[prediction(clock)]);seal=finish(worker,clock)
    calls=0
    def mutate(record):
        nonlocal calls
        event=record['payload']
        if event.get('phase')=='monotonic':
            event['value']=100.0 if calls==0 else 200.0;calls+=1
    seal=rehash(worker,seal,mutate)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='independent controller'):audit(worker,seal,registered)


def test_immutable_opportunity_conflict_across_batches_is_not_ignored(tmp_path):
    worker,clock,registered=setup(tmp_path)
    row=prediction(clock,would_enter=False);tick(worker,clock,[row]);clock.advance(5)
    tick(worker,clock,[dict(row,would_enter=True)]);seal=finish(worker,clock)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    with pytest.raises(ValueError,match='immutable opportunity'):audit(worker,seal,registered)


def test_reader_has_no_production_database_or_backend_resolver_dependency(tmp_path,monkeypatch):
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    def forbidden(*args,**kwargs):raise AssertionError('no live backend resolver or connection in replay')
    monkeypatch.setattr(replay,'resolve_backend',forbidden)
    assert audit(worker,seal,registered)['full_worker_decision_replay_pass']
    assert 'synthetic-key-must-not-be-retained' not in (Path(registered['root'])/'registration.json').read_text()


@pytest.mark.parametrize('case',['cloud','late','capacity','existing','bad_pin'])
def test_new_pre_start_local_replay_contract_is_required(tmp_path,case):
    worker,clock=capture_setup(tmp_path);clock.now=START-timedelta(seconds=1)
    env=LOCAL;root=tmp_path/'replay';pin=worker.registration_sha256;p=policy()
    if case=='cloud':env=dict(CRYPTOFORGE_BACKEND='supabase',SUPABASE_URL='https://synthetic.invalid',SUPABASE_SECRET_KEY='dummy')
    if case=='late':clock.now=START
    if case=='capacity':p=policy(maximum_active_bytes=65536)
    if case=='existing':root.mkdir()
    if case=='bad_pin':pin='f'*64
    with pytest.raises((ValueError,OSError)):
        register_worker_replay(root,capture_root=worker.root,expected_registration_sha256=pin,policy=p,backend_env=env,clock=clock)


def test_pre_end_gate_does_not_open_replay_or_source_outcomes(tmp_path):
    worker,clock,registered=setup(tmp_path)
    for p in [worker.root/'native',worker.root/'storage',Path(registered['root'])]:p.rename(p.with_name(p.name+'-hidden'))
    result=audit_worker_replay(worker.root,expected_registration_sha256=worker.registration_sha256,clock=clock)
    assert result['performance_hidden'] and not result['full_worker_decision_replay_pass']


def test_cli_real_clock_and_exclusive_output(tmp_path,capsys):
    spec=importlib.util.spec_from_file_location('worker_replay_cli',Path(__file__).resolve().parents[1]/'scripts/audit_paper_worker_replay_v2.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    args=['--root',str(worker.root),'--expected-registration-sha256',worker.registration_sha256,
        '--expected-seal-sha256',seal['seal_sha256'],'--replay-root',registered['root'],
        '--expected-replay-registration-sha256',registered['replay_registration_sha256']]
    with pytest.raises(SystemExit):cli.main(args+['--as-of',START.isoformat()])
    assert cli.main(args+['--output',str(worker.root/'invalid')])==1
    out=tmp_path/'result.json';assert cli.main(args+['--output',str(out)])==0
    assert json.loads(out.read_bytes())['full_worker_decision_replay_pass']
    assert cli.main(args+['--output',str(out)])==1


@pytest.mark.parametrize('case',['timeout','closeout','expired_pending','duplicate','position_limit','signal_limit'])
def test_independent_controller_execution_paths(tmp_path,case):
    changes={};wp=deepcopy(WORKER_POLICY)
    if case=='timeout':wp['exits']['maximum_hold_seconds']=4
    if case=='closeout':changes.update(end=START+timedelta(seconds=25),lifecycle=lifecycle(maximum_operations_per_poll=1,closeout_seconds=10))
    if case=='expired_pending':changes['config']=config(signal_expiry_seconds=6)
    if case=='position_limit':changes['config']=config(max_positions=1)
    if case=='signal_limit':wp['runtime']['maximum_new_signals_per_tick']=1
    worker,clock,registered=setup(tmp_path,worker_policy=wp,**changes)
    rows=[prediction(clock)]
    if case=='duplicate':rows*=2
    if case in {'position_limit','signal_limit'}:rows.append(prediction(clock,'second',pair='BBB/USDT'))
    tick(worker,clock,rows)
    clock.advance(10 if case=='expired_pending' else 5);tick(worker,clock)
    if case in {'timeout','closeout'}:
        while clock.now<START+timedelta(seconds=15):clock.advance(5);tick(worker,clock)
        if case=='closeout':clock.advance(5);tick(worker,clock)
    end=START+timedelta(seconds=25 if case=='closeout' else 20)
    clock.now=end;q,r=raw_market(clock)
    if case=='position_limit':
        quotes={};rules={}
        for pair in ('AAA/USDT','BBB/USDT'):
            q,r=raw_market(clock,pair);quotes[pair]=q;rules[pair]=r
    else:quotes,rules={q['pair']:q},{r['pair']:r}
    worker.mark_endpoint(quotes,rules);worker.terminate('completed');seal=worker.finalize()
    result=audit(worker,seal,registered,clock=clock)
    assert result['full_worker_decision_replay_pass'] and result['full_fifo_replay_pass']
    if case in {'timeout','closeout'}:
        assert result['fills_checked']==2 and result['coverage_evidence_pass']
    if case=='expired_pending':assert result['fills_checked']==0 and result['pending_intents']==0
    if case in {'duplicate','position_limit','signal_limit'}:assert result['fills_checked']==1


def test_strict_stake_cash_conservation_verifies_new_native_sizing(tmp_path):
    worker,clock,registered=setup(tmp_path,config=config(capital=D(6),stake=D(6),slippage=D(0),entry_fee=D(0),exit_fee=D(0)))
    worker._market=lambda pair:raw_market(clock,pair,price='17',step='1e-28')
    tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    seal=finish(worker,clock)
    assert source_audit(worker,seal)['worker_source_trace_pass']
    result=audit(worker,seal,registered)
    assert result['full_fifo_replay_pass'] and D(result['final_cash'])>=0
    assert result['fills_checked']==1


def test_reader_never_calls_native_worker_wallet_or_providers(tmp_path,monkeypatch):
    from cryptoforge.paper_worker_v2 import PaperWorkerV2 as PaperWorker
    from cryptoforge.paper_wallet_v2 import PaperWalletV2 as PaperWallet
    from cryptoforge.native_paper_archive_v2 import NativePaperArchiveV2 as NativePaperArchive
    worker,clock,registered=setup(tmp_path);tick(worker,clock,[prediction(clock)]);clock.advance(5);tick(worker,clock)
    seal=finish(worker,clock)
    def forbidden(*args,**kwargs):raise AssertionError('native production path must not be used by independent replay')
    monkeypatch.setattr(PaperWorker,'tick',forbidden);monkeypatch.setattr(PaperWallet,'execute',forbidden)
    monkeypatch.setattr(PaperWallet,'mark',forbidden);monkeypatch.setattr(NativePaperArchive,'resume',forbidden)
    worker._market=forbidden;worker._exit=forbidden
    assert audit(worker,seal,registered)['full_worker_decision_replay_pass']


@pytest.mark.parametrize('case',['rows','memory','disk','wall','sqlite_pages'])
def test_scratch_and_runtime_budgets_block_and_cleanup(tmp_path,monkeypatch,case):
    worker,clock,registered=setup(tmp_path,replay_policy=policy(maximum_state_rows=3) if case=='rows' else policy())
    tick(worker,clock,[prediction(clock)]);seal=finish(worker,clock)
    parent=tmp_path/'scratch';parent.mkdir()
    if case in {'memory','disk'}:
        import cryptoforge.paper_wallet_replay_v2 as streaming
        original=streaming.measure_resources
        key='available_memory_bytes' if case=='memory' else 'free_disk_bytes'
        monkeypatch.setattr(streaming,'measure_resources',lambda root:{**original(root),key:0})
    elif case=='wall':
        values=iter((0,121*10**9));monkeypatch.setattr(replay,'monotonic_ns',lambda:next(values))
    elif case=='sqlite_pages':
        original=replay._Scratch
        def limited(path,p):return original(path,replace(p,maximum_scratch_bytes=131072))
        monkeypatch.setattr(replay,'_Scratch',limited)
        original_put=replay._WorkerReplay.batches
        def fill_index(self,rows):
            for n in range(100):self.scratch.put('replay.synthetic',[str(n),'x'*4096])
            return original_put(self,rows)
        monkeypatch.setattr(replay._WorkerReplay,'batches',fill_index)
    with pytest.raises((ValueError,sqlite3.Error)):
        audit(worker,seal,registered,scratch_parent=parent)
    assert list(parent.iterdir())==[]


@pytest.mark.parametrize('case',['missing_contract','wrong_pin','contract_changed','extra_file','root_alias','scratch_inside_source','scratch_inside_replay'])
def test_original_pins_namespace_and_separate_scratch_required(tmp_path,case):
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    changes={}
    if case=='missing_contract':changes['replay_root']=None
    if case=='wrong_pin':changes['expected_replay_registration_sha256']='f'*64
    if case=='contract_changed':(Path(registered['root'])/'registration.json').write_text('{}')
    if case=='extra_file':(Path(registered['root'])/'extra').write_text('x')
    if case=='root_alias':
        alias=tmp_path/'alias';alias.symlink_to(Path(registered['root']),target_is_directory=True);changes['replay_root']=alias
    if case=='scratch_inside_source':changes['scratch_parent']=worker.root
    if case=='scratch_inside_replay':changes['scratch_parent']=Path(registered['root'])
    with pytest.raises((ValueError,OSError,KeyError)):audit(worker,seal,registered,**changes)


def test_registration_runtime_drift_blocks_without_touching_sources(tmp_path,monkeypatch):
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    before={str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}
    monkeypatch.setattr(replay,'runtime_hashes',lambda:{'drift':'f'*64})
    with pytest.raises(ValueError,match='identity/runtime'):audit(worker,seal,registered)
    assert before=={str(p):p.read_bytes() for p in worker.root.rglob('*') if p.is_file()}


def test_many_negative_batches_use_indexed_history_and_bounded_active_state(tmp_path):
    from test_paper_capture_v3 import storage
    worker,clock,registered=setup(tmp_path,end=START+timedelta(seconds=65),
        storage_policy=storage(maximum_events=2048,maximum_segment_events=64,maximum_record_bytes=32768,maximum_total_bytes=16*1024*1024))
    for n in range(13):
        clock.now=START+timedelta(seconds=5*n)
        tick(worker,clock,[prediction(clock,'op-'+str(n),would_enter=False)])
    clock.now=START+timedelta(seconds=65);worker.mark_endpoint({},{});worker.terminate('completed');seal=worker.finalize()
    parent=tmp_path/'scratch';parent.mkdir()
    result=audit(worker,seal,registered,scratch_parent=parent,clock=clock)
    assert result['ticks_checked']==13 and result['fills_checked']==0
    assert result['scratch_rows']>13*2 and result['peak_active_bytes']<20000
    assert result['coverage_evidence_pass'] and list(parent.iterdir())==[]


def test_immutable_worker_history_uses_identity_hash_without_payload_reuse(tmp_path,monkeypatch):
    worker,clock,registered=setup(tmp_path);tick(worker,clock);seal=finish(worker,clock)
    original=replay._WorkerReplay.operation
    checked=[]
    def inspect(self,prepared,complete):
        original(self,prepared,complete)
        if prepared['operation']=='worker_event':
            with pytest.raises(ValueError,match='immutable replay row'):
                self.scratch.get('worker.worker_events',self.worker_events)
            checked.append(self.worker_events)
    monkeypatch.setattr(replay._WorkerReplay,'operation',inspect)
    assert audit(worker,seal,registered)['full_worker_decision_replay_pass'] and checked==[1]
