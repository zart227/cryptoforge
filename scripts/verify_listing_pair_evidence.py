"""Confirm a token listing's quote via historical Spot candles at the stated start."""
from dataclasses import asdict
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path
import time

from cryptoforge.market_data import BybitPublicClient,MarketDataError
from cryptoforge.archive_quality import validate_candles
from cryptoforge.instrument_history import timestamp


def main():
    queue=json.loads(Path('.local/state/historical-event-queue.json').read_text())
    output=Path('.local/state/listing-pair-evidence.json')
    previous=json.loads(output.read_text()) if output.exists() else {}
    results={r['url']:r for r in previous.get('results',[]) if r.get('pair_confirmed')}
    root=Path('.local/archive-stage1/sources/pair-evidence');root.mkdir(exist_ok=True)
    client=BybitPublicClient(timeout=20,max_retries=2)
    for record in queue['source_reviews']:
        if record['status']!='pending_listing_quote_pair_evidence' or record['url'] in results:continue
        symbol=record['token']+'USDT';effective=timestamp(record['effective_at_candidate'])
        start=int(effective.timestamp()*1000)
        result={'url':record['url'],'symbol':symbol,'effective_at':effective.isoformat(),
                'source':'Bybit_v5_market_kline_category_spot','requested_start_ms':start,
                'pair_confirmed':False,'evidence_scope':'first_hour_near_announced_listing_not_full_history'}
        try:
            candles=client.get_klines(symbol,interval='5',limit=12,start_ms=start,end_ms=start+3600000-1)
            validate_candles(candles,now_ms=start+3600000)
            confirmed=bool(candles and start<=candles[0].start_ms<=start+300000 and any(c.volume>0 for c in candles))
            payload={'query':{'category':'spot','symbol':symbol,'interval':'5','start':start,'end':start+3600000-1},
                     'candles':[asdict(c) for c in candles]}
            raw=json.dumps(payload,sort_keys=True,default=str).encode();digest=hashlib.sha256(raw).hexdigest()
            path=root/(digest+'.json')
            if not path.exists():path.write_bytes(raw)
            result.update(pair_confirmed=confirmed,source_sha256=digest,snapshot_path=str(path.resolve()),
                          candles=len(candles),first_ms=candles[0].start_ms if candles else None)
        except (MarketDataError,ValueError) as exc:result['error']=str(exc)
        results[record['url']]=result
        output.write_text(json.dumps({'captured_at':datetime.now(UTC).isoformat(),'results':list(results.values()),
                                      'events_admitted':0,'live_eligible':False},indent=2))
        print(json.dumps({'symbol':symbol,'pair_confirmed':result['pair_confirmed'],'candles':result.get('candles')}),flush=True)
        time.sleep(.2)


if __name__=='__main__':main()
