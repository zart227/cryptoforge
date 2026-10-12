"""Verify dated universe decisions against immutable candle evidence."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from cryptoforge.archive_quality import validate_candles
from cryptoforge.market_data import Candle

DAY_MS = 86400000


def verify_probe(result: dict, *, as_of_ms: int) -> dict:
    raw = Path(result['snapshot_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != result['source_sha256']:
        raise ValueError('probe evidence hash mismatch')
    evidence = json.loads(raw)
    query = evidence['query']
    symbol = result['symbol']
    start = as_of_ms - DAY_MS
    if (query.get('category'), query.get('symbol'), query.get('interval'),
        query.get('start'), query.get('end')) != ('spot', symbol, '60', start, as_of_ms - 1):
        raise ValueError('probe must cover only the completed prior UTC day')
    candles = [Candle(**{key: Decimal(value) if key in {
        'open', 'high', 'low', 'close', 'volume', 'turnover'
    } else value for key, value in row.items()}) for row in evidence['candles']]
    quality = validate_candles(candles, now_ms=as_of_ms)
    if any(c.symbol != symbol or c.interval != '60' for c in candles):
        raise ValueError('mixed probe candles')
    # Bybit can return older bars for delisted symbols despite query bounds.
    # Preserve the raw response as evidence, but never admit it as a complete day.
    complete = (len(candles) == 24 and candles[0].start_ms == start
                and candles[-1].close_ms == as_of_ms and not quality['gap_ranges'])
    expected_status = 'complete_prior_day' if complete else 'no_complete_prior_day'
    if result['status'] != expected_status or result['candles'] != len(candles):
        raise ValueError('probe completeness mismatch')
    eligible = False
    if complete:
        turnover = sum((c.turnover for c in candles), Decimal(0))
        movement = (max(c.high for c in candles) - min(c.low for c in candles)) / candles[-1].close
        if (turnover != Decimal(result['prior_day_turnover_usdt']) or
                movement != Decimal(result['prior_day_range_fraction'])):
            raise ValueError('probe metrics mismatch')
        eligible = turnover >= Decimal('1000000') and movement >= Decimal('.01')
    if result['liquidity_eligible'] != eligible:
        raise ValueError('probe eligibility mismatch')
    return {'symbol': symbol, 'eligible': eligible,
            'turnover': Decimal(result.get('prior_day_turnover_usdt', '0'))}
