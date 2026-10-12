from dataclasses import replace
from datetime import UTC,datetime,timedelta
from decimal import Decimal as D
import pytest

from cryptoforge.paper_wallet import PaperWallet,PaperConfig

START=datetime(2026,10,8,10,tzinfo=UTC)


class Clock:
    def __init__(self):self.now=START
    def __call__(self):return self.now
    def advance(self,seconds=2):self.now+=timedelta(seconds=seconds)


def config(**changes):
    base=PaperConfig(capital=D('100'),stake=D('6'),entry_fee=D('.0018'),exit_fee=D('.0018'),
                     slippage=D('.0005'),cost_assumption_id='unit_scenario_not_account_fee_proof')
    return replace(base,**changes)


def market(clock,pair='AAA/USDT',price='100',step='.0001',depth='1000'):
    quote={'pair':pair,'market':'spot','venue':'bybit_global','bid':price,'ask':price,
           'bid_qty':depth,'ask_qty':depth,'observed_at':clock.now.isoformat()}
    filters={'pair':pair,'market':'spot','venue':'bybit_global','status':'Trading','quantity_step':step,
             'minimum_notional':'5','maximum_market_quantity':'10000','observed_at':clock.now.isoformat()}
    return quote,filters


def fill(wallet,clock,identity,side,pair='AAA/USDT',**kwargs):
    wallet.enqueue(identity,pair,side,created_at=clock.now);clock.advance()
    quote,filters=market(clock,pair,**kwargs)
    return wallet.execute(identity,quote,filters)


