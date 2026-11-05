from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptoforge.spot_reservations import spot_reservations
from cryptoforge.execution_controls import OrderControlBlocked
from test_submission_risk import setup, BUY


def wallet():
    return dict(coin='USDT', usdValue='20', walletBalance='20', locked='0', bonus='0',
        borrowAmount='0', spotBorrow='0', totalOrderIM='0', totalPositionIM='0')


def page(rows=(), cursor=''):
    return dict(retCode=0, result=dict(category='spot', list=list(rows), nextPageCursor=cursor))


def order(symbol, identity):
    return dict(symbol=symbol, side='Buy', orderId=identity)


def test_complete_pagination_and_locked_cash_without_double_subtraction():
    coin = wallet(); coin.update(locked='8', bonus='1')
    pages = [page([order('BTCUSDT','1')], 'next'), page([order('ETHUSDT','2')])]
    calls = []
    def get(path, params):
        calls.append((path, params)); return pages.pop(0)
    free, pending = spot_reservations(SimpleNamespace(_private_get=get), [coin])
    assert free == Decimal('11') and pending == {'BTCUSDT', 'ETHUSDT'}
    assert calls[0][1] == dict(category='spot', openOnly='0', limit='50')
    assert calls[1][1]['cursor'] == 'next'


@pytest.mark.parametrize('field,value', [('locked','NaN'), ('locked','21'), ('spotBorrow','1'),
    ('borrowAmount','1'), ('totalOrderIM','1'), ('totalPositionIM',''), ('bonus','Infinity')])
def test_unqualified_cash_is_unknown_not_full_wallet(field, value):
    coin = wallet(); coin[field] = value
    with pytest.raises((ValueError, ArithmeticError)):
        spot_reservations(SimpleNamespace(_private_get=lambda *a: pytest.fail('premature query')), [coin])


def test_missing_locked_field_rejected():
    coin = wallet(); del coin['locked']
    with pytest.raises(KeyError): spot_reservations(SimpleNamespace(), [coin])


@pytest.mark.parametrize('failure', ['loop', 'truncated', 'duplicate', 'missing_cursor', 'api_error'])
def test_incomplete_or_inconsistent_orders_never_prove_free_capacity(failure):
    rows = [order('BTCUSDT', 'same')]
    response = page(rows, 'again')
    if failure == 'duplicate': response = page(rows+rows)
    if failure == 'missing_cursor': del response['result']['nextPageCursor']
    if failure == 'api_error': response['retCode'] = 10001
    with pytest.raises((ValueError, KeyError)):
        spot_reservations(SimpleNamespace(_private_get=lambda *a: response), [wallet()],
            maximum_pages=1 if failure == 'truncated' else 3)


@pytest.mark.parametrize('case', ['reserved_cash', 'pending_capacity', 'same_symbol', 'api_outage'])
def test_submission_guard_blocks_unavailable_cash_or_pending_buys(tmp_path, case):
    guard, account, coins, sent = setup(tmp_path)
    coins[:] = [wallet()]; guard.reservation_guard = True
    rows = []
    if case == 'reserved_cash': coins[0]['locked'] = '15'
    if case == 'pending_capacity': rows = [order('ETHUSDT','1'), order('SOLUSDT','2')]
    if case == 'same_symbol': rows = [order('BTCUSDT','1')]
    def get(*args):
        if case == 'api_outage': raise OSError('offline')
        return page(rows)
    guard.client._private_get = get
    with pytest.raises(OrderControlBlocked): guard.create_spot_market_order(**BUY)
    assert sent == []


def test_existing_position_and_pending_same_symbol_count_once(tmp_path):
    guard, account, coins, sent = setup(tmp_path)
    coins[:] = [wallet(), dict(coin='ETH', usdValue='6')]
    guard.reservation_guard = True
    guard.client._private_get = lambda *a: page([order('ETHUSDT','1')])
    guard.create_spot_market_order(**BUY)
    assert len(sent) == 1


def test_sell_does_not_need_reservation_data(tmp_path):
    guard, _, _, sent = setup(tmp_path); guard.reservation_guard = True
    guard.client._private_get = lambda *a: pytest.fail('sell depends on cash query')
    guard.create_spot_market_order(**dict(BUY, side='Sell', qty=Decimal('.01')))
    assert sent[0]['side'] == 'Sell'
