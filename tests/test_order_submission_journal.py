from decimal import Decimal
from types import SimpleNamespace
import sqlite3

import pytest
from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient


INTENT = dict(symbol='BTCUSDT', side='Sell', qty=Decimal('0.01'), order_link_id='original-link')
ACK = {'retCode': 0, 'result': {'orderId': 'exchange-id'}}


def test_intent_committed_before_send_and_restart_never_resubmits(tmp_path):
    path = tmp_path/'orders.sqlite'; journal = OrderSubmissionJournal(path); calls = []
    def submit(**intent):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'prepared'
        calls.append(intent)
        raise TimeoutError('unknown exchange outcome')
    client = SimpleNamespace(create_spot_market_order=submit)
    with pytest.raises(TimeoutError):
        JournaledOrderClient(client, journal).create_spot_market_order(**INTENT)
    recovered = JournaledOrderClient(client, OrderSubmissionJournal(path))
    with pytest.raises(ValueError, match='reconcile'):
        recovered.create_spot_market_order(**INTENT)
    with pytest.raises(ValueError, match='unresolved'):
        recovered.create_spot_market_order(**dict(INTENT, order_link_id='another'))
    assert len(calls) == 1


def test_ack_response_recovered_without_second_submit(tmp_path):
    calls = []; journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    client = JournaledOrderClient(SimpleNamespace(create_spot_market_order=lambda **kw: calls.append(kw) or ACK), journal)
    assert client.create_spot_market_order(**INTENT) == ACK
    assert client.create_spot_market_order(**INTENT) == ACK
    assert len(calls) == 1
    with pytest.raises(ValueError, match='different intent'):
        client.create_spot_market_order(**dict(INTENT, qty=Decimal('.02')))


def test_local_prepare_failure_never_reaches_exchange(tmp_path, monkeypatch):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    def fail(**kw):
        raise OSError('disk full')
    monkeypatch.setattr(journal, 'prepare', fail)
    client = JournaledOrderClient(SimpleNamespace(create_spot_market_order=lambda **kw: pytest.fail('sent')), journal)
    with pytest.raises(OSError): client.create_spot_market_order(**INTENT)


def test_crash_after_submit_before_ack_write_cannot_retry(tmp_path, monkeypatch):
    path = tmp_path/'orders.sqlite'; journal = OrderSubmissionJournal(path); calls = []
    def fail(*args, **kw): raise OSError('simulated crash')
    monkeypatch.setattr(journal, 'finish', fail)
    client = JournaledOrderClient(SimpleNamespace(create_spot_market_order=lambda **kw: calls.append(kw) or ACK), journal)
    with pytest.raises(OSError): client.create_spot_market_order(**INTENT)
    with pytest.raises(ValueError, match='reconcile'):
        JournaledOrderClient(client.client, OrderSubmissionJournal(path)).create_spot_market_order(**INTENT)
    assert len(calls) == 1


def test_absence_is_unknown_positive_matching_observation_resolves_without_resend(tmp_path):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); journal.prepare(**INTENT)
    client = SimpleNamespace(get_open_orders=lambda **kw: [], get_order_history=lambda **kw: [])
    assert journal.reconcile(client) == 0
    with pytest.raises(ValueError, match='unresolved'):
        journal.prepare(**dict(INTENT, order_link_id='new-link'))
    client.get_order_history = lambda **kw: [dict(orderLinkId='original-link', symbol='BTCUSDT',
        side='Sell', orderId='exchange-id', orderStatus='Filled')]
    assert journal.reconcile(client) == 1
    with pytest.raises(ValueError, match='reconcile'): journal.prepare(**INTENT)
    assert journal.prepare(**dict(INTENT, order_link_id='new-link')) is None


def test_conflicting_observation_remains_blocked(tmp_path):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); journal.prepare(**INTENT)
    wrong = dict(orderLinkId='original-link', symbol='BTCUSDT', side='Buy', orderId='other')
    with pytest.raises(ValueError, match='conflicting'):
        journal.reconcile(SimpleNamespace(get_open_orders=lambda **kw: [wrong], get_order_history=lambda **kw: []))
    with pytest.raises(ValueError, match='unresolved'):
        journal.prepare(**dict(INTENT, order_link_id='new-link'))


def test_uncertain_market_does_not_block_other_market_sell_but_blocks_buys(tmp_path):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite'); journal.prepare(**INTENT)
    with pytest.raises(ValueError, match='unresolved'):
        journal.prepare(**dict(INTENT, symbol='ETHUSDT', side='Buy', order_link_id='buy'))
    assert journal.prepare(**dict(INTENT, symbol='ETHUSDT', order_link_id='exit')) is None


def test_executor_exit_with_both_journals_survives_remote_record_outage(tmp_path):
    from test_exit_data_fallback import setup_case
    from cryptoforge.decision_outbox import DecisionOutbox, DurableDecisionClient
    from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
    executor, public, now, orders = setup_case()
    def submit(**intent):
        orders.append(intent)
        return ACK
    executor.bybit.create_spot_market_order = submit
    executor.bybit = JournaledOrderClient(executor.bybit, OrderSubmissionJournal(tmp_path/'orders.sqlite'))
    outbox = DecisionOutbox(tmp_path/'decisions.sqlite')
    def offline(*args, **kwargs): raise OSError('remote unavailable')
    executor.supabase = DurableDecisionClient(SimpleNamespace(upsert=offline), outbox)
    del executor._record
    result = run_with_exit_data_fallback(executor, public, 'HYPE/USDT', live=True, now=now)
    assert result.decision == 'approve_exit' and result.order == ACK
    assert len(orders) == 1 and outbox.pending() == 1
    with sqlite3.connect(tmp_path/'orders.sqlite') as db:
        assert db.execute('SELECT status FROM order_submissions').fetchone()[0] == 'acknowledged'


@pytest.mark.parametrize('response', [None, {}, {'retCode': 1, 'result': {'orderId': 'x'}},
    {'retCode': 0, 'result': {'orderId': 'x', 'orderLinkId': 'wrong-link'}}])
def test_unqualified_response_never_allows_resend(tmp_path, response):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    client = JournaledOrderClient(SimpleNamespace(create_spot_market_order=lambda **kw: response), journal)
    with pytest.raises(ValueError, match='acknowledgment'): client.create_spot_market_order(**INTENT)
    with pytest.raises(ValueError, match='reconcile'): client.create_spot_market_order(**INTENT)
