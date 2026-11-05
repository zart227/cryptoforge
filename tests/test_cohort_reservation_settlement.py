from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from cryptoforge.order_submission_journal import OrderSubmissionJournal
from cryptoforge.reservation_settlement import verify_closed_cohort, settle_journal
from test_reservation_settlement import case


def cohort():
    first, sales, wallet, pending = deepcopy(case())
    second = deepcopy(first)
    second[0]['order_link_id'] = 'buy2'
    second[1].update(orderId='B2', orderLinkId='buy2')
    second[2][0].update(orderId='B2', orderLinkId='buy2', execId='exec-B2', execTime='3000')
    second = (*second[:3], 'B2')
    sale1 = sales[0]
    sale1[0]['qty'] = '.5'
    sale1[1].update(cumExecQty='.5', cumExecValue='3')
    sale1[2][0].update(execQty='.5', execValue='3', execFee='.003')
    sale2 = deepcopy(sale1)
    sale2[0].update(qty='1.498', order_link_id='sell2')
    sale2[1].update(orderId='S2', orderLinkId='sell2', cumExecQty='1.498', cumExecValue='8.988')
    sale2[2][0].update(orderId='S2', orderLinkId='sell2', execId='exec-S2', execTime='4000',
        execQty='1.498', execValue='8.988', execFee='.009')
    sale2 = (*sale2[:3], 'S2')
    return [first, second], [sale1, sale2], wallet, pending


def test_interleaved_buy_sell_cohort_uses_only_available_fifo_lots():
    proof = verify_closed_cohort(*cohort())
    assert Decimal(proof['received_base']) == Decimal(proof['consumed_base']) == Decimal('1.998')
    assert [(row['buy_exec_id'], row['sell_exec_id'], Decimal(row['base_quantity']))
        for row in proof['fifo_allocations']] == [
        ('exec-B', 'exec-S', Decimal('.5')), ('exec-B', 'exec-S2', Decimal('.499')),
        ('exec-B2', 'exec-S2', Decimal('.999'))]
    assert not proof['profitability_established']


@pytest.mark.parametrize('problem', ['future_inventory', 'same_time', 'duplicate_exec',
    'duplicate_order', 'leftover', 'nonzero_wallet', 'different_symbol'])
def test_unproven_or_reused_cohort_inventory_retains_reserves(problem):
    buys, sales, wallet, pending = cohort()
    if problem == 'future_inventory': sales[0][2][0]['execTime'] = '999'
    if problem == 'same_time': sales[0][2][0]['execTime'] = '1000'
    if problem == 'duplicate_exec': buys[1][2][0]['execId'] = buys[0][2][0]['execId']
    if problem == 'duplicate_order': buys.append(deepcopy(buys[0]))
    if problem == 'leftover': sales.pop()
    if problem == 'nonzero_wallet': wallet['walletBalance'] = '.001'
    if problem == 'different_symbol': buys[1][0]['symbol'] = 'ETHUSDT'
    with pytest.raises(ValueError): verify_closed_cohort(buys, sales, wallet, pending)


def source_journal(tmp_path):
    buys, sales, wallet, pending = cohort()
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    for entry in [buys[0], sales[0], buys[1], sales[1]]:
        intent, _, _, identity = entry
        journal.prepare(**dict(intent, qty=Decimal(intent['qty'])))
        journal.finish(intent['order_link_id'], 'acknowledged', dict(retCode=0, result=dict(orderId=identity)))
    by_id = {entry[3]: entry for entry in buys+sales}
    def get(endpoint, params):
        if endpoint == '/v5/account/wallet-balance':
            return dict(retCode=0, result=dict(list=[dict(accountType='UNIFIED', coin=[wallet])]))
        if endpoint == '/v5/order/realtime': rows = pending
        else:
            entry = by_id[params['orderId']]
            rows = [entry[1]] if endpoint == '/v5/order/history' else entry[2]
        return dict(retCode=0, result=dict(category='spot', list=deepcopy(rows), nextPageCursor=''))
    return journal, SimpleNamespace(_private_get=get), buys, sales


def test_source_collector_releases_both_buys_atomically_and_restart_does_not_reuse_sales(tmp_path):
    journal, client, _, _ = source_journal(tmp_path)
    assert settle_journal(journal, client) == dict(released_closed=2, retained=0)
    assert OrderSubmissionJournal(journal.path).buy_reservations() == {}
    assert settle_journal(journal, client) == dict(released_closed=0, retained=0)
    with journal.connect() as db:
        proofs = [json.loads(row[0]) for row in db.execute("SELECT response FROM order_submissions WHERE status='released_closed'")]
    assert len(proofs) == 2 and proofs[0] == proofs[1] and len(proofs[0]['original_sources']) == 10


def test_failure_on_second_release_rolls_back_first(tmp_path):
    journal, client, _, _ = source_journal(tmp_path)
    with journal.connect() as db:
        db.execute("CREATE TRIGGER simulate_crash BEFORE UPDATE ON order_submissions "
            "WHEN NEW.link='buy2' AND NEW.status='released_closed' BEGIN SELECT RAISE(ABORT,'simulated failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='simulated failure'):
        settle_journal(journal, client)
    assert journal.buy_reservations() == {'BTCUSDT': Decimal('12')}


def test_execution_proof_cannot_be_used_to_release_another_cohort(tmp_path):
    journal, client, _, _ = source_journal(tmp_path)
    settle_journal(journal, client)
    journal.prepare(symbol='BTCUSDT', side='Buy', qty=Decimal('6'), order_link_id='later')
    journal.finish('later', 'acknowledged', dict(retCode=0, result=dict(orderId='later-id')))
    with journal.connect() as db:
        proof = json.loads(db.execute("SELECT response FROM order_submissions WHERE link='buy'").fetchone()[0])
        raw = db.execute("SELECT payload FROM order_submissions WHERE link='later'").fetchone()[0]
    proof['buy_links'] = ['later']
    with pytest.raises(ValueError, match='already consumed'):
        journal.release_closed_cohort({'later': hashlib.sha256(raw.encode()).hexdigest()}, proof)
    assert journal.buy_reservations() == {'BTCUSDT': Decimal('6')}
