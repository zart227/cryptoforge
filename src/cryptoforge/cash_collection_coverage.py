"""Collection diagnostics by actual buy identity, never additional training labels."""
from collections import Counter
from cryptoforge.live_experience import _order,_time


def collection_coverage(trades,covered_keys,result,*,source_as_of):
    groups={}
    for row in trades:
        identity=str(row.get('idempotency_key') or '')
        if not identity.startswith('bybit:spot:fifo:') or row.get('mode')!='live':continue
        if _time(row['opened_at'])>source_as_of:continue
        if 'origin=cryptoforge' not in str(row.get('entry_reason')):continue
        order=_order(row.get('entry_reason'))
        if order:groups.setdefault((row['pair'],order),[]).append(row)
    accepted={(r['pair'],r['entry_order']) for r in result['examples']}
    excluded={(r.get('pair'),r.get('entry_order')):r['reason'] for r in result['excluded']}
    categories=Counter();pairs=Counter();details=[]
    for key,rows in sorted(groups.items()):
        # Cancelled zero-basis remainder proves closure; it is not a new sample.
        active=[r for r in rows if r['status'] in {'open','closed'}]
        if not active:continue
        if key in accepted:status='eligible_current_snapshot'
        elif key in excluded:status='excluded:'+excluded[key]
        elif not any(r['status']=='closed' for r in active):status='awaiting_first_closed_exit'
        elif key not in covered_keys:status='outside_current_verified_audit_coverage'
        else:status='unexplained_collection_omission'
        categories[status]+=1;pairs[key[0]]+=1
        details.append({'pair':key[0],'entry_order':key[1],
            'entry_at':min(_time(r['opened_at']) for r in active).isoformat(),'status':status})
    return {'schema_version':'cash-collection-coverage-v1','source_as_of':source_as_of.isoformat(),
        'scope':'canonical_rows_returned_by_reader_not_exchange_wide_history',
        'distinct_bot_buy_orders':sum(categories.values()),'status_counts':dict(categories),
        'pair_counts':dict(pairs),'buys':details,'unexplained_omissions':categories['unexplained_collection_omission'],
        'diagnostic_only':True,'additional_training_examples':0}
