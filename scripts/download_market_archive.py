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
    parser.add_argument('--interval', choices=['1','5','15','60'], default='5')
    parser.add_argument('--directory', type=Path, default=Path('.local/archive-stage1'))
    parser.add_argument('--start', help='Inclusive UTC ISO timestamp; use with --end.')
    parser.add_argument('--end', help='Exclusive UTC ISO timestamp; use with --start.')
    args = parser.parse_args()
    if not 1 <= args.days <= 730:
        parser.error('days must be between 1 and 730')
    if bool(args.start) != bool(args.end):
        parser.error('start and end must be supplied together')
    end = datetime.fromisoformat(args.end.replace('Z','+00:00')) if args.end else datetime.now(UTC)
    start = datetime.fromisoformat(args.start.replace('Z','+00:00')) if args.start else end-timedelta(days=args.days)
    if start.tzinfo is None or end.tzinfo is None or start>=end or end>datetime.now(UTC):
        parser.error('closed timezone-aware historical range required')
    protocol_path=Path('config/research-protocol-v1.json')
    if protocol_path.exists():
        for dataset in json.loads(protocol_path.read_text()).get('datasets',[]):
            if Path(dataset['path']).parent.resolve()==args.directory.resolve():
                parser.error('cannot modify a frozen archive; use a staging directory')
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
