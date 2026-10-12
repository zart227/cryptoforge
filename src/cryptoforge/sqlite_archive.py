"""Streaming decimal-preserving historical cache with resumable page commits."""
from datetime import UTC,datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time

from cryptoforge.archive_quality import validate_candles
from cryptoforge.market_data import Candle,interval_to_milliseconds,MarketDataError
from cryptoforge.supabase_executor import CandleRow

SCHEMA='''CREATE TABLE IF NOT EXISTS candles (
 symbol TEXT NOT NULL, interval TEXT NOT NULL, start_ms INTEGER NOT NULL,
 open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL,
 volume TEXT NOT NULL, turnover TEXT NOT NULL,
 PRIMARY KEY(symbol,interval,start_ms)) WITHOUT ROWID'''


def _candle(row):
    return Candle(row[0],row[1],row[2],*(Decimal(v) for v in row[3:]))


class SQLiteArchive:
    def __init__(self,path: Path):
        self.path=path
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    def rows(self,symbol,interval,start_ms,end_ms):
        cursor=self.db.execute('SELECT * FROM candles WHERE symbol=? AND interval=? AND start_ms>=? AND start_ms<? ORDER BY start_ms',
                               (symbol,interval,start_ms,end_ms))
        for row in cursor:
            yield _candle(row)

    def report(self,symbol,interval,start_ms,end_ms):
        step=interval_to_milliseconds(interval)
        first_expected=((start_ms+step-1)//step)*step
        end=(end_ms//step)*step
        expected=first_expected;count=0;gaps=[];digest=hashlib.sha256()
        first=last=None
        for candle in self.rows(symbol,interval,first_expected,end):
            validate_candles([candle],now_ms=end_ms)
            if candle.start_ms>expected:
                gaps.append({'start_ms':expected,'end_ms_exclusive':candle.start_ms,'missing_candles':(candle.start_ms-expected)//step})
            expected=candle.close_ms;count+=1
            first=candle.start_ms if first is None else first;last=candle.start_ms
            values=[candle.symbol,candle.interval,candle.start_ms,*[str(v) for v in (candle.open,candle.high,candle.low,candle.close,candle.volume,candle.turnover)]]
            digest.update((json.dumps(values,separators=(',',':'))+'\n').encode())
        if expected<end:
            gaps.append({'start_ms':expected,'end_ms_exclusive':end,'missing_candles':(end-expected)//step})
        return {'symbol':symbol,'interval':interval,'requested_start_ms':start_ms,'requested_end_ms_exclusive':end_ms,
                'candles':count,'first_ms':first,'last_ms':last,'gaps':gaps,
                'expected_candles':max(0,(end-first_expected)//step),
                'missing_candles':sum(g['missing_candles'] for g in gaps),
                'sha256':digest.hexdigest(),'checksum_scheme':'sha256-canonical-row-json-lines-v1',
                'source':'bybit_v5_spot_kline','format':'sqlite-decimal-text-v1','path':str(self.path.resolve()),
                'dataset_id':f'{symbol}-{interval}-{digest.hexdigest()[:16]}',
                'status':'valid' if count and not gaps else 'incomplete',
                'cache_mutable':True,'training_requires_range_checksum_verification':True}

    def download(self,client,symbol,interval,start_ms,end_ms,*,pause=0.2,progress=None):
        if interval not in {'1','5','15','60'} or not symbol.isalnum() or not symbol.endswith('USDT') or start_ms>=end_ms or pause<0:
            raise ValueError('invalid history request')
        if end_ms>int(time.time()*1000):
            raise ValueError('future ranges are not available')
        step=interval_to_milliseconds(interval)
        cursor=(end_ms//step)*step-1
        aligned_start=((start_ms+step-1)//step)*step
        pages=0
        while cursor>=aligned_start:
            if shutil.disk_usage(self.path.parent).free<2*1024**3:
                raise ValueError('disk reserve below 2 GiB; resumable download paused')
            floor=max(aligned_start,(cursor//step-999)*step)
            expected_count=(cursor//step-floor//step)+1
            existing=self.db.execute('SELECT count(*) FROM candles WHERE symbol=? AND interval=? AND start_ms>=? AND start_ms<=?',
                                     (symbol,interval,floor,cursor)).fetchone()[0]
            if existing==expected_count:
                cursor=floor-1
                continue
            page=client.get_klines(symbol,interval=interval,limit=1000,start_ms=aligned_start,end_ms=cursor)
            if not page:
                break
            if any(c.symbol!=symbol or c.interval!=interval for c in page):
                raise ValueError('history page identity mismatch')
            earliest=min(c.start_ms for c in page)
            if earliest>cursor:
                raise MarketDataError('history pagination did not advance')
            closed=[c for c in page if aligned_start<=c.start_ms and c.close_ms<=end_ms]
            validate_candles(closed,now_ms=end_ms)
            records=[(c.symbol,c.interval,c.start_ms,*[str(v) for v in (c.open,c.high,c.low,c.close,c.volume,c.turnover)]) for c in closed]
            # Successful pages are durable even if the following API call fails.
            with self.db:
                self.db.executemany('INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?,?)',records)
            pages+=1;cursor=earliest-1
            if progress and pages%10==0:
                progress({'symbol':symbol,'pages':pages,'oldest_loaded_ms':earliest})
            if pause: time.sleep(pause)
        report=self.report(symbol,interval,start_ms,end_ms)
        manifest_dir=self.path.parent/'manifests'/self.path.stem;manifest_dir.mkdir(parents=True,exist_ok=True)
        filename=manifest_dir/f'{symbol}-{interval}-{start_ms}-{end_ms}-{report["sha256"][:16]}.json'
        if not filename.exists():
            filename.write_text(json.dumps({**report,'captured_at':datetime.now(UTC).isoformat()},indent=2))
        report['manifest_path']=str(filename.resolve())
        return report

    def continuous_segments(self,manifest: dict):
        """Expose valid subranges without filling gaps or pretending full coverage."""
        ranges=[];start=None;previous_end=None
        for candle in self.rows(manifest['symbol'],manifest['interval'],manifest['requested_start_ms'],manifest['requested_end_ms_exclusive']):
            validate_candles([candle],now_ms=manifest['requested_end_ms_exclusive'])
            if previous_end is not None and candle.start_ms!=previous_end:
                ranges.append((start,previous_end));start=None
            if start is None:start=candle.start_ms
            previous_end=candle.close_ms
        if start is not None:ranges.append((start,previous_end))
        return [{**self.report(manifest['symbol'],manifest['interval'],begin,end),
                 'parent_dataset_id':manifest['dataset_id'],'parent_coverage_status':manifest['status'],
                 'scope':'continuous_subrange_excluding_missing_candles'} for begin,end in ranges]

    def read_manifest(self,manifest: dict,*,limit: int):
        if limit<=0:
            raise ValueError('positive limit required')
        current=self.report(manifest['symbol'],manifest['interval'],manifest['requested_start_ms'],manifest['requested_end_ms_exclusive'])
        if current['sha256']!=manifest['sha256'] or current['status']!='valid':
            raise ValueError('incomplete or changed historical dataset')
        step=interval_to_milliseconds(manifest['interval'])
        start=max(manifest['first_ms'],manifest['last_ms']-(limit-1)*step)
        pair=manifest['symbol'][:-4]+'/USDT'
        return [CandleRow(pair,c.symbol,datetime.fromtimestamp(c.start_ms/1000,UTC),c.open,c.high,c.low,c.close,c.volume)
                for c in self.rows(manifest['symbol'],manifest['interval'],start,manifest['last_ms']+step)]
