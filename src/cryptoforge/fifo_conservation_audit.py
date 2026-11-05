"""Independently validate FIFO allocation order and remaining acquisition basis."""
from collections import defaultdict,deque
from decimal import Decimal
from cryptoforge.fifo_case_audit import audit_segment

D=Decimal


def audit_conservation(fills,records):
    source={fill['execId']:fill for fill in fills}
    if len(source)!=len(fills):raise ValueError('unique FIFO source identities required')
    rows={row['external_trade_id']:row for row in records}
    if len(rows)!=len(records):raise ValueError('unique allocated segment identities required')
    queues=defaultdict(deque);lots=[];checked=set();closed=0;unmatched=D(0)
    def owned(fill):return str(fill.get('orderLinkId') or '').startswith('cf-')
    def equal(actual,expected):
        value=D(str(actual))
        if not value.is_finite() or abs(value-expected)>max(D('1e-24'),abs(expected)*D('1e-24')):
            raise ValueError('FIFO quantity or basis conservation differs from source')
    for fill in sorted(fills,key=lambda row:(int(row['execTime']),row['execId'])):
        symbol=fill['symbol']
        if fill.get('execType','Trade')!='Trade' or not symbol.endswith('USDT'):continue
        qty=D(fill['execQty']);basefee=D(fill.get('execFee') or 0) if fill.get('feeCurrency')==symbol[:-4] else D(0)
        if fill['side']=='Buy':
            received=qty-basefee
            if not received.is_finite() or received<=0:raise ValueError('positive received inventory required')
            lot={'fill':fill,'received':received,'remaining':received}
            queues[symbol].append(lot);lots.append(lot)
        elif fill['side']=='Sell':
            remaining=qty+basefee
            if not remaining.is_finite() or remaining<=0:raise ValueError('positive consumed inventory required')
            while remaining>0 and queues[symbol]:
                lot=queues[symbol][0];matched=min(remaining,lot['remaining']);buy=lot['fill']
                if owned(buy) or owned(fill):
                    key=f"bybit:spot:fifo:{buy['execId']}:{fill['execId']}"
                    if key not in rows:raise ValueError('missing original FIFO allocation')
                    row=rows[key]
                    if row['status']!='closed':raise ValueError('closed source allocation required')
                    equal(row['amount'],matched);audit_segment(row,fills);checked.add(key);closed+=1
                lot['remaining']-=matched;remaining-=matched
                if lot['remaining']==0:queues[symbol].popleft()
            unmatched+=remaining
        else:raise ValueError('explicit FIFO source side required')
    open_lots=0;basis=D(0)
    for lot in lots:
        fill=lot['fill']
        if not owned(fill):continue
        key=f"bybit:spot:fifo:{fill['execId']}:remaining"
        if key not in rows:raise ValueError('remaining acquisition record required even at zero')
        row=rows[key];equal(row['amount'],lot['remaining'])
        expected_status='open' if lot['remaining']>0 else 'cancelled'
        if row['status']!=expected_status:raise ValueError('remaining acquisition status mismatch')
        value=D(fill['execValue']) if fill.get('execValue') not in (None,'') else D(fill['execQty'])*D(fill['execPrice'])
        quote_fee=D(fill.get('execFee') or 0) if fill.get('feeCurrency')=='USDT' else D(0)
        cost=(value+quote_fee)*lot['remaining']/lot['received']
        equal(row['stake_amount'],cost);checked.add(key);basis+=cost;open_lots+=lot['remaining']>0
    if checked!=set(rows):raise ValueError('unmatched extra FIFO segment records')
    return {'closed_allocations_checked':closed,'remaining_records_checked':len(checked)-closed,
            'open_lots':open_lots,'open_basis':str(basis),'unmatched_sale_quantity':str(unmatched),
            'fifo_order_and_conservation_verified':True,'historical_execution_certified':False,
            'live_promotion_allowed':False}
