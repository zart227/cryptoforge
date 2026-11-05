"""Narrow reservation release proof for a completely closed local Spot cycle."""
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from collections import deque


def number(row, key, *, positive=False):
    value = Decimal(str(row[key]))
    if not value.is_finite() or value < 0 or (positive and value == 0):
        raise ValueError('unqualified settlement amount')
    return value


def verified_order(order, fills, intent, order_id):
    terminal = order.get('orderStatus')
    leaves = number(order, 'leavesQty')
    if (order['orderId'] != order_id or order['orderLinkId'] != intent['order_link_id']
            or order['symbol'] != intent['symbol'] or order['side'] != intent['side']
            or terminal not in {'Filled', 'PartiallyFilledCanceled'}
            or (terminal == 'Filled' and leaves != 0) or not fills):
        raise ValueError('terminal exact original Spot order required')
    qty = Decimal('0'); value = Decimal('0'); inventory = Decimal('0'); times = []; ids = set()
    base = intent['symbol'][:-4]
    for fill in fills:
        if (fill['orderId'] != order_id or fill['orderLinkId'] != intent['order_link_id']
                or fill['symbol'] != intent['symbol'] or fill['side'] != intent['side']
                or fill.get('execType') != 'Trade' or not fill.get('execId')
                or fill['execId'] in ids or fill.get('extraFees')):
            raise ValueError('original unique trade executions required')
        ids.add(fill['execId'])
        amount = number(fill, 'execQty', positive=True)
        price = number(fill, 'execPrice', positive=True)
        notional = number(fill, 'execValue', positive=True)
        fee = number(fill, 'execFee')
        if fill.get('feeCurrency') not in {base, 'USDT'} or amount * price != notional:
            raise ValueError('unsupported fee or execution arithmetic')
        base_fee = fee if fill['feeCurrency'] == base else Decimal('0')
        movement = amount-base_fee if intent['side'] == 'Buy' else amount+base_fee
        if movement <= 0:
            raise ValueError('invalid received or consumed inventory')
        qty += amount; value += notional; inventory += movement
        stamp = int(fill['execTime'])
        if stamp <= 0: raise ValueError('positive execution time required')
        times.append(stamp)
    if qty != number(order, 'cumExecQty', positive=True) or value != number(order, 'cumExecValue', positive=True):
        raise ValueError('execution coverage differs from terminal cumulative totals')
    requested = number(intent, 'qty', positive=True)
    executed = value if intent['side'] == 'Buy' else qty
    if executed > requested or (intent['side'] == 'Sell' and terminal == 'Filled' and qty != requested):
        raise ValueError('fills differ from original quote/base request')
    if terminal == 'PartiallyFilledCanceled':
        if executed >= requested or (intent['side'] == 'Sell' and leaves > requested-qty):
            raise ValueError('partial cancellation conflicts with original request')
    return inventory, min(times), max(times), ids


def verify_closed_cycle(buy, sales, wallet, open_orders):
    intent, order, fills, order_id = buy
    if not intent['symbol'].endswith('USDT') or intent['side'] != 'Buy':
        raise ValueError('USDT Spot Buy scope required')
    received, _, buy_end, used = verified_order(order, fills, intent, order_id)
    consumed = Decimal('0')
    if not sales or open_orders:
        raise ValueError('known completed sales and no open symbol orders required')
    for sale_intent, sale_order, sale_fills, sale_id in sales:
        if sale_intent['symbol'] != intent['symbol'] or sale_intent['side'] != 'Sell':
            raise ValueError('matching local sale required')
        quantity, sale_start, _, ids = verified_order(sale_order, sale_fills, sale_intent, sale_id)
        if sale_start < buy_end or used & ids:
            raise ValueError('unordered or reused execution proof')
        used |= ids; consumed += quantity
    if consumed != received:
        raise ValueError('complete received inventory must be consumed exactly')
    if wallet['coin'] != intent['symbol'][:-4] or any(number(wallet, key) != 0
            for key in ('walletBalance', 'locked', 'borrowAmount', 'spotBorrow')):
        raise ValueError('explicit zero final base inventory required')
    return {'schema_version': 'closed-reservation-proof-v2', 'buy_link': intent['order_link_id'],
        'received_base': str(received), 'consumed_base': str(consumed),
        'terminal_order_statuses': {row[3]: row[1]['orderStatus'] for row in [buy, *sales]},
        'execution_ids': sorted(used), 'reservation_release_verified': True,
        'profitability_established': False}


