"""Independent Decimal replay of paper fill and FIFO segment accounting."""
from decimal import Decimal as D
from cryptoforge.live_learning_protocol import time


def _number(value):
    result=D(str(value))
    if not result.is_finite():raise ValueError('finite paper arithmetic required')
    return result


def _same(actual,expected):
    if abs(_number(actual)-expected)>D('1e-20'):
        raise ValueError('paper fill or segment arithmetic mismatch')


def verify_paper_fill_arithmetic(fills,segments,config):
    entry,exit,slippage=(_number(config[key]) for key in ('entry_fee','exit_fee','slippage'))
    if any(not 0<=value<1 for value in (entry,exit,slippage)):raise ValueError('explicit paper execution fractions required')
    indexed={}
    for fill in fills:
        identity=fill['intent_id']
        if identity in indexed:raise ValueError('duplicate paper fill identity')
        indexed[identity]=fill
        qty,order,price=(_number(fill[key]) for key in ('quantity','order_quantity','price'))
        if min(qty,order,price)<=0:raise ValueError('positive paper fill inputs required')
        quote,filters=fill['quote'],fill['filters']
        if quote['pair']!=fill['pair'] or filters['pair']!=fill['pair']:raise ValueError('original market fill pair required')
        if not time(fill['signal_time'])<time(fill['filled_at']) or not (
                time(filters['observed_at'])<=time(quote['observed_at'])<=time(fill['filled_at'])):
            raise ValueError('paper fill consumed unavailable market information')
        if fill['quote_observed_at']!=quote['observed_at']:
            raise ValueError('paper fill original quote clock mismatch')
        if order>_number(filters['maximum_market_quantity']):raise ValueError('paper fill violates maximum quantity')
        depth=_number(quote['ask_qty'] if fill['side']=='Buy' else quote['bid_qty'])
        if order>depth*_number(config['max_depth_fraction']):raise ValueError('paper fill violates displayed depth assumption')
        step=_number(filters['quantity_step'])
        if step<=0 or order%step!=0 or order*price<_number(filters['minimum_notional']):
            raise ValueError('paper fill violates recorded quantity/minimum rules')
        if fill['side']=='Buy':
            if _number(fill['cost'])>_number(config['stake']):
                raise ValueError('paper acquisition exceeds frozen stake budget')
            if fill['fee_currency']!='base':raise ValueError('explicit base purchase fee required')
            _same(price,_number(quote['ask'])*(1+slippage))
            _same(qty,order*(1-entry));_same(fill['cost'],order*price)
            _same(fill['fee_amount'],order*entry);_same(fill['fee_quote_equivalent'],order*price*entry)
        elif fill['side']=='Sell':
            if fill['fee_currency']!='quote':raise ValueError('explicit quote sale fee required')
            _same(price,_number(quote['bid'])*(1-slippage));_same(qty,order)
            _same(fill['proceeds'],qty*price*(1-exit))
            _same(fill['fee_amount'],qty*price*exit);_same(fill['fee_quote_equivalent'],qty*price*exit)
        else:raise ValueError('explicit paper fill side required')
    sales={key:[] for key,fill in indexed.items() if fill['side']=='Sell'}
    for segment in segments:
        buy=indexed.get(segment['entry_intent']);sell=indexed.get(segment['exit_intent'])
        if not buy or not sell or buy['side']!='Buy' or sell['side']!='Sell' or not segment['pair']==buy['pair']==sell['pair']:
            raise ValueError('FIFO segment requires original paired fills')
        qty=_number(segment['quantity'])
        if qty<=0:raise ValueError('positive FIFO segment required')
        fraction=qty/_number(buy['quantity']);cost=_number(buy['cost'])*fraction
        _same(segment['cost'],cost)
        _same(segment['net_pnl'],qty*_number(sell['price'])*(1-exit)-cost)
        _same(segment['fees'],_number(buy['fee_quote_equivalent'])*fraction+qty*_number(sell['price'])*exit)
        sales[segment['exit_intent']].append(segment)
    for identity,values in sales.items():
        _same(sum((_number(row['quantity']) for row in values),D(0)),_number(indexed[identity]['quantity']))
    return {'fills_verified':len(fills),'segments_verified':len(segments),'scope':'recorded_paper_assumption_arithmetic_not_real_fill_certification'}
