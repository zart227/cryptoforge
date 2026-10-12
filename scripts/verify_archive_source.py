"""Read-only archive quality checks and comparison with public Bybit data."""
from dataclasses import asdict
from datetime import UTC,datetime
import json
from pathlib import Path
import resource
import shutil
import time

from cryptoforge.archive import row_to_candle
from cryptoforge.archive_quality import validate_candles,aggregate_candles
from cryptoforge.market_data import BybitPublicClient


def main():
    client=BybitPublicClient(timeout=20)
    now=int(time.time()*1000)
    checks=[]
    begin=time.monotonic()
    for symbol in ['BTCUSDT','ETHUSDT']:
        file=Path('.local/archive')/f'{symbol}-5.json'
        rows=[row_to_candle(r) for r in json.loads(file.read_text())]
        quality=validate_candles(rows,now_ms=now)
        sample_checks=[]
        for index in (0,len(rows)//2,len(rows)-3):
            expected=rows[index:index+3]
            actual=client.get_klines(symbol,interval='5',limit=3,
                                     start_ms=expected[0].start_ms,end_ms=expected[-1].close_ms-1)
            assert actual==expected, f'{symbol}: source sample mismatch at {index}'
            sample_checks.append({'start_ms':expected[0].start_ms,'candles':len(expected),'match':True})
        minute_file=Path('.local/archive-stage1')/f'{symbol}-1.json'
        minutes=[row_to_candle(r) for r in json.loads(minute_file.read_text())]
        validate_candles(minutes,now_ms=now)
        five=aggregate_candles(minutes,'5',now_ms=now)
        hour=aggregate_candles(five,'60',now_ms=now)
        direct5=client.get_klines(symbol,interval='5',limit=1000,start_ms=minutes[0].start_ms,end_ms=minutes[-1].close_ms-1)
        direct60=client.get_klines(symbol,interval='60',limit=1000,start_ms=minutes[0].start_ms,end_ms=minutes[-1].close_ms-1)
        assert five==direct5, f'{symbol}: minute aggregation mismatch'
        assert hour==direct60, f'{symbol}: hour aggregation mismatch'
        checks.append({'symbol':symbol,'quality':quality,'source_checks':sample_checks,
                       'minute_candles':len(minutes),'aggregate_5m':len(five),'aggregate_1h':len(hour),
                       'aggregation_exact_match':True})
    # Current online instrument info is a snapshot, not historical membership.
    instruments={i['symbol']:i for i in client._get_json('/v5/market/instruments-info',{'category':'spot'})['result']['list']}
    tickers={t.symbol:t for t in client.get_tickers()}
    requested=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','LTCUSDT','DOTUSDT']
    universe=[]
    for symbol in requested:
        info=instruments.get(symbol)
        ticker=tickers.get(symbol)
        universe.append({'symbol':symbol,'observed_at':datetime.now(UTC).isoformat(),
                         'online_specification':info,'turnover_24h':str(ticker.turnover_24h) if ticker else None,
                         'historical_listings_delistings_spread_rules':'unavailable_from_current_snapshot',
                         'eligible_for_pilot':bool(info and info.get('status')=='Trading' and ticker)})
    report={'checks':checks,'universe_current_snapshot':universe,
            'bias_warning':'present-day selection cannot establish a point-in-time historical universe',
            'measurement':{'wall_seconds':round(time.monotonic()-begin,3),
                           'process_peak_rss_mb':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2),
                           'free_disk_mb':round(shutil.disk_usage('.').free/1024**2,2)},
            'history_expansion_status':'not_downloaded_12_months', 'live_eligible':False}
    output=Path('.local/state/archive-quality-source.json');output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2))
    print(json.dumps({'checks':checks,'eligible_pilot_pairs':sum(u['eligible_for_pilot'] for u in universe),
                      'measurement':report['measurement']}))


if __name__=='__main__':
    main()
