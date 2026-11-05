from copy import deepcopy
from decimal import Decimal

import pytest
from cryptoforge.reservation_settlement import verify_closed_cycle, settle_journal
from test_reservation_settlement import case, journal_case


def partial_buy_case():
    buy, sales, wallet, pending = deepcopy(case())
    buy[1].update(orderStatus='PartiallyFilledCanceled', cumExecQty='.5', cumExecValue='3', leavesQty='.5')
    buy[2][0].update(execQty='.5', execValue='3', execFee='.0005')
    sales[0][0]['qty'] = '.4995'
    sales[0][1].update(cumExecQty='.4995', cumExecValue='2.997')
    sales[0][2][0].update(execQty='.4995', execValue='2.997', execFee='.003')
    return buy, sales, wallet, pending


def test_terminal_partial_buy_releases_only_after_its_received_base_is_closed():
    proof = verify_closed_cycle(*partial_buy_case())
    assert Decimal(proof['received_base']) == Decimal('.4995')
    assert proof['terminal_order_statuses']['B'] == 'PartiallyFilledCanceled'
    assert proof['schema_version'] == 'closed-reservation-proof-v2'


def test_cancelled_partial_sale_plus_remainder_sale_close_exact_inventory():
    buy, sales, wallet, pending = deepcopy(case())
    first = sales[0]
    first[0]['qty'] = '.999'
    first[1].update(orderStatus='PartiallyFilledCanceled', leavesQty='.499', cumExecQty='.5', cumExecValue='3')
    first[2][0].update(execQty='.5', execValue='3', execFee='.003')
    second = deepcopy(first)
    second[0].update(qty='.499', order_link_id='remainder')
    second[1].update(orderId='S2', orderLinkId='remainder', orderStatus='Filled', leavesQty='0',
        cumExecQty='.499', cumExecValue='2.994')
    second[2][0].update(orderId='S2', orderLinkId='remainder', execId='exec-S2', execTime='3000',
        execQty='.499', execValue='2.994', execFee='.003')
    second = (*second[:3], 'S2')
    proof = verify_closed_cycle(buy, [first, second], wallet, pending)
    assert Decimal(proof['consumed_base']) == Decimal('.999')


@pytest.mark.parametrize('problem', ['open_partial', 'unknown_status', 'zero_execution',
    'over_request', 'bad_sell_leaves', 'missing_fill', 'remaining_inventory'])
def test_partial_or_unknown_remainder_never_releases(problem):
    buy, sales, wallet, pending = partial_buy_case()
    if problem == 'open_partial': buy[1]['orderStatus'] = 'PartiallyFilled'
    if problem == 'unknown_status': buy[1]['orderStatus'] = 'Cancelled'
    if problem == 'zero_execution': buy[1]['cumExecQty'] = '0'
    if problem == 'over_request': buy[0]['qty'] = '2'
    if problem == 'bad_sell_leaves':
        sales[0][0]['qty'] = '1'
        sales[0][1].update(orderStatus='PartiallyFilledCanceled', leavesQty='1')
    if problem == 'missing_fill': buy[2].clear()
    if problem == 'remaining_inventory': wallet['walletBalance'] = '.0001'
    with pytest.raises(ValueError): verify_closed_cycle(buy, sales, wallet, pending)


def test_terminal_partial_fill_source_collector_retains_original_proof(tmp_path):
    journal, client, _, _ = journal_case(tmp_path)
    buy, sales, _, _ = partial_buy_case()
    # Original journal quote amount is6; sale originally requested.999,
    # executed.4995 then cancelled: preserve the original intent unchanged.
    sales[0][1].update(orderStatus='PartiallyFilledCanceled', leavesQty='.4995')
    get = client._private_get
    def partial(endpoint, params):
        response = get(endpoint, params)
        if endpoint in {'/v5/order/history', '/v5/execution/list'}:
            entry = buy if params['orderId'] == 'B' else sales[0]
            response['result']['list'] = [deepcopy(entry[1])] if endpoint == '/v5/order/history' else deepcopy(entry[2])
        return response
    client._private_get = partial
    assert settle_journal(journal, client) == dict(released_closed=1, retained=0)
    assert journal.buy_reservations() == {}