def verify_closed_cohort(buys, sales, wallet, open_orders):
    """Consume only available local lots, then require every lot fully closed."""
    if not buys or not sales or open_orders:
        raise ValueError('complete closed local cohort required')
    symbol = buys[0][0]['symbol']
    if not symbol.endswith('USDT'):
        raise ValueError('USDT Spot cohort required')
    used = set(); orders = set(); links = set(); events = []; sides_at_time = {}
    for entry, expected_side in [(row, 'Buy') for row in buys] + [(row, 'Sell') for row in sales]:
        intent, order, fills, identity = entry
        if intent['side'] != expected_side or intent['symbol'] != symbol:
            raise ValueError('one symbol and explicit cohort sides required')
        if identity in orders or intent['order_link_id'] in links:
            raise ValueError('order cannot appear twice in settlement cohort')
        orders.add(identity); links.add(intent['order_link_id'])
        _, _, _, ids = verified_order(order, fills, intent, identity)
        if used & ids:
            raise ValueError('cohort execution cannot be reused')
        used |= ids
        for fill in fills:
            stamp = int(fill['execTime']); sides_at_time.setdefault(stamp, set()).add(expected_side)
            fee = number(fill, 'execFee') if fill['feeCurrency'] == symbol[:-4] else Decimal('0')
            qty = number(fill, 'execQty', positive=True)
            qty = qty-fee if expected_side == 'Buy' else qty+fee
            events.append((stamp, fill['execId'], expected_side, qty, intent['order_link_id']))
    if any(len(sides) > 1 for sides in sides_at_time.values()):
        raise ValueError('same-time buy/sell ordering is ambiguous')
    lots = deque(); allocations = []; received = Decimal('0'); consumed = Decimal('0')
    for _, identity, side, qty, link in sorted(events):
        if side == 'Buy':
            lots.append([identity, qty, link]); received += qty
            continue
        consumed += qty
        while qty > 0:
            if not lots:
                raise ValueError('sale needs unavailable or external opening inventory')
            lot = lots[0]; matched = min(qty, lot[1])
            allocations.append(dict(buy_exec_id=lot[0], sell_exec_id=identity,
                buy_link=lot[2], sell_link=link, base_quantity=str(matched)))
            lot[1] -= matched; qty -= matched
            if lot[1] == 0: lots.popleft()
    if lots or received != consumed:
        raise ValueError('all local lots must be closed without residual inventory')
    if wallet['coin'] != symbol[:-4] or any(number(wallet, key) != 0
            for key in ('walletBalance', 'locked', 'borrowAmount', 'spotBorrow')):
        raise ValueError('explicit zero final cohort wallet required')
    return dict(schema_version='closed-reservation-cohort-v1', buy_links=[row[0]['order_link_id'] for row in buys],
        execution_ids=sorted(used), received_base=str(received), consumed_base=str(consumed),
        fifo_allocations=allocations, same_side_timestamp_tie_policy='execId lexicographic; no cost-basis claim',
        reservation_release_verified=True, profitability_established=False)


