"""Independent quantity/opening-balance check before learning from FIFO PnL."""
from decimal import Decimal

D=Decimal


def verify_inventory(fills,transactions,wallet_coins,*,tolerance=D('0.00000001')):
    wallet={r['coin']:D(str(r.get('walletBalance') or 0)) for r in wallet_coins}
    tracked={str(r['symbol'])[:-4] for r in fills if str(r.get('orderLinkId') or '').startswith('cf-')}
    results=[]
    for coin in sorted(tracked):
        expected=D(0)
        for fill in fills:
            if fill['symbol']!=coin+'USDT':continue
            quantity=D(str(fill['execQty']))
            fee=D(str(fill.get('execFee') or 0)) if fill.get('feeCurrency')==coin else D(0)
            expected+=quantity-fee if fill['side']=='Buy' else -quantity-fee
        tx=sorted((t for t in transactions if t.get('currency')==coin),key=lambda t:(int(t['transactionTime']),str(t.get('id',''))))
        first=tx[0] if tx else None
        opening=D(str(first['cashBalance']))-D(str(first['change'])) if first else None
        actual=wallet.get(coin,D(0));difference=actual-expected
        consistent=opening is not None and abs(opening)<=tolerance and abs(difference)<=tolerance
        results.append({'coin':coin,'known_inventory':str(expected),'wallet_inventory':str(actual),
                        'opening_inventory':str(opening) if opening is not None else None,
                        'difference':str(difference),'consistent':consistent})
    return {'coins':results,'consistent':bool(results) and all(r['consistent'] for r in results),
            'scope':'tracked_coins_only_unknown_opening_inventory_is_not_assumed_zero'}
