from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient
from test_submission_risk import setup, BUY


def acknowledged(journal, *, symbol='ETHUSDT', link='old', qty='6'):
    journal.prepare(symbol=symbol, side='Buy', qty=Decimal(qty), order_link_id=link)
    journal.finish(link, 'acknowledged', dict(retCode=0, result=dict(orderId='exchange-'+link)))


def test_ack_survives_restart_and_empty_exchange_history(tmp_path):
    path = tmp_path/'orders.sqlite'; journal = OrderSubmissionJournal(path)
    acknowledged(journal)
    recovered = OrderSubmissionJournal(path)
    assert recovered.reconcile(SimpleNamespace(get_open_orders=lambda **kw: [], get_order_history=lambda **kw: [])) == 0
    assert recovered.buy_reservations() == {'ETHUSDT': Decimal('6')}


def test_current_prepared_order_does_not_reserve_against_itself(tmp_path):
    guard, _, _, sent = setup(tmp_path)
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    guard.submission_journal = journal
    JournaledOrderClient(guard, journal).create_spot_market_order(**BUY)
    assert len(sent) == 1 and journal.buy_reservations() == {'BTCUSDT': Decimal('6')}


def test_stale_remote_wallet_cannot_fund_more_than_local_capacity(tmp_path):
    guard, _, _, sent = setup(tmp_path)
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); guard.submission_journal = journal
    client = JournaledOrderClient(guard, journal)
    client.create_spot_market_order(**BUY)
    client.create_spot_market_order(**dict(BUY, symbol='ETHUSDT', order_link_id='second'))
    with pytest.raises(OrderControlBlocked, match='capacity'):
        client.create_spot_market_order(**dict(BUY, symbol='SOLUSDT', order_link_id='third'))
    assert len(sent) == 2


def test_local_quote_reserve_blocks_insufficient_cash(tmp_path):
    guard, account, _, sent = setup(tmp_path)
    account.usdt_wallet_balance = Decimal('8')
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); acknowledged(journal)
    guard.submission_journal = journal
    with pytest.raises(OrderControlBlocked, match='capacity'): guard.create_spot_market_order(**BUY)
    assert sent == []


@pytest.mark.parametrize('status,qty,value,released', [('Cancelled','0','0',True),
    ('Rejected','0','0',True), ('Filled','1','6',False), ('Cancelled','.1','.6',False),
    ('PartiallyFilledCanceled','0','0',False),
    ('Cancelled','','',False)])
def test_only_positive_zero_fill_terminal_proof_releases_cash(tmp_path, status, qty, value, released):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); acknowledged(journal)
    observation = dict(symbol='ETHUSDT', side='Buy', orderLinkId='old', orderId='exchange-old',
        orderStatus=status, cumExecQty=qty, cumExecValue=value)
    client = SimpleNamespace(get_open_orders=lambda **kw: [], get_order_history=lambda **kw: [observation])
    assert journal.reconcile(client) == 1
    assert (journal.buy_reservations() == {}) is released


def test_same_link_different_exchange_order_cannot_release_reserve(tmp_path):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); acknowledged(journal)
    row = dict(symbol='ETHUSDT', side='Buy', orderLinkId='old', orderId='different',
        orderStatus='Cancelled', cumExecQty='0', cumExecValue='0')
    with pytest.raises(ValueError, match='acknowledged'):
        journal.reconcile(SimpleNamespace(get_open_orders=lambda **kw: [], get_order_history=lambda **kw: [row]))
    assert journal.buy_reservations() == {'ETHUSDT': Decimal('6')}
