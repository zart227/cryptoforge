"""Common price/time exit precedence; observation and fill models stay explicit."""
from decimal import Decimal


def price_time_exit(*,price,entry_price,stop_fraction,elapsed_seconds,maximum_hold_seconds,target_fraction=None):
    for value in (price,entry_price):
        if not isinstance(value,Decimal) or not value.is_finite() or value<=0:raise ValueError('positive finite observed exit price required')
    for value in (stop_fraction,target_fraction):
        if value is not None and (not isinstance(value,Decimal) or not value.is_finite() or not 0<value<1):
            raise ValueError('finite declared exit fraction required')
    if stop_fraction is None:raise ValueError('explicit hard-stop rule required')
    for value in (elapsed_seconds,maximum_hold_seconds):
        if type(value) not in (int,float,Decimal):raise ValueError('finite exit duration required')
        if not Decimal(str(value)).is_finite():raise ValueError('finite exit duration required')
    if elapsed_seconds<0 or maximum_hold_seconds<=0:raise ValueError('ordered positive exit duration required')
    if price<=entry_price*(1-stop_fraction):return 'stop'
    if target_fraction is not None and price>=entry_price*(1+target_fraction):return 'target'
    if elapsed_seconds>=maximum_hold_seconds:return 'timeout'
    return None
