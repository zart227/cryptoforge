"""Local, resumable archive of closed Bybit Spot candles."""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import time

from cryptoforge.market_data import BybitPublicClient, Candle, MarketDataError, interval_to_milliseconds
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.archive_quality import validate_candles


def download_archive(client: BybitPublicClient, symbol: str, interval: str,
                     start_ms: int, end_ms: int, directory: Path, *, pause: float = 0.2) -> dict:
    if start_ms >= end_ms or pause < 0 or not symbol.isalnum() or not symbol.endswith('USDT'):
        raise ValueError('invalid archive range, delay, or USDT symbol')
    if interval not in {"1", "5", "15", "60"}:
        raise ValueError("unsupported archive interval")
    step = interval_to_milliseconds(interval)
    path = directory / f'{symbol}-{interval}.json'
    directory.mkdir(parents=True, exist_ok=True)
    cached = json.loads(path.read_text()) if path.exists() else []
    validate_candles([row_to_candle(row) for row in cached],now_ms=int(time.time()*1000))
    if any(row['symbol'] != symbol or str(row['interval']) != interval for row in cached):
        raise ValueError('cached archive identity mismatch')
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
        if any(c.symbol != symbol or c.interval != interval for c in page):
            raise ValueError('Bybit page identity mismatch')
        closed_page = [c for c in page if start_ms <= c.start_ms and c.close_ms <= min(end_ms,int(time.time()*1000))]
        validate_candles(closed_page,now_ms=min(end_ms,int(time.time()*1000)))
        for candle in closed_page:
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
    selected_rows = [rows[k] for k in selected]
    quality = validate_candles([row_to_candle(row) for row in selected_rows],now_ms=min(end_ms,int(time.time()*1000)))
    first_expected=((start_ms+step-1)//step)*step
    expected_end=(end_ms//step)*step
    edges=[]
    if expected_count and not selected:
        edges=[{'start_ms':first_expected,'end_ms_exclusive':expected_end,'missing_candles':expected_count}]
    elif selected:
        if selected[0]>first_expected:
            edges.append({'start_ms':first_expected,'end_ms_exclusive':selected[0],
                          'missing_candles':(selected[0]-first_expected)//step})
        if selected[-1]+step<expected_end:
            edges.append({'start_ms':selected[-1]+step,'end_ms_exclusive':expected_end,
                          'missing_candles':(expected_end-selected[-1]-step)//step})
    quality['gap_ranges']=sorted(quality['gap_ranges']+edges,key=lambda g:g['start_ms'])
    if quality['gap_ranges']:
        quality['status']='gapped' if selected else 'empty'
    raw = json.dumps(selected_rows,sort_keys=True,separators=(',',':')).encode()
    digest = hashlib.sha256(raw).hexdigest()
    snapshot_dir = directory / 'snapshots'
    snapshot_dir.mkdir(exist_ok=True)
    snapshot_path = snapshot_dir / f'{symbol}-{interval}-{start_ms}-{end_ms}-{digest[:16]}.json'
    if snapshot_path.exists() and snapshot_path.read_bytes() != raw:
        raise ValueError('immutable snapshot checksum mismatch')
    if not snapshot_path.exists():
        snapshot_path.write_bytes(raw)
    report = {'source':'bybit_v5_spot_kline','downloaded_at':datetime.now(UTC).isoformat(),
            'requested_start_ms':start_ms,'requested_end_ms_exclusive':end_ms,
            'dataset_id':f'{symbol}-{interval}-{digest[:16]}','sha256':digest,
            'snapshot_path':str(snapshot_path.resolve()),'quality':quality,
            'transformation_version':'raw-ohlcv-v1',
            'symbol':symbol,'interval':interval,'candles':len(selected),
            'expected_candles':expected_count,'missing_candles':expected_count-len(selected),
            'first_ms':selected[0] if selected else None,'last_ms':selected[-1] if selected else None,
            'path':str(path.resolve())}
    manifest_path = snapshot_path.with_suffix('.manifest.json')
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(report,indent=2))
    report['manifest_path'] = str(manifest_path.resolve())
    return report


class ArchiveReader:
    def __init__(self, directory: Path, *, protocol: dict | None = None):
        self.directory = directory
        self.protocol = protocol

    def read_candles(self, pair: str, *, timeframe: str = '5m', limit: int = 120) -> list[CandleRow]:
        if timeframe not in {'1m','5m','15m','1h'} or limit <= 0:
            raise ValueError('unsupported timeframe or limit')
        symbol = pair.replace('/','')
        if not symbol.isalnum() or not symbol.endswith('USDT'):
            raise ValueError('invalid pair')
        interval = {'1m':'1','5m':'5','15m':'15','1h':'60'}[timeframe]
        rows = json.loads((self.directory/f'{symbol}-{interval}.json').read_text())[-limit:]
        if any(row['symbol'] != symbol or str(row['interval']) != interval for row in rows):
            raise ValueError('archive identity mismatch')
        validate_candles([row_to_candle(row) for row in rows],now_ms=int(time.time()*1000))
        candles = [CandleRow(pair,symbol,datetime.fromtimestamp(int(r['start_ms'])/1000,UTC),
                             *(Decimal(r[key]) for key in ('open','high','low','close','volume')))
                   for r in rows]
        step = interval_to_milliseconds(interval)/1000
        if any((b.open_time-a.open_time).total_seconds() != step for a,b in zip(candles,candles[1:])):
            raise ValueError(f'{pair}: archive contains gaps; refusing training across missing candles')
        if self.protocol is not None:
            from cryptoforge.research_protocol import assert_development_range
            dataset = next((d for d in self.protocol['datasets'] if d['pair'] == pair), None)
            source = self.directory / f'{symbol}-{interval}.json'
            if dataset is None or source.resolve() != Path(dataset['path']).resolve():
                raise ValueError('dataset not part of frozen universe/source')
            if candles:
                assert_development_range(self.protocol,candles[0].open_time,candles[-1].open_time)
        return candles


def row_to_candle(row: dict) -> Candle:
    return Candle(str(row['symbol']),str(row['interval']),int(row['start_ms']),
                  *(Decimal(str(row[key])) for key in ('open','high','low','close','volume','turnover')))
