from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptoforge.order_submission_journal import OrderSubmissionJournal
from cryptoforge.reservation_settlement import verify_closed_cycle, settle_journal


def case():
    buy_intent = dict(symbol='BTCUSDT', side='Buy', qty='6', order_link_id='buy')
    sell_intent = dict(symbol='BTCUSDT', side='Sell', qty='.999', order_link_id='sell')
    def source(intent, identity, qty, value, stamp, fee, currency):
        order = dict(orderId=identity, orderLinkId=intent['order_link_id'], symbol='BTCUSDT', side=intent['side'],
            orderStatus='Filled', leavesQty='0', cumExecQty=qty, cumExecValue=value)
        fill = dict(orderId=identity, orderLinkId=intent['order_link_id'], symbol='BTCUSDT', side=intent['side'],
            execType='Trade', execId='exec-'+identity, execQty=qty, execPrice='6', execValue=value,
            execFee=fee, feeCurrency=currency, execTime=str(stamp), extraFees='')
        return intent, order, [fill], identity
    buy = source(buy_intent, 'B', '1', '6', 1000, '.001', 'BTC')
    sell = source(sell_intent, 'S', '.999', '5.994', 2000, '.006', 'USDT')
    wallet = dict(coin='BTC', walletBalance='0', locked='0', borrowAmount='0', spotBorrow='0')
    return buy, [sell], wallet, []


def test_exact_base_fee_quantity_conservation_proves_closed_reservation():
    proof = verify_closed_cycle(*case())
    assert proof['received_base'] == proof['consumed_base'] == '0.999'
    assert proof['reservation_release_verified'] and not proof['profitability_established']


def test_multiple_buy_fills_and_base_sell_fee_conserve_inventory():
    buy, sales, wallet, pending = deepcopy(case())
    original = buy[2].pop()
    for index in range(2):
        fill = deepcopy(original)
        fill.update(execId='buy-'+str(index), execQty='.5', execValue='3', execFee='.0005')
        buy[2].append(fill)
    sales[0][0]['qty'] = '.998'
    sales[0][1].update(cumExecQty='.998', cumExecValue='5.988')
    sales[0][2][0].update(execQty='.998', execValue='5.988', execFee='.001', feeCurrency='BTC')
    proof = verify_closed_cycle(buy, sales, wallet, pending)
    assert Decimal(proof['received_base']) == Decimal(proof['consumed_base']) == Decimal('.999')


@pytest.mark.parametrize('problem', ['gap', 'partial', 'third_fee', 'extra_fee', 'duplicate',
    'before_buy', 'remaining_wallet', 'pending', 'wrong_id', 'wrong_link', 'wrong_market', 'nonfinite', 'overquote'])
def test_incomplete_or_conflicting_proof_never_releases(problem):
    buy, sales, wallet, pending = deepcopy(case())
    if problem == 'gap': buy[1]['cumExecQty'] = '2'
    if problem == 'partial': sales[0][1]['orderStatus'] = 'PartiallyFilled'
    if problem == 'third_fee': buy[2][0]['feeCurrency'] = 'BNB'
    if problem == 'extra_fee': buy[2][0]['extraFees'] = 'unknown'
    if problem == 'duplicate': sales[0][2].append(deepcopy(sales[0][2][0]))
    if problem == 'before_buy': sales[0][2][0]['execTime'] = '999'
    if problem == 'remaining_wallet': wallet['walletBalance'] = '.00001'
    if problem == 'pending': pending.append(dict(orderId='pending'))
    if problem == 'wrong_id': sales[0][2][0]['orderId'] = 'other'
    if problem == 'wrong_link': buy[2][0]['orderLinkId'] = 'other'
    if problem == 'wrong_market': wallet['coin'] = 'ETH'
    if problem == 'nonfinite': buy[2][0]['execFee'] = 'NaN'
    if problem == 'overquote': buy[0]['qty'] = '5'
    with pytest.raises(ValueError): verify_closed_cycle(buy, sales, wallet, pending)


def journal_case(tmp_path):
    journal = OrderSubmissionJournal(tmp_path/'orders.sqlite')
    buy, sales, wallet, pending = case()
    for intent, _, _, identity in [buy, *sales]:
        journal.prepare(**dict(intent, qty=Decimal(intent['qty'])))
        journal.finish(intent['order_link_id'], 'acknowledged', dict(retCode=0, result=dict(orderId=identity)))
    calls = []
    def get(endpoint, params):
        calls.append((endpoint, deepcopy(params)))
        if endpoint == '/v5/account/wallet-balance':
            return dict(retCode=0, result=dict(list=[dict(accountType='UNIFIED', coin=[deepcopy(wallet)])]))
        if endpoint == '/v5/order/realtime': rows = deepcopy(pending)
        else:
            entry = buy if params['orderId'] == 'B' else sales[0]
            rows = [deepcopy(entry[1])] if endpoint == '/v5/order/history' else deepcopy(entry[2])
        return dict(retCode=0, result=dict(category='spot', list=rows, nextPageCursor=''))
    return journal, SimpleNamespace(_private_get=get), calls, wallet


def test_authenticated_source_collection_release_is_durable_and_keeps_receipts(tmp_path):
    journal, client, calls, _ = journal_case(tmp_path)
    assert settle_journal(journal, client) == dict(released_closed=1, retained=0)
    assert OrderSubmissionJournal(journal.path).buy_reservations() == {}
    assert len(calls) == 6
    with journal.connect() as db:
        import json
        status, raw = db.execute("SELECT status,response FROM order_submissions WHERE link='buy'").fetchone()
        receipt = json.loads(raw)
    assert status == 'released_closed' and len(receipt['original_sources']) == 6
    assert len(receipt['source_sha256']) == 64
    assert settle_journal(journal, client)['released_closed'] == 0
    with pytest.raises(ValueError, match='reconcile'):
        journal.prepare(symbol='BTCUSDT', side='Buy', qty=Decimal('6'), order_link_id='buy')


def test_unknown_or_nonzero_wallet_retains_full_reserve(tmp_path):
    journal, client, _, wallet = journal_case(tmp_path)
    wallet['walletBalance'] = '.01'
    assert settle_journal(journal, client) == dict(released_closed=0, retained=1)
    assert journal.buy_reservations() == {'BTCUSDT': Decimal('6')}


def test_missing_execution_history_cannot_prove_closeout(tmp_path):
    journal, client, _, _ = journal_case(tmp_path)
    get = client._private_get
    def missing(endpoint, params):
        response = get(endpoint, params)
        if endpoint == '/v5/execution/list': response['result']['list'] = []
        return response
    client._private_get = missing
    assert settle_journal(journal, client)['released_closed'] == 0
    assert journal.buy_reservations()
