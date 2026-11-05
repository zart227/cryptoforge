"""Exit-only public candle fallback, separate from frozen research kernels."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from cryptoforge.supabase_executor import CandleRow, ExecutorDecision


def validate_exit_candles(rows, pair, now, minimum, maximum_age):
    if now.tzinfo is None or len(rows) < minimum:
        raise ValueError('insufficient closed exit candles')
    step = timedelta(minutes=5)
    previous = None
    for row in rows:
        if (row.pair != pair or row.symbol != pair.replace('/', '')
                or row.open_time.tzinfo is None or row.open_time + step > now
                or row.open_time.timestamp() % 300 != 0
                or (previous is not None and row.open_time - previous != step)):
            raise ValueError('invalid exit candle chronology or market')
        values = (row.open, row.high, row.low, row.close, row.volume)
        if (any(not isinstance(value, Decimal) or not value.is_finite() for value in values)
                or min(values[:4]) <= 0 or row.volume < 0
                or row.low > min(row.open, row.close) or row.high < max(row.open, row.close)):
            raise ValueError('invalid exit OHLCV')
        previous = row.open_time
    if now - rows[-1].open_time > maximum_age:
        raise ValueError('stale exit candles')
    return rows


def run_with_exit_data_fallback(executor, public, pair, *, live=False, now=None):
    """Only data acquisition is retried; never retry an order-capable run_once."""
    now = now or datetime.now(UTC)
    reader, blockers = executor.reader, executor.entry_blockers
    degraded = False
    try:
        rows = reader.read_candles(pair, limit=120)
        validate_exit_candles(rows, pair, now, executor.min_candles, executor.max_candle_age)
    except Exception:  # Data failure only; no order has been attempted.
        degraded = True
        try:
            raw = public.get_klines(pair.replace('/', ''), interval='5', limit=121)
            rows = [CandleRow(pair=pair, symbol=row.symbol,
                open_time=datetime.fromtimestamp(row.start_ms/1000, UTC), open=row.open,
                high=row.high, low=row.low, close=row.close, volume=row.volume)
                for row in raw if datetime.fromtimestamp(row.start_ms/1000, UTC)+timedelta(minutes=5) <= now][-120:]
            validate_exit_candles(rows, pair, now, executor.min_candles, executor.max_candle_age)
        except Exception:
            # Preserve this blocker for all subsequent pairs in this cycle.
            blocker = 'exit_data_unavailable; new entries paused; position management requires recovery'
            executor.entry_blockers = tuple(dict.fromkeys((*blockers, blocker)))
            return ExecutorDecision('recovery_required', pair, (blocker,))
    try:
        executor.reader = SimpleNamespace(read_candles=lambda *args, **kwargs: rows)
        if degraded:
            executor.entry_blockers = (*blockers, 'exit_only_public_fallback; new entries paused')
        result = executor.run_once(pair, live=live, now=now)
        if degraded:
            return ExecutorDecision(result.decision, result.pair,
                (*result.reasons, 'exit_data_source=bybit_public_closed_5m; entry_disabled'), result.order)
        return result
    finally:
        executor.reader, executor.entry_blockers = reader, blockers
