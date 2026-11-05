"""Independent quantity/opening-balance check before learning from FIFO PnL."""
from decimal import Decimal
from cryptoforge.execution_identity import unique_executions

D=Decimal


def verify_inventory(fills,transactions,wallet_coins,*,tolerance=D('0.00000001')):
    fills=[fill for fill in unique_executions(fills) if fill.get('execType','Trade')=='Trade' and str(fill.get('symbol','')).endswith('USDT')]
    if len({r['coin'] for r in wallet_coins})!=len(wallet_coins):raise ValueError('duplicate wallet coin')
    wallet={r['coin']:D(str(r['walletBalance'])) for r in wallet_coins}
    if any(not value.is_finite() for value in wallet.values()):raise ValueError('finite wallet balance required')
    tracked={str(r['symbol'])[:-4] for r in fills if str(r.get('orderLinkId') or '').startswith('cf-')}
    results=[]
    for coin in sorted(tracked):
        expected=D(0);unknown_fees=0
        for fill in fills:
            if fill['symbol']!=coin+'USDT':continue
            if fill.get('execFee') in (None,'') or (D(str(fill['execFee']))!=0 and not fill.get('feeCurrency')) or fill.get('extraFees'):
                unknown_fees+=1
            quantity=D(str(fill['execQty']))
            fee=D(str(fill.get('execFee') or 0)) if fill.get('feeCurrency')==coin else D(0)
            expected+=quantity-fee if fill['side']=='Buy' else -quantity-fee
        tx=sorted((t for t in transactions if t.get('currency')==coin),key=lambda t:(int(t['transactionTime']),str(t.get('id',''))))
        first=tx[0] if tx else None
        opening=D(str(first['cashBalance']))-D(str(first['change'])) if first else None
        if opening is not None and not opening.is_finite():raise ValueError('finite opening inventory required')
        actual=wallet.get(coin);difference=actual-expected if actual is not None else None
        consistent=not unknown_fees and opening is not None and actual is not None and abs(opening)<=tolerance and abs(difference)<=tolerance
        results.append({'coin':coin,'known_inventory':str(expected),'wallet_inventory':str(actual) if actual is not None else None,
                        'opening_inventory':str(opening) if opening is not None else None,
                        'difference':str(difference) if difference is not None else None,'unknown_fee_executions':unknown_fees,'consistent':consistent})
    return {'coins':results,'consistent':bool(results) and all(r['consistent'] for r in results),
            'scope':'tracked_coins_only_unknown_opening_inventory_is_not_assumed_zero'}
