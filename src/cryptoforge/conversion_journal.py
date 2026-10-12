"""Verified small-balance conversions as accounting events, never exchange orders."""
from decimal import Decimal

D=Decimal


def conversion_fills(records,transactions):
    result=[]
    for record in records:
        if record.get('accountType')!='eb_convert_uta' or record.get('status') not in {'success','partial_fulfillment'}:continue
        quote=str(record['exchangeTxId']);created=int(record['createdAt'])
        for sub in record.get('subRecords',[]):
            if sub.get('status')!='success':continue
            coin=str(sub['fromCoin'])
            if coin=='USDT':continue
            if sub.get('toCoin')!='USDT':raise ValueError('non-USDT conversion requires explicit cross-currency accounting')
            qty=D(str(sub['fromAmount']));net=D(str(sub['toAmount']));fee=D(str(sub.get('feeAmount') or 0))
            tax_info=sub.get('taxFeeInfo') or {};tax=D(str(tax_info.get('totalAmount') or 0))
            if fee and sub.get('feeCoin')!='USDT':raise ValueError('unknown conversion fee currency')
            if tax and tax_info.get('feeCoin')!='USDT':raise ValueError('unknown conversion tax currency')
            if not all(x.is_finite() for x in (qty,net,fee,tax)) or qty<=0 or net<=0 or min(fee,tax)<0:
                raise ValueError('invalid conversion amounts')
            matched=[t for t in transactions if t.get('type')=='CURRENCY_SELL' and t.get('currency')==coin
                and str(t.get('id','')).startswith(quote+'_') and D(str(t.get('change') or 0))==-qty
                and created<=int(t['transactionTime'])<=created+300000]
            if len(matched)!=1:raise ValueError('conversion inventory debit not uniquely verified')
            debit=matched[0];time=int(debit['transactionTime'])
            credit=[t for t in transactions if t.get('type')=='CURRENCY_BUY' and t.get('currency')=='USDT'
                    and str(t.get('id','')).startswith(quote+'_'+coin)
                    and int(t['transactionTime'])==time and abs(D(str(t.get('change') or 0))-net)<=D('0.00000001')]
            if len(credit)!=1:raise ValueError('conversion USDT proceeds not independently verified')
            total_fee=fee+tax;gross=net+total_fee
            result.append({'execId':'conversion:'+quote+':'+coin,'orderId':'conversion:'+quote+':'+coin,
                'orderLinkId':'','execTime':str(time),'execType':'Trade','side':'Sell','symbol':coin+'USDT',
                'execQty':str(qty),'execPrice':str(gross/qty),'execValue':str(gross),
                'execFee':str(total_fee),'feeCurrency':'USDT','journalSource':'verified_small_balance_conversion',
                'sourceDebitId':debit['id'],'sourceCreditId':credit[0]['id'],'sourceQuoteId':quote})
    return result
