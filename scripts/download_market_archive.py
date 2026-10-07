from __future__ import annotations
import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from cryptoforge.archive import download_archive
from cryptoforge.market_data import BybitPublicClient


def main():
    parser = argparse.ArgumentParser(description='Download closed historical Bybit Spot candles locally.')
    parser.add_argument('--pair', action='append', required=True)
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--interval', choices=['5','15','60'], default='5')
    parser.add_argument('--directory', type=Path, default=Path('.local/archive'))
    args = parser.parse_args()
    if not 1 <= args.days <= 730:
        parser.error('days must be between 1 and 730')
    end = datetime.now(UTC)
    start = end-timedelta(days=args.days)
    reports = []
    for pair in args.pair:
        report = download_archive(BybitPublicClient(timeout=20),pair.replace('/',''),args.interval,
                                  int(start.timestamp()*1000),int(end.timestamp()*1000),args.directory)
        reports.append(report)
        print(json.dumps(report),flush=True)
    (args.directory/'download-manifest.json').write_text(json.dumps(reports,indent=2))
    return 0 if all(r['candles'] for r in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
