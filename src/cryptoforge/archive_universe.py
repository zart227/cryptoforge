"""Causal liquidity membership within an explicitly limited fixed archive basket."""
from decimal import Decimal
from typing import Iterable

from cryptoforge.market_data import Candle,interval_to_milliseconds

DAY_MS=86400000


def daily_membership(candles: Iterable[Candle], *, minimum_turnover=Decimal('1000000')) -> list[dict]:
    """Membership at next UTC midnight uses ONLY the previous completed day.

    This cannot reconstruct delisted or uncollected pairs and is not evidence
    of historical instrument filters. A fixed survivor basket remains biased.
    """
    buckets={}
    previous=None
    identity=None
    for candle in candles:
        current_identity=(candle.symbol,candle.interval)
        if identity is not None and identity!=current_identity:
            raise ValueError('mixed history')
        identity=current_identity
        step=interval_to_milliseconds(candle.interval)
        if DAY_MS%step or candle.start_ms%step:
            raise ValueError('UTC-aligned intraday candle interval required')
        if previous is not None and candle.start_ms<=previous:
            raise ValueError('one symbol in increasing timestamp order required')
        previous=candle.start_ms
        day=candle.start_ms//DAY_MS*DAY_MS
        bucket=buckets.setdefault(day,{'symbol':candle.symbol,'interval':candle.interval,'count':0,'turnover':Decimal(0)})
        if candle.symbol!=bucket['symbol'] or candle.interval!=bucket['interval']:
            raise ValueError('mixed history')
        if not candle.turnover.is_finite() or candle.turnover<0:
            raise ValueError('invalid turnover')
        bucket['count']+=1;bucket['turnover']+=candle.turnover
    return [{'effective_at_ms':day+DAY_MS,'observed_day_start_ms':day,
             'symbol':bucket['symbol'],'source_candles':bucket['count'],
             'turnover_usdt_previous_day':str(bucket['turnover']),
             'included':bucket['count']==DAY_MS//interval_to_milliseconds(bucket['interval']) and bucket['turnover']>=minimum_turnover,
             'evidence':'completed_historical_candles_only','historical_instrument_rules':'unknown',
             'scope':'fixed_basket_not_entire_exchange'} for day,bucket in sorted(buckets.items())]
