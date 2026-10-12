"""Build a pre-study liquidity universe from a dated official historical baseline."""
from dataclasses import asdict
from datetime import datetime,UTC,timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import time

from cryptoforge.announcement_sources import article_tables
from cryptoforge.market_data import BybitPublicClient,MarketDataError
from cryptoforge.archive_quality import validate_candles
from cryptoforge.instrument_history import timestamp

AS_OF=datetime(2025,10,1,tzinfo=UTC)
START=int((AS_OF-timedelta(days=1)).timestamp()*1000);END=int(AS_OF.timestamp()*1000)
ROOT=Path('.local/archive-stage1/sources/historical-universe-probes')
OUTPUT=Path('.local/state/historical-universe-20251001.json')


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    source=Path('.local/archive-stage1/sources/minimum-jan2025.next.json')
    article=json.loads(source.read_text())['articleDetail']
    if timestamp(article['date'])>=AS_OF:raise ValueError('baseline was not published before the selection date')
    rows=article_tables(article)
    candidates=sorted({r[0] for r in rows if r and re.fullmatch(r'[A-Z0-9]+USDT',r[0])})
    previous=json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    results={r['symbol']:r for r in previous.get('results',[]) if r.get('status') in {'complete_prior_day','no_complete_prior_day'}}
    protocol={'as_of':AS_OF.isoformat(),'baseline_publication':article['date'],'candidate_pool':'dated_January_2025_official_Spot_rule_table',
              'candidate_symbols':candidates,'minimum_prior_turnover_usdt':'1000000','minimum_prior_range_fraction':'0.01',
              'maximum_selected_pairs':20,'ranking':'prior_day_turnover_only','current_universe_used':False,'future_returns_used':False}
    def persist():
        eligible=[r for r in results.values() if r.get('liquidity_eligible')]
        ranked=sorted(eligible,key=lambda r:(-Decimal(r['prior_day_turnover_usdt']),r['symbol']))[:20]
        OUTPUT.write_text(json.dumps({'protocol':protocol,'results':list(results.values()),'selected_symbols':[r['symbol'] for r in ranked],
            'coverage_status':'partial_historical_baseline_not_entire_exchange','historical_execution_rules_complete':False,
            'live_eligible':False},indent=2))
    client=BybitPublicClient(timeout=15,max_retries=2)
    for index,symbol in enumerate(candidates,1):
        if symbol in results:continue
        result={'symbol':symbol,'liquidity_eligible':False,'request_start_ms':START,'request_end_ms_exclusive':END}
        try:
            candles=client.get_klines(symbol,interval='60',limit=24,start_ms=START,end_ms=END-1)
            quality=validate_candles(candles,now_ms=END)
            complete=len(candles)==24 and candles[0].start_ms==START and candles[-1].close_ms==END and not quality['gap_ranges']
            raw=json.dumps({'query':{'category':'spot','symbol':symbol,'start':START,'end':END-1,'interval':'60'},
                            'candles':[asdict(c) for c in candles]},default=str,sort_keys=True).encode()
            digest=hashlib.sha256(raw).hexdigest();path=ROOT/(digest+'.json')
            if not path.exists():path.write_bytes(raw)
            result.update(status='complete_prior_day' if complete else 'no_complete_prior_day',
                          source_sha256=digest,snapshot_path=str(path.resolve()),candles=len(candles))
            if complete:
                turnover=sum((c.turnover for c in candles),Decimal(0))
                movement=(max(c.high for c in candles)-min(c.low for c in candles))/candles[-1].close
                result.update(prior_day_turnover_usdt=str(turnover),prior_day_range_fraction=str(movement),
                              liquidity_eligible=turnover>=Decimal('1000000') and movement>=Decimal('.01'))
        except (MarketDataError,ValueError) as exc:result.update(status='probe_unavailable',error=str(exc))
        results[symbol]=result;persist()
        if index%25==0:print(json.dumps({'processed':len(results),'total':len(candidates),'eligible':sum(r['liquidity_eligible'] for r in results.values())}),flush=True)
        time.sleep(.2)
    persist()
    print(json.dumps({'processed':len(results),'total':len(candidates),'selected':json.loads(OUTPUT.read_text())['selected_symbols']}))


if __name__=='__main__':main()