def collect_pages(client, endpoint, params, receipts):
    rows = []; seen = set()
    for _ in range(20):
        response = client._private_get(endpoint, dict(params))
        receipts.append(dict(endpoint=endpoint, params=dict(params), response=response))
        if response.get('retCode') != 0 or response['result'].get('category') != 'spot':
            raise ValueError('unqualified settlement source')
        result = response['result']
        if not isinstance(result.get('list'), list): raise ValueError('source list required')
        rows.extend(result['list'])
        cursor = result['nextPageCursor']
        if not isinstance(cursor, str) or cursor in seen:
            raise ValueError('invalid settlement pagination')
        if not cursor: return rows
        seen.add(cursor); params = dict(params, cursor=cursor)
    raise ValueError('incomplete settlement pagination')


def collect_order(client, entry, receipts):
    intent, order_id = entry
    params = dict(category='spot', orderId=order_id, limit='50')
    orders = collect_pages(client, '/v5/order/history', params, receipts)
    if len(orders) != 1: raise ValueError('one exact terminal order source required')
    fills = collect_pages(client, '/v5/execution/list', dict(params, limit='100'), receipts)
    return intent, orders[0], fills, order_id


def settle_journal(journal, client):
    with journal.connect() as db:
        rows = db.execute("SELECT link,symbol,payload,sha,response,observed_at FROM order_submissions "
            "WHERE status IN ('acknowledged','observed')").fetchall()
    entries = []
    for link, symbol, raw, sha, response, stamp in rows:
        if hashlib.sha256(raw.encode()).hexdigest() != sha: raise ValueError('corrupt settlement intent')
        intent = json.loads(raw); previous = json.loads(response)
        ids = {row['orderId'] for row in previous.get('exchange_observations', [])}
        if previous.get('result', {}).get('orderId'): ids.add(previous['result']['orderId'])
        if len(ids) == 1: entries.append((intent, ids.pop(), stamp))
    released = 0; retained = 0
    symbols = sorted({intent['symbol'] for intent, _, _ in entries if intent['side']=='Buy'})
    for symbol in symbols:
        cohort = [(intent, identity, stamp) for intent, identity, stamp in entries
            if intent['side']=='Buy' and intent['symbol']==symbol]
        try:
            receipts = []
            buys = [collect_order(client, (intent, identity), receipts) for intent, identity, _ in cohort]
            first_observed = min(datetime.fromisoformat(stamp) for _, _, stamp in cohort)
            sales = [collect_order(client, (sale, sale_id), receipts) for sale, sale_id, sale_stamp in entries
                if sale['side']=='Sell' and sale['symbol']==symbol
                and datetime.fromisoformat(sale_stamp) >= first_observed]
            pending = collect_pages(client, '/v5/order/realtime',
                dict(category='spot', symbol=symbol, openOnly='0', limit='50'), receipts)
            response = client._private_get('/v5/account/wallet-balance',
                dict(accountType='UNIFIED', coin=symbol[:-4]))
            receipts.append(dict(endpoint='/v5/account/wallet-balance', response=response))
            accounts = response['result']['list']
            if response.get('retCode') != 0 or len(accounts) != 1 or accounts[0].get('accountType') != 'UNIFIED':
                raise ValueError('one authenticated wallet account required')
            coins = accounts[0]['coin']
            if len(coins) != 1: raise ValueError('explicit final base coin required')
            proof = (verify_closed_cycle(buys[0], sales, coins[0], pending) if len(buys)==1
                else verify_closed_cohort(buys, sales, coins[0], pending))
            proof.update(observed_at=datetime.now(UTC).isoformat(), original_sources=receipts)
            proof['source_sha256'] = hashlib.sha256(json.dumps(receipts, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (ValueError, KeyError, TypeError, ArithmeticError, OSError):
            retained += len(cohort)
            continue
        journal.release_closed_cohort({intent['order_link_id']: hashlib.sha256(
            json.dumps(intent, sort_keys=True, allow_nan=False).encode()).hexdigest() for intent, _, _ in cohort}, proof)
        released += len(cohort)
    return dict(released_closed=released, retained=retained)
