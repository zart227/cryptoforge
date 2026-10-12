"""Stream long-range quality, source samples and causal fixed-basket membership."""
import argparse
from datetime import datetime,UTC
import json
from pathlib import Path

from cryptoforge.archive_universe import daily_membership
from cryptoforge.market_data import BybitPublicClient,interval_to_milliseconds
from cryptoforge.sqlite_archive import SQLiteArchive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default='.local/archive-stage1/history.sqlite')
    parser.add_argument('--output',default='.local/state/long-archive-quality.json')
    parser.add_argument('--reuse-report',action='append',default=[])
    args=parser.parse_args()
    database=Path(args.database);directory=database.parent
    progress=directory/(database.stem+'-download-progress.json')
    if not progress.exists():progress=directory/'long-download-progress.json'
    download=json.loads(progress.read_text())
    archive=SQLiteArchive(database);client=BybitPublicClient(timeout=20,max_retries=3)
    output=Path(args.output)
    previous=json.loads(output.read_text()) if output.exists() else {}
    reusable=[json.loads(Path(path).read_text()) for path in args.reuse_report]+[previous]
    prior_checks={c['symbol']:c for report in reusable for c in report.get('checks',[])}
    prior_membership={}
    for report in reusable:
        for symbol in {row['symbol'] for row in report.get('daily_membership',[])}:
            prior_membership[symbol]=[row for row in report['daily_membership'] if row['symbol']==symbol]
    checks=[];membership=[]
    try:
        for manifest in download['reports']:
            symbol=manifest['symbol'];interval=manifest['interval']
            start=manifest['requested_start_ms'];end=manifest['requested_end_ms_exclusive']
            current=archive.report(symbol,interval,start,end)
            assert current['sha256']==manifest['sha256'] and current['status']=='valid'
            cached=prior_checks.get(symbol)
            if cached and cached['sha256']==current['sha256']:
                checks.append(cached)
                membership.extend(prior_membership.get(symbol,[]))
                continue
            step=interval_to_milliseconds(interval)
            samples=[]
            for point in (current['first_ms'],current['first_ms']+(current['candles']//2)*step,current['last_ms']-2*step):
                expected=list(archive.rows(symbol,interval,point,point+3*step))
                actual=client.get_klines(symbol,interval=interval,limit=3,start_ms=point,end_ms=point+3*step-1)
                assert expected==actual,f'{symbol}: source mismatch at {point}'
                samples.append({'start_ms':point,'candles':3,'match':True})
            dates=daily_membership(archive.rows(symbol,interval,start,end))
            membership.extend(dates)
            checks.append({'symbol':symbol,'candles':current['candles'],'missing':current['missing_candles'],
                           'sha256':current['sha256'],'source_checks':samples,'observed_complete_days':len(dates)})
            print(json.dumps({'symbol':symbol,'quality':'valid','source_samples_matched':3}),flush=True)
    finally:
        archive.close()
    snapshot=json.loads(Path('.local/state/archive-quality-source.json').read_text())['universe_current_snapshot']
    report={'verified_at':datetime.now(UTC).isoformat(),'checks':checks,'daily_membership':membership,
            'instrument_observations':snapshot,'historical_metadata_gaps':['delisted_or_uncollected_symbols','instrument_rules_before_observed_at','historical_bid_ask_spread'],
            'scope':'dated_historical_basket_partial' if database.stem.startswith('historical-universe-') else 'fixed_survivor_basket_only','market_wide_profitability_claims_allowed':False,
            'live_eligible':False,'all_requested_pairs_complete':bool(checks) and len(checks)==len(download['reports']) and not download['failures']}
    dest=output;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,indent=2))
    print(json.dumps({'verified_pairs':len(checks),'candles':sum(c['candles'] for c in checks),'daily_records':len(membership),
                      'all_requested_pairs_complete':report['all_requested_pairs_complete']}))


if __name__=='__main__':
    main()
