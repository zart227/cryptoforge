"""Local, resumable archive of closed Bybit Spot candles."""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import time

from cryptoforge.market_data import BybitPublicClient, Candle, MarketDataError, interval_to_milliseconds
from cryptoforge.supabase_executor import CandleRow


def download_archive(client: BybitPublicClient, symbol: str, interval: str,
                     start_ms: int, end_ms: int, directory: Path, *, pause: float = 0.2) -> dict:
    if start_ms >= end_ms or pause < 0 or not symbol.isalnum() or not symbol.endswith('USDT'):
        raise ValueError('invalid archive range, delay, or USDT symbol')
    step = interval_to_milliseconds(interval)
    path = directory / f'{symbol}-{interval}.json'
    directory.mkdir(parents=True, exist_ok=True)
    cached = json.loads(path.read_text()) if path.exists() else []
    rows = {int(row['start_ms']):row for row in cached}
    cursor = end_ms-1
    while cursor >= start_ms:
        # Skip completely cached pages on repeated runs; gaps are fetched again.
        floor = max(((start_ms+step-1)//step)*step, (cursor//step-999)*step)
        expected = range(floor,(cursor//step)*step+1,step)
        if all(timestamp in rows for timestamp in expected):
            cursor = floor-1
            continue
        page = client.get_klines(symbol,interval=interval,limit=1000,start_ms=start_ms,end_ms=cursor)
        if not page:
            break
        earliest = min(c.start_ms for c in page)
        if earliest > cursor:
            raise MarketDataError('archive pagination did not advance')
        for candle in page:
            if start_ms <= candle.start_ms and candle.close_ms <= end_ms:
                rows[candle.start_ms] = {k:str(v) if isinstance(v,Decimal) else v
                                         for k,v in asdict(candle).items()}
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps([rows[k] for k in sorted(rows)]))
        temp.replace(path)
        cursor = earliest-1
        if pause:
            time.sleep(pause)
    selected = sorted(k for k in rows if start_ms <= k and k+step <= end_ms)
    expected_count = max(0,(end_ms//step)-((start_ms+step-1)//step))
    return {'symbol':symbol,'interval':interval,'candles':len(selected),
            'expected_candles':expected_count,'missing_candles':expected_count-len(selected),
            'first_ms':selected[0] if selected else None,'last_ms':selected[-1] if selected else None,
            'path':str(path.resolve())}


class ArchiveReader:
    def __init__(self, directory: Path):
        self.directory = directory

    def read_candles(self, pair: str, *, timeframe: str = '5m', limit: int = 120) -> list[CandleRow]:
        if timeframe not in {'5m','15m','1h'} or limit <= 0:
            raise ValueError('unsupported timeframe or limit')
        symbol = pair.replace('/','')
        if not symbol.isalnum() or not symbol.endswith('USDT'):
            raise ValueError('invalid pair')
        interval = {'5m':'5','15m':'15','1h':'60'}[timeframe]
        rows = json.loads((self.directory/f'{symbol}-{interval}.json').read_text())[-limit:]
        candles = [CandleRow(pair,symbol,datetime.fromtimestamp(int(r['start_ms'])/1000,UTC),
                             *(Decimal(r[key]) for key in ('open','high','low','close','volume')))
                   for r in rows]
        step = interval_to_milliseconds(interval)/1000
        if any((b.open_time-a.open_time).total_seconds() != step for a,b in zip(candles,candles[1:])):
            raise ValueError(f'{pair}: archive contains gaps; refusing training across missing candles')
        return candles
