"""Independent rational oracle for v2 paper replay. No producer math imports."""
from contextlib import contextmanager
from decimal import Context,Decimal,localcontext
from fractions import Fraction

PRECISION = 2048
ALLOCATION_PLACES = 512


@contextmanager
def arithmetic():
    with localcontext(Context(prec=PRECISION)):
        yield


def number(value,*,zero=False,limit=128):
    result=Decimal(str(value))
    parts=result.as_tuple()
    if (not result.is_finite() or len(parts.digits)>limit or abs(parts.exponent)>limit
            or result<0 or not zero and result==0):
        raise ValueError('bounded finite independent replay number required')
    return result


def decimal(value):
    """Integer long division constructs a finite decimal without context division."""
    value=Fraction(value)
    whole,remainder=divmod(abs(value.numerator),value.denominator)
    digits=[]
    while remainder:
        digit,remainder=divmod(remainder*10,value.denominator)
        digits.append(str(digit))
        if len(digits)>4096:raise ValueError('bounded terminating replay decimal required')
    text=('-' if value<0 else '')+str(whole)+('.'+''.join(digits) if digits else '')
    result=Decimal(text)
    if len(result.as_tuple().digits)>4096:raise ValueError('replay result representation exhausted')
    return result


def total(values):return decimal(sum((Fraction(v) for v in values),Fraction(0)))
def product(*values):
    result=Fraction(1)
    for value in values:result*=Fraction(value)
    return decimal(result)

def difference(left,right):return decimal(Fraction(left)-Fraction(right))
def floor_quantity(amount,step):
    a=Fraction(number(amount,zero=True,limit=4096));unit=Fraction(number(step))
    return decimal((a//unit)*unit)


def acquisition(budget,price,step,fee,*,fee_currency='base'):
    b,p,s,f=(Fraction(number(v,zero=i==3)) for i,v in enumerate((budget,price,step,fee)))
    if f>=1 or fee_currency not in {'base','quote'}:raise ValueError('explicit independent replay fee required')
    per_step=s*p*(1+f if fee_currency=='quote' else 1)
    units=b//per_step
    gross=units*s;notional=gross*p
    cash=notional*(1+f if fee_currency=='quote' else 1)
    if not cash<=b<(units+1)*per_step:raise ValueError('independent maximal affordable quantity violated')
    return dict(gross=decimal(gross),quantity=decimal(gross*(1-f) if fee_currency=='base' else gross),
        cost=decimal(cash),fee=decimal(notional*f),amount=decimal(gross*f if fee_currency=='base' else notional*f))


def sale(quantity,price,fee):
    q=Fraction(number(quantity,limit=4096));p=Fraction(number(price,limit=4096));f=Fraction(number(fee,zero=True))
    if f>=1:raise ValueError('independent sale fee must be below one')
    notional=q*p
    return decimal(notional*(1-f)),decimal(notional*f)


def allocate(basis,sold,quantity):
    b=Fraction(number(basis,zero=True,limit=4096));s=Fraction(number(sold,limit=4096));q=Fraction(number(quantity,limit=4096))
    if s>q:raise ValueError('independent allocation exceeds owned lot')
    if s==q:return decimal(b)
    # Integer divmod is an independent oracle for the registered 512-place floor.
    numerator=b.numerator*s.numerator*q.denominator*10**ALLOCATION_PLACES
    denominator=b.denominator*s.denominator*q.numerator
    units,_=divmod(numerator,denominator)
    return decimal(Fraction(units,10**ALLOCATION_PLACES))
