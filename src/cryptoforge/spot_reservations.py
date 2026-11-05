"""Conservative non-borrowed USDT cash and complete open-order observation."""
from decimal import Decimal


def amount(row, key):
    value = Decimal(str(row[key]))
    if not value.is_finite() or value < 0:
        raise ValueError('invalid spot reservation amount')
    return value


def spot_reservations(client, coins, *, maximum_pages=20):
    usdt = [row for row in coins if row.get('coin') == 'USDT']
    if len(usdt) != 1:
        raise ValueError('one original USDT wallet row required')
    wallet = usdt[0]
    balance, locked, bonus = (amount(wallet, key) for key in ('walletBalance', 'locked', 'bonus'))
    # Margin/borrowed buying power is outside this Spot cash contract.
    if any(amount(wallet, key) != 0 for key in ('borrowAmount', 'spotBorrow', 'totalOrderIM', 'totalPositionIM')):
        raise ValueError('borrowed or margin-reserved balance is unqualified')
    available = balance - locked - bonus
    if available < 0:
        raise ValueError('inconsistent reserved balance')
    cursor = ''; seen_cursors = set(); seen_orders = set(); pending = set()
    for _ in range(maximum_pages):
        params = dict(category='spot', openOnly='0', limit='50')
        if cursor:
            params['cursor'] = cursor
        response = client._private_get('/v5/order/realtime', params)
        if response.get('retCode') != 0:
            raise ValueError('open order query failed')
        result = response['result']
        if result.get('category') != 'spot' or not isinstance(result.get('list'), list):
            raise ValueError('invalid open order page')
        for row in result['list']:
            identity, symbol, side = row['orderId'], row['symbol'], row['side']
            if (not identity or identity in seen_orders or not isinstance(symbol, str) or not symbol
                    or side not in {'Buy', 'Sell'}):
                raise ValueError('inconsistent open orders')
            seen_orders.add(identity)
            if side == 'Buy':
                pending.add(symbol)
        cursor = result['nextPageCursor']
        if not isinstance(cursor, str):
            raise ValueError('unknown open order pagination')
        if not cursor:
            return available, pending
        if cursor in seen_cursors:
            raise ValueError('repeated open order cursor')
        seen_cursors.add(cursor)
    raise ValueError('incomplete open order pagination')
