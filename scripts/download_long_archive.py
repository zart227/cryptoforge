"""Stage-1 only: bounded memory download of a fixed historical Spot basket."""
import argparse
from datetime import datetime,UTC
import json
from pathlib import Path
import resource
import time

from cryptoforge.market_data import BybitPublicClient,MarketDataError
from cryptoforge.sqlite_archive import SQLiteArchive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--start',required=True)
    parser.add_argument('--end',required=True)
    parser.add_argument('--interval',choices=['1','5','15','60'],default='5')
    parser.add_argument('--database',type=Path,default=Path('.local/archive-stage1/history.sqlite'))
    args=parser.parse_args()
    start=datetime.fromisoformat(args.start.replace('Z','+00:00'));end=datetime.fromisoformat(args.end.replace('Z','+00:00'))
    if start.tzinfo is None or end.tzinfo is None or not start<end<=datetime.now(UTC):
        parser.error('closed timezone-aware historical range required')
    if (end-start).days>730: parser.error('maximum 730 days per requested range')
    archive=SQLiteArchive(args.database);reports=[];failures={};began=time.monotonic()
    client=BybitPublicClient(timeout=20,max_retries=3,retry_backoff_seconds=2)
    output=args.database.parent/(args.database.stem+'-download-progress.json')
    def progress(value): print(json.dumps(value),flush=True)
    try:
        for pair in dict.fromkeys(args.pair):
            try:
                report=archive.download(client,pair.replace('/',''),args.interval,int(start.timestamp()*1000),int(end.timestamp()*1000),progress=progress)
                reports.append(report)
                print(json.dumps({k:report[k] for k in ('symbol','candles','missing_candles','status','manifest_path')}),flush=True)
            except (MarketDataError,ValueError) as exc:
                failures[pair]=str(exc)
                print(json.dumps({'pair':pair,'paused_reason':str(exc)}),flush=True)
            output.write_text(json.dumps({'reports':reports,'failures':failures,
                 'requested_start':start.isoformat(),'requested_end':end.isoformat(),
                 'wall_seconds':time.monotonic()-began,'peak_rss_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                 'scope':'fixed_current_basket_development_not_point_in_time_universe','live_eligible':False},indent=2))
    finally:
        archive.close()
    return 0 if not failures and all(r['status']=='valid' for r in reports) else 1


if __name__=='__main__':
    raise SystemExit(main())
