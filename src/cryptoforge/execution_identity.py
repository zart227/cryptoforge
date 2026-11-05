"""Validate immutable economic execution fields before FIFO or inventory audit."""
from decimal import Decimal, InvalidOperation

FIELDS=('symbol','side','execTime','execType','execQty','execPrice','execValue',
        'execFee','feeCurrency','extraFees','orderId','orderLinkId')
NUMERIC={'execQty','execPrice','execValue','execFee'}


def unique_executions(fills):
    seen={};result=[]
    for fill in fills:
        identity=fill.get('execId')
        if not isinstance(identity,str) or not identity:
            raise ValueError('execution identity required')
        signature=[]
        for key in FIELDS:
            value=fill.get(key)
            if key in NUMERIC and value not in (None,''):
                try:number=Decimal(str(value))
                except (InvalidOperation,ValueError) as exc:raise ValueError('invalid execution number') from exc
                if not number.is_finite():raise ValueError('finite execution numbers required')
                value=number
            if key=='execType' and value is None:value='Trade'
            signature.append(value)
        signature=tuple(signature)
        if identity in seen:
            if seen[identity]!=signature:raise ValueError('conflicting immutable execution identity')
            continue
        seen[identity]=signature
        if fill.get('execType','Trade')=='Trade' and str(fill.get('symbol','')).endswith('USDT'):
            if fill.get('side') not in {'Buy','Sell'}:raise ValueError('explicit execution side required')
            if any(Decimal(str(fill.get(key) or 0))<=0 for key in ('execQty','execPrice')):
                raise ValueError('positive execution quantity and price required')
            if fill.get('execValue') not in (None,'') and Decimal(str(fill['execValue']))<=0:
                raise ValueError('positive execution value required')
            try:stamp=int(fill['execTime'])
            except (KeyError,ValueError,TypeError) as exc:raise ValueError('execution time required') from exc
            if stamp<0:raise ValueError('nonnegative execution time required')
        result.append(fill)
    return result