def test_signal_needs_later_quote_and_cannot_fill_a_pre_enqueue_price(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    wallet.enqueue('b1','AAA/USDT','Buy',created_at=clock.now-timedelta(seconds=4))
    quote,filters=market(clock)
    assert wallet.execute('b1',quote,filters)['status']=='pending'
    clock.advance();quote,filters=market(clock)
    assert wallet.execute('b1',quote,filters)['status']=='filled'


def test_quote_cash_and_base_fee_are_charged_once(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(slippage=D(0)),clock=clock)
    result=fill(wallet,clock,'b1','Buy');trade=result['fill']
    assert D(trade['cost'])==D(6) and D(wallet.snapshot()['cash'])==D(94)
    assert D(trade['order_quantity'])==D('.06') and D(trade['quantity'])==D('.059892')
    assert trade['fee_currency']=='base' and D(trade['fee_amount'])==D('.000108')
    wallet.mark({'AAA/USDT':market(clock)[0]})
    sold=fill(wallet,clock,'s1','Sell')['fill']
    assert sold['fee_currency']=='quote'
    assert D(wallet.snapshot()['cash'])==D(94)+D(sold['proceeds'])
    assert wallet.snapshot()['open_lots']  # residual inventory is not erased


def test_one_cash_wallet_prevents_reusing_capital_for_two_pairs(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(capital=D(6)),clock=clock)
    assert fill(wallet,clock,'b1','Buy')['status']=='filled'
    quote,filters=market(clock);wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    assert fill(wallet,clock,'b2','Buy',pair='BBB/USDT')['reason']=='insufficient_shared_cash'


def test_duplicate_fill_does_not_spend_twice_and_restart_preserves_state(tmp_path):
    clock=Clock();path=tmp_path/'paper.sqlite';wallet=PaperWallet(path,candidate_sha='a'*64,config=config(),clock=clock)
    fill(wallet,clock,'b1','Buy');before=wallet.snapshot()
    quote,filters=market(clock);assert wallet.execute('b1',quote,filters)['duplicate']
    restored=PaperWallet(path,candidate_sha='a'*64,config=config(),clock=clock)
    assert restored.snapshot()==before
    with pytest.raises(ValueError,match='cannot change'):
        PaperWallet(path,candidate_sha='a'*64,config=config(capital=D(200)),clock=clock)


@pytest.mark.parametrize('error',['stale','future','crossed','wrong_market','zero_depth'])
def test_invalid_quotes_never_debit_paper_cash(tmp_path,error):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    wallet.enqueue('b1','AAA/USDT','Buy',created_at=clock.now);clock.advance()
    quote,filters=market(clock)
    if error=='stale':clock.advance(15)
    elif error=='future':quote['observed_at']=(clock.now+timedelta(seconds=1)).isoformat()
    elif error=='crossed':quote['ask']='99'
    elif error=='wrong_market':filters['market']='linear'
    else:quote['bid_qty']='0'
    with pytest.raises(ValueError):wallet.execute('b1',quote,filters)
    assert D(wallet.snapshot()['cash'])==100 and not wallet.snapshot()['fills']


def test_expired_signals_are_rejected_instead_of_backfilled(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    wallet.enqueue('b1','AAA/USDT','Buy',created_at=clock.now);clock.advance(31)
    assert wallet.execute('b1',*market(clock))['reason']=='expired_signal'
    with pytest.raises(ValueError,match='backdated'):
        wallet.enqueue('late','AAA/USDT','Buy',created_at=START)


def test_unknown_liquidation_and_daily_loss_block_new_entries(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(max_daily_loss=D('.1')),clock=clock)
    fill(wallet,clock,'b1','Buy')
    assert wallet.mark({})['equity'] is None
    assert fill(wallet,clock,'b2','Buy',pair='BBB/USDT')['reason']=='daily_equity_guard_or_missing_fresh_mark'
    quote,filters=market(clock,price='90');mark=wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    assert D(mark['equity'])<D('99.9')
    assert fill(wallet,clock,'b3','Buy',pair='BBB/USDT')['reason']=='daily_equity_guard_or_missing_fresh_mark'


def test_nontradable_small_residual_releases_slot_but_is_not_deleted(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(max_positions=1),clock=clock)
    fill(wallet,clock,'b1','Buy');fill(wallet,clock,'s1','Sell')
    quote,filters=market(clock);mark=wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    assert mark['nontradable_small_basis_pairs']==['AAA/USDT']
    assert wallet.snapshot()['open_lots']
    assert fill(wallet,clock,'b2','Buy',pair='BBB/USDT')['status']=='filled'


def test_precision_exit_minimum_and_depth_limits_are_not_ideal_fills(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    assert fill(wallet,clock,'b1','Buy',step='.01')['reason']=='exit_minimum_or_residual_precision_risk'
    assert fill(wallet,clock,'b2','Buy',depth='.001')['reason']=='size_or_displayed_liquidity_limit'


def test_missing_filters_cannot_turn_gross_mark_into_liquidation_profit(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    fill(wallet,clock,'b1','Buy');clock.advance(301)
    mark=wallet.mark({'AAA/USDT':market(clock,price='150')[0]})
    assert D(mark['gross_bid_equity'])>100 and mark['equity'] is None
    assert mark['uncertain_liquidation_pairs']==['AAA/USDT']


def test_real_or_training_database_cannot_be_reused_as_paper_wallet(tmp_path):
    import sqlite3
    path=tmp_path/'real.sqlite';db=sqlite3.connect(path)
    db.execute('CREATE TABLE executions (id TEXT PRIMARY KEY)');db.commit();db.close()
    with pytest.raises(ValueError,match='unrelated database'):
        PaperWallet(path,candidate_sha='a'*64,config=config(),clock=Clock())
    db=sqlite3.connect(path)
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[('executions',)]
    db.close()


def test_instrument_rules_cannot_be_rewound_after_a_newer_observation(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    fill(wallet,clock,'b1','Buy');quote,filters=market(clock);wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    old=dict(filters);old['observed_at']=(clock.now-timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError,match='rewound'):
        wallet.mark({'AAA/USDT':quote},{'AAA/USDT':old})


def test_overnight_gap_without_an_intermediate_mark_does_not_reset_loss_budget(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    fill(wallet,clock,'b1','Buy');clock.advance(86400)
    quote,filters=market(clock,price='50');mark=wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    assert D(mark['equity'])<D(98)
    result=fill(wallet,clock,'b2','Buy',pair='BBB/USDT')
    assert result['reason']=='daily_equity_guard_or_missing_fresh_mark'


def test_fifo_repeated_buy_can_consume_old_dust_without_hiding_its_basis(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    fill(wallet,clock,'b1','Buy');fill(wallet,clock,'s1','Sell')
    quote,filters=market(clock);wallet.mark({'AAA/USDT':quote},{'AAA/USDT':filters})
    assert fill(wallet,clock,'b2','Buy')['status']=='filled'
    assert fill(wallet,clock,'s2','Sell')['status']=='filled'
    segments=wallet.snapshot()['closed_segments']
    second_exit=[r for r in segments if r['exit_intent']=='s2']
    assert [r['entry_intent'] for r in second_exit]==['b1','b2']
    assert all(D(r['cost'])>0 for r in second_exit)


def test_cash_plus_remaining_basis_reconciles_to_realized_paper_pnl(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    fill(wallet,clock,'b1','Buy');fill(wallet,clock,'s1','Sell',price='103')
    state=wallet.snapshot();basis=sum((D(row['cost']) for row in state['open_lots']),D(0))
    pnl=sum((D(row['net_pnl']) for row in state['closed_segments']),D(0))
    assert abs(D(state['cash'])+basis-D(100)-pnl)<D('1e-24')
    assert all(row['mode']=='paper' for row in state['fills']+state['closed_segments'])


def test_sell_without_owned_inventory_cannot_create_short_exposure(tmp_path):
    clock=Clock();wallet=PaperWallet(tmp_path/'paper.sqlite',candidate_sha='a'*64,config=config(),clock=clock)
    assert fill(wallet,clock,'s1','Sell')['reason']=='unsellable_inventory_preserved'
    assert D(wallet.snapshot()['cash'])==100 and not wallet.snapshot()['open_lots']
