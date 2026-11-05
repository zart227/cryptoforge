"""Independent arithmetic check of an observed allocated FIFO segment."""
from decimal import Decimal
import re


def audit_segment(segment, fills):
    lookup={row['execId']:row for row in fills}
    if len(lookup)!=len(fills):raise ValueError('unique original execution inputs required')
    def execution(reason):
        match=re.search(r'\bexecution=([^\s]+)',reason or '')
        if not match or match[1] not in lookup:raise ValueError('original segment execution source required')
        return lookup[match[1]]
    buy=execution(segment['entry_reason']);sell=execution(segment['exit_reason'])
    if buy['side']!='Buy' or sell['side']!='Sell' or buy['symbol']!=sell['symbol']:
        raise ValueError('paired acquisition and sale sources required')
    if int(buy['execTime'])>int(sell['execTime']):raise ValueError('acquisition must precede sale')
    symbol=buy['symbol'];base=symbol[:-4]
    if not symbol.endswith('USDT') or segment['pair']!=base+'/USDT':raise ValueError('segment market differs from source')
    def number(row,key):
        value=Decimal(str(row[key]))
        if not value.is_finite():raise ValueError('finite source accounting required')
        return value
    def amounts(row):
        qty=number(row,'execQty');price=number(row,'execPrice');fee=number(row,'execFee')
        value=number(row,'execValue') if row.get('execValue') not in (None,'') else qty*price
        currency=row.get('feeCurrency')
        if qty<=0 or price<=0 or value<=0:raise ValueError('positive execution economics required')
        if row.get('extraFees') or fee!=0 and currency not in {base,'USDT'}:
            raise ValueError('known base or quote fee source required')
        return qty,value,fee if currency==base else Decimal(0),fee if currency=='USDT' else Decimal(0),fee*price if currency==base else fee
    bqty,bvalue,bbase,bquote,bfee=amounts(buy)
    sqty,svalue,sbase,squote,sfee=amounts(sell)
    acquired=bqty-bbase;consumed=sqty+sbase;matched=number(segment,'amount')
    if not 0<matched<=min(acquired,consumed):raise ValueError('allocated quantity exceeds source acquisition or sale')
    cost=(bvalue+bquote)*matched/acquired
    proceeds=(svalue-squote)*matched/consumed
    fees=bfee*matched/acquired+sfee*matched/consumed
    expected={'stake_amount':cost,'fee_amount':fees,'realized_pnl':proceeds-cost}
    for key,value in expected.items():
        actual=number(segment,key)
        if abs(actual-value)>max(Decimal('1e-24'),abs(value)*Decimal('1e-24')):
            raise ValueError('source allocation differs from segment '+key)
    return {'segment_id':segment['external_trade_id'],'buy_execution_id':buy['execId'],'sell_execution_id':sell['execId'],
        'allocated_quantity':str(matched),'source_received_quantity':str(acquired),'source_consumed_quantity':str(consumed),
        'partial_acquisition_allocation':matched<acquired,'partial_sale_allocation':matched<consumed,
        'buy_fee_currency':buy.get('feeCurrency'),'sell_fee_currency':sell.get('feeCurrency'),
        'sale_source':sell.get('journalSource','spot_execution'),'arithmetic_passed':True,
        'full_fifo_order_certified':False,'historical_market_rules_certified':False}
