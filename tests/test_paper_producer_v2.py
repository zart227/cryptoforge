"""Adversarial v2 kernel checks. Fixtures do not qualify an actual study."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D, Inexact, localcontext
from fractions import Fraction as F
import hashlib
import json
import sqlite3

import pytest

from cryptoforge.paper_wallet import PaperWallet
from cryptoforge.paper_wallet_v2 import PaperWalletV2
from cryptoforge.paper_worker import PaperWorker
from cryptoforge.paper_worker_v2 import PaperWorkerV2
from cryptoforge.paper_producer_v2 import VERSION
from cryptoforge.spot_buy_math import spot_acquisition as legacy_acquisition
from cryptoforge.spot_buy_math_v2 import spot_acquisition, floor_quantity
from test_paper_wallet import Clock, START, config, market, fill
from test_paper_worker import prediction


@pytest.mark.parametrize('fee_currency', ['base', 'quote'])
@pytest.mark.parametrize('precision', [6, 28, 80])
@pytest.mark.parametrize('stake,price,step,fee', [
    ('6','17','1e-28','0'), ('6','17','1e-28','.0018'),
    ('6','0.00017','1e-8','.0001'), ('6','100','.0001','.0018'),
    ('1','3','.01','.1'), ('1','999','1','0'),
    ('0.000001','0.00000007','1e-28','.003'),
])
def test_sizing_is_affordable_maximal_and_context_independent(fee_currency,precision,stake,price,step,fee):
    values=dict(stake=D(stake),price=D(price),quantity_step=D(step),fee_fraction=D(fee),fee_currency=fee_currency)
    with localcontext() as context:
        context.prec=precision;context.traps[Inexact]=True
        result=spot_acquisition(**values)
    # Check economic invariants in rational arithmetic, independently of
    # Decimal multiplication/division and of the producer's own assertions.
    gross=F(result.gross_quantity);unit=F(step);quote=F(price);fraction=F(fee)
    cost=lambda quantity:quantity*quote*(1+fraction if fee_currency=='quote' else 1)
    assert gross/unit==(gross/unit).numerator
    assert cost(gross)==F(result.cash_cost)<=F(stake)<cost(gross+unit)
    assert F(result.net_quantity)==gross*(1-fraction if fee_currency=='base' else 1)
    assert F(result.fee_quote_equivalent)==gross*quote*fraction


def test_old_rounding_defect_is_reproduced_and_new_wallet_never_borrows(tmp_path):
    clock=Clock();cfg=config(capital=D(6),stake=D(6),slippage=D(0),entry_fee=D(0),exit_fee=D(0))
    legacy=legacy_acquisition(stake=D(6),price=D(17),quantity_step=D('1e-28'),fee_fraction=D(0),fee_currency='base')
    assert legacy.cash_cost>D(6)
    wallet=PaperWalletV2(tmp_path/'v2.sqlite',candidate_sha='a'*64,config=cfg,clock=clock)
    trade=fill(wallet,clock,'buy','Buy',price='17',step='1e-28')['fill']
    assert F(trade['cost'])<=6 and F(wallet.snapshot()['cash'])==6-F(trade['cost'])>=0
    assert D(trade['order_quantity'])==D('0.3529411764705882352941176470')
    q,r=market(clock,price='17',step='1e-28');wallet.mark({'AAA/USDT':q},{'AAA/USDT':r})
    clock.advance();assert fill(wallet,clock,'other','Buy',pair='BBB/USDT',price='17',step='1e-28')['reason']=='insufficient_shared_cash'


def same_clock_history(path,cls,*,restart=False):
    clock=Clock();cfg=config()
    wallet=cls(path,candidate_sha='a'*64,config=cfg,clock=clock)
    for identity,side in [('z-first','Buy'),('sell-one','Sell'),('a-second','Buy'),('sell-two','Sell')]:
        wallet.enqueue(identity,'AAA/USDT',side,created_at=clock.now)
    clock.advance();quote,rules=market(clock)
    for identity in ['z-first','sell-one','a-second','sell-two']:
        assert wallet.execute(identity,quote,rules)['status']=='filled'
        wallet.mark({'AAA/USDT':quote},{'AAA/USDT':rules})
        if restart:wallet=cls(path,candidate_sha='a'*64,config=cfg,clock=clock)
    return wallet


@pytest.mark.parametrize('restart',[False,True])
def test_equal_clock_fifo_follows_committed_buy_order_not_ids(tmp_path,restart):
    old=same_clock_history(tmp_path/'old.sqlite',PaperWallet).snapshot()
    assert [row['entry_intent'] for row in old['closed_segments'] if row['exit_intent']=='sell-two']==['a-second','z-first']
    wallet=same_clock_history(tmp_path/'new.sqlite',PaperWalletV2,restart=restart)
    state=wallet.snapshot()
    assert [row['entry_intent'] for row in state['closed_segments'] if row['exit_intent']=='sell-two']==['z-first','a-second']
    assert [row['intent_id'] for row in state['fills']]==['z-first','sell-one','a-second','sell-two']
    assert [row['fill_sequence'] for row in state['fills']]==[1,2,3,4]
    assert all(row['producer_version']==VERSION for row in state['fills'])


def worker_fixture(tmp_path,*,cfg=None):
    clock=Clock();wallet=PaperWalletV2(tmp_path/'wallet.sqlite',candidate_sha='a'*64,config=cfg or config(),clock=clock)
    policy={'enabled':True,'status':'frozen','runtime':{'maximum_new_signals_per_tick':2,'wall_budget_seconds':10},
            'exits':{'stop_fraction':'.04','maximum_hold_seconds':3600,'shared_exit_signal':False}}
    worker=PaperWorkerV2(wallet,tmp_path/'worker.sqlite',policy=policy,market=lambda pair:market(clock,pair),clock=clock)
    return clock,wallet,worker


@pytest.mark.parametrize('provider',['normal','fail','cross_cutoff'])
def test_pending_buy_is_cancelled_at_cutoff_even_when_market_fails(tmp_path,provider):
    clock,wallet,worker=worker_fixture(tmp_path);cutoff=START+timedelta(seconds=4)
    tick=lambda rows:worker.tick(rows,window_start=START,window_end=START+timedelta(seconds=20),entry_cutoff=cutoff)
    tick([prediction(clock)])
    assert len(wallet.pending_intents())==1
    clock.advance(3 if provider=='cross_cutoff' else 4)
    def quotes(pair):
        if provider=='fail':raise TimeoutError('not persisted')
        if provider=='cross_cutoff':clock.advance(1)
        return market(clock,pair)
    worker.market=quotes
    report=tick([])
    assert report['status']=='paper_tick_complete'
    assert not wallet.pending_intents() and not wallet.snapshot()['fills']
    with sqlite3.connect(wallet.path) as db:
        assert db.execute('SELECT status,reason FROM intents').fetchone()==('rejected','paper_entry_window_finished')


def test_execution_clock_guard_cancels_buy_but_does_not_block_sell(tmp_path):
    clock,wallet,worker=worker_fixture(tmp_path)
    fill(wallet,clock,'buy','Buy');quote,rules=market(clock)
    wallet.mark({'AAA/USDT':quote},{'AAA/USDT':rules})
    wallet.enqueue('late','BBB/USDT','Buy',created_at=clock.now)
    wallet.enqueue('exit','AAA/USDT','Sell',created_at=clock.now)
    clock.advance();cutoff=clock.now
    assert wallet.execute('late',*market(clock,'BBB/USDT'),entry_cutoff=cutoff)['reason']=='paper_entry_window_finished'
    assert wallet.execute('exit',*market(clock),entry_cutoff=cutoff)['status']=='filled'
    assert not wallet.pending_intents()


def test_closeout_cancels_buy_and_keeps_existing_sell_and_cash_accounting(tmp_path):
    clock,wallet,worker=worker_fixture(tmp_path)
    fill(wallet,clock,'buy','Buy')
    wallet.enqueue('exit','AAA/USDT','Sell',created_at=clock.now)
    wallet.enqueue('late','BBB/USDT','Buy',created_at=clock.now)
    clock.advance();cutoff=clock.now
    report=worker.tick([],window_start=START,window_end=START+timedelta(seconds=20),entry_cutoff=cutoff)
    state=wallet.snapshot()
    assert report['fills_processed']==['filled']
    assert [row['intent_id'] for row in state['fills']]==['buy','exit']
    assert F(state['cash'])==100-F(state['fills'][0]['cost'])+F(state['fills'][1]['proceeds'])
    assert not wallet.pending_intents()


def test_latest_buy_context_uses_causal_sequence_when_clocks_tie(tmp_path,monkeypatch):
    # Deliberately choose IDs whose lexical order disagrees with execution.
    clock,wallet,worker=worker_fixture(tmp_path)
    for identity,side in [('z-first','Buy'),('exit-one','Sell'),('a-second','Buy')]:
        wallet.enqueue(identity,'AAA/USDT',side,created_at=clock.now)
    clock.advance()
    for identity,price in [('z-first','100'),('exit-one','100'),('a-second','101')]:
        q,r=market(clock,price=price)
        # Same-time instrument metadata cannot be changed; only quotes differ.
        wallet.execute(identity,q,r);wallet.mark({'AAA/USDT':q},{'AAA/USDT':r})
    observed=[]
    def exit_rule(**kwargs):observed.append(kwargs);return None
    monkeypatch.setattr('cryptoforge.paper_worker_v2.price_time_exit',exit_rule)
    worker.tick([],window_start=START,window_end=START+timedelta(days=1))
    assert observed[0]['entry_price']==D('101')*(1+config().slippage)


def test_failed_fill_rolls_back_sequence_cash_and_lot_together(tmp_path,monkeypatch):
    clock,wallet,worker=worker_fixture(tmp_path)
    wallet.enqueue('buy','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    with sqlite3.connect(wallet.path) as db:
        db.execute("CREATE TRIGGER fail_fill BEFORE INSERT ON fills BEGIN SELECT RAISE(ABORT,'fixture crash'); END")
    with pytest.raises(sqlite3.IntegrityError,match='fixture crash'):wallet.execute('buy',*market(clock))
    with sqlite3.connect(wallet.path) as db:
        assert db.execute('SELECT count(*) FROM fill_order').fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM lots').fetchone()==(0,)
        db.execute('DROP TRIGGER fail_fill')
    result=wallet.execute('buy',*market(clock))
    assert result['fill']['fill_sequence']==1
    assert wallet.execute('buy',*market(clock))['duplicate']
    assert len(wallet.snapshot()['fills'])==1


@pytest.mark.parametrize('direction',['old_to_new','new_to_old'])
def test_old_and_new_wallets_cannot_adopt_each_others_state(tmp_path,direction):
    classes=(PaperWallet,PaperWalletV2) if direction=='old_to_new' else (PaperWalletV2,PaperWallet)
    path=tmp_path/'wallet.sqlite';classes[0](path,candidate_sha='a'*64,config=config(),clock=Clock())
    before=path.read_bytes()
    with pytest.raises(ValueError):classes[1](path,candidate_sha='a'*64,config=config(),clock=Clock())
    assert path.read_bytes()==before


@pytest.mark.parametrize('mutation',['config','candidate','runtime','stored_policy','sequence','missing_sequence'])
def test_mutated_contract_or_causal_order_fails_closed(tmp_path,monkeypatch,mutation):
    clock,wallet,worker=worker_fixture(tmp_path);fill(wallet,clock,'buy','Buy')
    if mutation=='config':wallet.config=replace(wallet.config,stake=D(7))
    elif mutation=='candidate':wallet.candidate_sha='b'*64
    elif mutation=='runtime':monkeypatch.setattr('cryptoforge.paper_wallet_v2.runtime_hashes',lambda:{'changed':'b'*64})
    else:
        with sqlite3.connect(wallet.path) as db:
            if mutation=='stored_policy':db.execute("UPDATE state SET value='{}' WHERE key='policy'")
            elif mutation=='sequence':db.execute('UPDATE fill_order SET sequence=9')
            else:db.execute('DELETE FROM fill_order')
    before=wallet.path.read_bytes()
    with pytest.raises(ValueError,match='paper v2'):wallet.mark({})
    assert wallet.path.read_bytes()==before


@pytest.mark.parametrize('bad',[D('NaN'),D('Infinity'),D(-1),D(0),D('1e-129'),D('1e129')])
def test_unbounded_or_invalid_sizing_inputs_are_rejected(bad):
    with pytest.raises(ValueError):spot_acquisition(stake=D(6),price=bad,quantity_step=D('.0001'),fee_fraction=D(0),fee_currency='base')


def test_fine_step_sellable_quantity_never_exceeds_inventory():
    amount=D('0.35294117647058823529411764705');step=D('1e-28')
    rounded=floor_quantity(amount,step)
    assert F(rounded)<=F(amount)<F(rounded)+F(step)


def test_worker_version_state_cannot_be_reused_by_frozen_worker(tmp_path):
    clock,wallet,worker=worker_fixture(tmp_path);before=worker.path.read_bytes()
    with pytest.raises(ValueError,match='cannot change'):
        PaperWorker(wallet,worker.path,policy=worker.policy,market=worker.market,clock=clock)
    assert worker.path.read_bytes()==before


@pytest.mark.parametrize('precision',[6,28,80])
def test_fifo_cash_basis_and_pnl_conserve_exactly_without_tolerance(tmp_path,precision):
    clock=Clock();wallet=PaperWalletV2(tmp_path/'wallet.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    for number in range(4):
        with localcontext() as context:
            context.prec=precision;context.traps[Inexact]=True
            assert fill(wallet,clock,f'buy-{number}','Buy')['status']=='filled'
            assert fill(wallet,clock,f'sell-{number}','Sell',price='103')['status']=='filled'
            q,r=market(clock,price='103');wallet.mark({'AAA/USDT':q},{'AAA/USDT':r})
        state=wallet.snapshot()
        residual=sum((F(row['cost']) for row in state['open_lots']),F(0))
        pnl=sum((F(row['net_pnl']) for row in state['closed_segments']),F(0))
        assert F(state['cash'])+residual==100+pnl
        assert all(F(row['cost'])>=0 and F(row['quantity'])>=0 and F(row['entry_fee'])>=0 for row in state['open_lots'])


def registration_args(tmp_path,clock):
    return dict(root=tmp_path/'contract',candidate_sha='a'*64,study_protocol_sha256='b'*64,role='candidate',config=config(),
        worker_policy={'enabled':True,'status':'frozen','runtime':{'maximum_new_signals_per_tick':2,'wall_budget_seconds':10},
                       'exits':{'stop_fraction':'.04','maximum_hold_seconds':3600,'shared_exit_signal':False}},
        backend_env={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_URL':'http://127.0.0.1:54321','CRYPTOFORGE_LOCAL_API_KEY':'fixture-secret-do-not-persist'},
        start=START+timedelta(seconds=10),end=START+timedelta(seconds=40),closeout_seconds=10,clock=clock)


def test_new_contract_freezes_only_local_public_configuration_offline(tmp_path,monkeypatch):
    from cryptoforge.paper_producer_v2 import register_kernel,load_kernel
    clock=Clock();args=registration_args(tmp_path,clock)
    args['worker_policy']['api_key']='must-not-persist-arbitrary-policy-fields'
    receipt=register_kernel(**args)
    assert not receipt['paper_evidence_pass'] and not receipt['live_admission_granted']
    def no_backend(*args):raise AssertionError('sealed contract reading must be offline')
    monkeypatch.setattr('cryptoforge.paper_producer_v2.resolve_backend',no_backend)
    original=load_kernel(args['root'],expected_contract_sha256=receipt['contract_sha256'],expected_registration_sha256=receipt['registration_sha256'])
    assert original['source_backend']=={'name':'local','api_origin':'http://127.0.0.1:54321'}
    assert original['entry_cutoff']==(START+timedelta(seconds=30)).isoformat()
    assert original['full_worker_or_host_qualified'] is False
    assert len(list(args['root'].iterdir()))==2  # No wallet, worker or network activity.
    args['worker_policy']['exits']['stop_fraction']='.9'
    assert D(original['worker_policy']['exits']['stop_fraction'])==D('.04')
    raw=b''.join(p.read_bytes() for p in args['root'].iterdir())
    assert b'fixture-secret' not in raw and b'must-not-persist' not in raw


@pytest.mark.parametrize('bad',['cloud','missing_local_key','late','naive','role','cutoff','bad_sha','disabled','bad_exit','negative_cap','unbounded_decimal','symlink'])
def test_invalid_kernel_registration_never_creates_contract(tmp_path,bad):
    from cryptoforge.paper_producer_v2 import register_kernel
    clock=Clock();args=registration_args(tmp_path,clock)
    if bad=='cloud':args['backend_env']={'SUPABASE_URL':'https://example.invalid','SUPABASE_SERVICE_ROLE_KEY':'fixture'}
    elif bad=='missing_local_key':args['backend_env']={'CRYPTOFORGE_BACKEND':'local','CRYPTOFORGE_LOCAL_API_KEY_FILE':str(tmp_path/'missing-key')}
    elif bad=='late':clock.advance(10)
    elif bad=='naive':args['start']=args['start'].replace(tzinfo=None)
    elif bad=='role':args['role']='production'
    elif bad=='cutoff':args['closeout_seconds']=30
    elif bad=='bad_sha':args['candidate_sha']='a'*63
    elif bad=='disabled':args['worker_policy']['enabled']=False
    elif bad=='bad_exit':args['worker_policy']['exits']['stop_fraction']='NaN'
    elif bad=='negative_cap':args['worker_policy']['runtime']['maximum_new_signals_per_tick']=0
    elif bad=='unbounded_decimal':args['config']=config(capital=D('1e129'))
    else:
        real=tmp_path/'real';real.mkdir();(tmp_path/'linked').symlink_to(real,target_is_directory=True);args['root']=tmp_path/'linked'/'contract'
    with pytest.raises(ValueError):register_kernel(**args)
    assert not args['root'].exists()


@pytest.mark.parametrize('phase',[2,3,4])
def test_registration_overrun_or_clock_rewind_cannot_be_adopted(tmp_path,phase):
    from cryptoforge.paper_producer_v2 import register_kernel,load_kernel
    clock=Clock();args=registration_args(tmp_path,clock);calls=0
    def advancing():
        nonlocal calls
        calls+=1
        return START+timedelta(seconds=10) if calls>=phase else START
    args['clock']=advancing
    with pytest.raises(ValueError,match='missed original start'):register_kernel(**args)
    if args['root'].exists():assert not (args['root']/'registered.json').exists()


@pytest.mark.parametrize('mutation',['runtime','contract_bytes','registration_bytes','missing_completion','linked_contract','admission'])
def test_contract_reader_requires_original_external_pins_and_rejects_admission(tmp_path,monkeypatch,mutation):
    from cryptoforge.paper_producer_v2 import register_kernel,load_kernel
    clock=Clock();args=registration_args(tmp_path,clock);receipt=register_kernel(**args)
    path=args['root']/'kernel-contract.json'
    if mutation=='runtime':monkeypatch.setattr('cryptoforge.paper_producer_v2.runtime_hashes',lambda:{'changed':'c'*64})
    elif mutation=='contract_bytes':path.write_bytes(path.read_bytes()+b' ')
    elif mutation=='registration_bytes':(args['root']/'registered.json').write_bytes(b'{}')
    elif mutation=='missing_completion':(args['root']/'registered.json').unlink()
    elif mutation=='linked_contract':
        import os
        os.link(path,tmp_path/'linked.json')
    else:
        from cryptoforge.paper_producer_v2 import _canonical
        data=json.loads(path.read_bytes());data['paper_evidence_pass']=True;raw=_canonical(data);path.write_bytes(raw)
        receipt['contract_sha256']=hashlib.sha256(raw).hexdigest()
        registered=args['root']/'registered.json';data=json.loads(registered.read_bytes());data['contract_sha256']=receipt['contract_sha256'];raw=_canonical(data);registered.write_bytes(raw)
        receipt['registration_sha256']=hashlib.sha256(raw).hexdigest()
    with pytest.raises(ValueError):load_kernel(args['root'],expected_contract_sha256=receipt['contract_sha256'],expected_registration_sha256=receipt['registration_sha256'])


def test_contract_creation_cannot_overwrite_existing_namespace(tmp_path):
    from cryptoforge.paper_producer_v2 import register_kernel
    clock=Clock();args=registration_args(tmp_path,clock);register_kernel(**args)
    before={p.name:p.read_bytes() for p in args['root'].iterdir()}
    with pytest.raises(FileExistsError):register_kernel(**args)
    assert {p.name:p.read_bytes() for p in args['root'].iterdir()}==before


@pytest.mark.parametrize('kind',['wallet_symlink','wallet_hardlink','worker_symlink','worker_hardlink','wallet_path','worker_path','stored_worker_identity'])
def test_runtime_cannot_redirect_owned_state_or_adopt_modified_worker_identity(tmp_path,kind):
    import os
    clock,wallet,worker=worker_fixture(tmp_path)
    original_wallet=wallet.path;original_worker=worker.path
    if kind.endswith('symlink') or kind.endswith('hardlink'):
        owner=wallet if kind.startswith('wallet') else worker
        linked=tmp_path/'linked.sqlite'
        if kind.endswith('symlink'):linked.symlink_to(owner.path);owner.path=linked
        else:os.link(owner.path,linked)
    elif kind=='wallet_path':wallet.path=tmp_path/'other-wallet.sqlite'
    elif kind=='worker_path':worker.path=tmp_path/'other-worker.sqlite'
    else:
        with sqlite3.connect(worker.path) as db:db.execute("UPDATE worker_state SET value='{}' WHERE key='identity'")
    before=[path.read_bytes() for path in (original_wallet,original_worker)]
    with pytest.raises(ValueError,match='paper'):worker.tick([],window_start=START,window_end=START+timedelta(days=1))
    assert [path.read_bytes() for path in (original_wallet,original_worker)]==before


def test_v2_uses_no_frozen_wallet_or_worker_execution_methods(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('frozen kernel execution must not implement v2')
    for method in ['execute','mark','enqueue']:
        monkeypatch.setattr(PaperWallet,method,forbidden)
    monkeypatch.setattr(PaperWorker,'tick',forbidden)
    clock,wallet,worker=worker_fixture(tmp_path)
    worker.tick([prediction(clock)],window_start=START,window_end=START+timedelta(days=1))
    clock.advance()
    worker.tick([],window_start=START,window_end=START+timedelta(days=1))
    assert wallet.snapshot()['fills'][0]['side']=='Buy'


def test_quote_precision_and_unbounded_initial_capital_fail_before_state_mutation(tmp_path):
    with pytest.raises(ValueError,match='representation'):
        PaperWalletV2(tmp_path/'huge.sqlite',candidate_sha='a'*64,config=config(capital=D('1e129')),clock=Clock())
    assert not (tmp_path/'huge.sqlite').exists()
    clock,wallet,worker=worker_fixture(tmp_path)
    wallet.enqueue('buy','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    q,r=market(clock,price='1e129')
    with pytest.raises(ValueError,match='representation'):wallet.execute('buy',q,r)
    assert not wallet.snapshot()['fills'] and D(wallet.snapshot()['cash'])==100


@pytest.mark.parametrize('state',['wallet','worker'])
def test_missing_runtime_state_is_not_silently_recreated(tmp_path,state):
    clock,wallet,worker=worker_fixture(tmp_path)
    path=wallet.path if state=='wallet' else worker.path
    path.unlink()
    with pytest.raises(ValueError,match='original file path'):
        worker.tick([],window_start=START,window_end=START+timedelta(days=1))
    assert not path.exists()


def test_cutoff_clock_is_observed_after_acquiring_the_sqlite_write_lock(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    clock,wallet,worker=worker_fixture(tmp_path)
    wallet.enqueue('late','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    q,r=market(clock);cutoff=clock.now+timedelta(seconds=1)
    reached_lock=Event()
    class ObservedConnection(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if sql=='BEGIN IMMEDIATE':reached_lock.set()
            return super().execute(sql,*args,**kwargs)
    monkeypatch.setattr(wallet,'_db',lambda:sqlite3.connect(wallet.path,timeout=2,factory=ObservedConnection))
    blocker=sqlite3.connect(wallet.path)
    try:
        blocker.execute('BEGIN IMMEDIATE')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(wallet.execute,'late',q,r,entry_cutoff=cutoff)
            try:
                assert reached_lock.wait(1)
                clock.advance(2)
            finally:blocker.rollback()
            assert future.result(timeout=3)=={'status':'rejected','reason':'paper_entry_window_finished'}
    finally:blocker.close()
    assert wallet.snapshot()['fills']==[] and D(wallet.snapshot()['cash'])==100


@pytest.mark.parametrize('fee',[D('-1'),D('1'),D('NaN'),D('Infinity')])
def test_v2_rejects_invalid_fee_without_inferred_currency_or_clamping(fee):
    from cryptoforge.spot_buy_math_v2 import spot_sale
    with pytest.raises(ValueError):spot_acquisition(stake=D(6),price=D(17),quantity_step=D('.0001'),fee_fraction=fee,fee_currency='base')
    with pytest.raises(ValueError):spot_sale(quantity=D(1),price=D(10),fee_fraction=fee,fee_currency='quote')


@pytest.mark.parametrize('currency',['other',None,'BASE'])
def test_v2_requires_explicit_supported_fee_currency(currency):
    from cryptoforge.spot_buy_math_v2 import spot_sale
    with pytest.raises(ValueError):spot_acquisition(stake=D(6),price=D(17),quantity_step=D('.0001'),fee_fraction=D('.0018'),fee_currency=currency)
    with pytest.raises(ValueError):spot_sale(quantity=D(1),price=D(10),fee_fraction=D('.0018'),fee_currency=currency)
