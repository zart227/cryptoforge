"""Identify legacy candle-key collisions without inventing lost order reasons."""
from datetime import datetime
import hashlib


def diagnose_case(evidence):
    case = evidence['case']
    pair, order_id = case['pair'], case['exit_order']
    orders = [o for o in evidence['exchange_order_response']['result']['list']
              if str(o.get('orderId')) == order_id and o.get('symbol') == pair.replace('/', '')
              and o.get('side') == 'Sell']
    if len(orders) != 1:
        raise ValueError('one exact exchange sell order required')
    order = orders[0]
    link = order['orderLinkId']
    matches = []
    for row in evidence['nearby_decisions']:
        if row.get('pair') != pair or row.get('mode') != 'live':
            continue
        candle = (row.get('features') or {}).get('latest_open_time')
        if not candle:
            continue
        stamp = datetime.fromisoformat(candle)
        if stamp.tzinfo is None:
            continue
        exit_digest = hashlib.sha256(f'{pair}:exit:{candle}'.encode()).hexdigest()
        row_digest = hashlib.sha256(f'{pair}:{candle}'.encode()).hexdigest()
        if link == 'cf-' + exit_digest[:28]:
            expected_key = 'cf-' + row_digest[:28]
        elif len(link.split('-')) == 3 and link.endswith('-' + exit_digest[:20]):
            expected_key = 'cf-' + link.split('-')[1] + '-' + row_digest[:20]
        else:
            continue
        if row.get('idempotency_key') != expected_key:
            continue
        result = ((row.get('features') or {}).get('order') or {}).get('result') or {}
        if result.get('orderId'):
            continue
        executed = datetime.fromisoformat(case['closed_at'])
        decided = datetime.fromisoformat(row['decided_at'])
        created = datetime.fromisoformat(row['created_at'])
        if any(t.tzinfo is None for t in (executed, decided, created)):
            raise ValueError('aware evidence timestamps required')
        if decided <= executed or created > decided:
            continue
        matches.append({'pair': pair, 'order_id': order_id, 'order_link_id': link,
                        'execution_at': case['closed_at'], 'net_return_pct': case['net_return_pct'],
                        'matched_candle': candle, 'legacy_record_key': expected_key,
                        'record_created_at': row['created_at'], 'record_updated_at': row['decided_at'],
                        'created_minus_execution_seconds': (created-executed).total_seconds(),
                        'surviving_decision': row['decision'],
                        'surviving_reasons': row['reasons'],
                        'exact_exit_candle_hash_match': True,
                        'legacy_record_collision_supported': True,
                        'original_exit_reasons_recovered': False,
                        'surviving_reasons_are_exit_reasons': False})
    if len(matches) != 1:
        raise ValueError('unique later legacy candle-key record required')
    return matches[0]
