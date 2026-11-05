from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
import json
import sqlite3

import pytest
from cryptoforge.decision_outbox import DecisionOutbox
from cryptoforge.order_submission_journal import OrderSubmissionJournal, JournaledOrderClient
from test_order_submission_journal import INTENT, ACK


def original():
    return dict(pair='BTC/USDT', mode='live', decision='approve_exit',
        decided_at='2026-11-02T07:00:00+00:00', reasons=['stop_loss=True'],
        features={'order':{},'original_input_candles':[{'close':'100'}]}, idempotency_key='before-submit')


def test_crash_after_ack_before_record_recovers_original_context_and_never_resubmits(tmp_path):
    path=tmp_path/'orders.sqlite';journal=OrderSubmissionJournal(path);calls=[]
    journal.capture_decision_context(INTENT,original())
    client=JournaledOrderClient(SimpleNamespace(create_spot_market_order=lambda **kw:calls.append(kw) or ACK),journal)
    client.create_spot_market_order(**INTENT)
    # Simulate process death before executor._record. A new object recovers the record.
    journal=OrderSubmissionJournal(path);box=DecisionOutbox(tmp_path/'decisions.sqlite')
    assert journal.recover_decisions(box)==1
    assert journal.recover_decisions(box)==0
    delivered=[]
    assert box.flush(SimpleNamespace(upsert=lambda *a,**kw:delivered.append((a,kw))))==1
    row=delivered[0][0][1][0]
    assert row['reasons']==['stop_loss=True']
    assert row['decided_at']==original()['decided_at']
    assert row['features']['original_input_candles']==original()['features']['original_input_candles']
    assert row['features']['order']['result']['orderId']=='exchange-id'
    assert row['idempotency_key']=='executor:live:BTC/USDT:order:exchange-id'
    assert delivered[0][1]['resolution']=='ignore-duplicates'
    assert len(calls)==1


def test_unknown_submit_recovers_only_after_exact_exchange_observation(tmp_path):
    journal=OrderSubmissionJournal(tmp_path/'orders.sqlite');box=DecisionOutbox(tmp_path/'decisions.sqlite')
    journal.capture_decision_context(INTENT,original());journal.prepare(**INTENT)
    assert journal.recover_decisions(box)==0
    journal.reconcile(SimpleNamespace(get_open_orders=lambda **kw:[],get_order_history=lambda **kw:[]))
    assert journal.recover_decisions(box)==0
    observation=dict(orderLinkId=INTENT['order_link_id'],symbol='BTCUSDT',side='Sell',orderId='found',orderStatus='Filled')
    journal.reconcile(SimpleNamespace(get_open_orders=lambda **kw:[],get_order_history=lambda **kw:[observation]))
    assert journal.recover_decisions(box)==1
    rows=[];box.flush(SimpleNamespace(upsert=lambda table,batch,**kw:rows.extend(batch)))
    assert rows[0]['features']['order_binding_source']=='exact_exchange_observation'
    assert rows[0]['features']['order']['result']['orderId']=='found'


def test_first_context_wins_but_different_intent_and_corruption_are_rejected(tmp_path):
    journal=OrderSubmissionJournal(tmp_path/'orders.sqlite');record=original()
    journal.capture_decision_context(INTENT,record)
    record['reasons']=['different_later_signal'];journal.capture_decision_context(INTENT,record)
    with journal.connect() as db:
        raw=db.execute('SELECT payload FROM order_decision_contexts').fetchone()[0]
    assert json.loads(raw)['record']['reasons']==['stop_loss=True']
    with pytest.raises(ValueError,match='different intent'):
        journal.capture_decision_context(dict(INTENT,qty=Decimal('.02')),record)
    with journal.connect() as db:db.execute("UPDATE order_decision_contexts SET payload='{}'")
    with pytest.raises(ValueError,match='corrupt'):
        journal.capture_decision_context(INTENT,record)


def test_failed_outbox_enqueue_leaves_context_recoverable(tmp_path,monkeypatch):
    journal=OrderSubmissionJournal(tmp_path/'orders.sqlite');box=DecisionOutbox(tmp_path/'decisions.sqlite')
    journal.capture_decision_context(INTENT,original());journal.prepare(**INTENT);journal.finish(INTENT['order_link_id'],'acknowledged',ACK)
    def fail(*a,**kw):raise OSError('disk full')
    with monkeypatch.context() as scoped:
        scoped.setattr(box,'enqueue',fail)
        with pytest.raises(OSError):journal.recover_decisions(box)
    assert journal.recover_decisions(box)==1


def test_pre_submission_executor_capture_exists_before_exchange_and_failure_prevents_send(tmp_path,monkeypatch):
    from test_exit_data_fallback import setup_case
    from cryptoforge.exit_data_fallback import run_with_exit_data_fallback
    executor,public,now,orders=setup_case()
    journal=OrderSubmissionJournal(tmp_path/'orders.sqlite')
    def submit(**intent):
        with journal.connect() as db:
            raw=db.execute('SELECT payload FROM order_decision_contexts').fetchone()[0]
            context=json.loads(raw)
            assert 'stop_loss=True' in context['record']['reasons']
            assert context['record']['features']['original_input_candles']
            assert context['record']['features']['order']=={}
        orders.append(intent);return ACK
    executor.bybit.create_spot_market_order=submit
    executor.bybit=JournaledOrderClient(executor.bybit,journal)
    result=run_with_exit_data_fallback(executor,public,'HYPE/USDT',live=True,now=now)
    assert result.decision=='approve_exit' and len(orders)==1
    def fail(*a,**kw):raise OSError('context disk full')
    monkeypatch.setattr(journal,'capture_decision_context',fail)
    with pytest.raises(OSError):
        run_with_exit_data_fallback(executor,public,'HYPE/USDT',live=True,now=now)
    assert len(orders)==1


def test_crash_after_outbox_enqueue_before_marker_only_duplicates_durable_receipt(tmp_path,monkeypatch):
    journal=OrderSubmissionJournal(tmp_path/'orders.sqlite');box=DecisionOutbox(tmp_path/'decisions.sqlite')
    journal.capture_decision_context(INTENT,original());journal.prepare(**INTENT);journal.finish(INTENT['order_link_id'],'acknowledged',ACK)
    journal.recover_decisions(box)
    # Emulate a crash after enqueue, before the committed marker.
    with journal.connect() as db:db.execute('UPDATE order_decision_contexts SET enqueued=0')
    assert journal.recover_decisions(box)==1
    assert box.pending()==1
