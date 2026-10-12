"""Audit a checksummed minute snapshot against frozen development five-minute data."""
import argparse
from datetime import datetime,UTC
import hashlib,json
from pathlib import Path
from cryptoforge.archive import ArchiveReader
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.intrabar_source_audit import compare_intrabar_source
from cryptoforge.research_protocol import prepare_research


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',required=True)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--sha256',required=True,help='SHA256 of exact mutable SYMBOL-1.json file bytes, distinct from canonical snapshot SHA')
    parser.add_argument('--maximum-minutes',type=int,default=1440)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if not 5<=args.maximum_minutes<=10080:parser.error('minute audit bound must be 5..10080')
    protocol=prepare_research()
    symbol=args.pair.replace('/','')
    if not symbol.isalnum() or not symbol.endswith('USDT'):parser.error('USDT market required')
    path=args.directory/(symbol+'-1.json')
    if path.stat().st_size>16*1024**2:parser.error('minute source exceeds bounded audit size')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=args.sha256:parser.error('minute source checksum mismatch')
    fine=ArchiveReader(args.directory).read_candles(args.pair,timeframe='1m',limit=args.maximum_minutes+1)
    if len(fine)>args.maximum_minutes:parser.error('minute source exceeds requested bound; use a separate slice')
    dataset=next((d for d in protocol['datasets'] if d['pair']==args.pair),None)
    if dataset is None:parser.error('pair outside frozen universe')
    coarse=ArchiveReader(Path(dataset['path']).parent,protocol=protocol).read_candles(args.pair,limit=1000000)
    report=compare_intrabar_source(fine,coarse,protocol=protocol,as_of=datetime.now(UTC))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:parser.error('minute source changed during audit')
    if hashlib.sha256(Path(dataset['path']).read_bytes()).hexdigest()!=dataset['sha256']:parser.error('frozen coarse source changed during audit')
    report.update(fine_sha256=digest,coarse_sha256=dataset['sha256'])
    write_json_report(args.output,report)
    print(json.dumps({key:report[key] for key in ('fine_candles','coarse_bars','source_consistency_pass')}))
    return 0 if report['source_consistency_pass'] else 1


if __name__=='__main__':raise SystemExit(main())
