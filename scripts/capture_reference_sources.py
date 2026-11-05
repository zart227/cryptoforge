"""Capture mandatory Bybit Spot sources into an isolated research ledger."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.local_source_provenance import parse,read_file,stamp
from cryptoforge.reference_source_ledger import ReferenceLedger,audit_reference_ledger


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('probe','create'):
        s=sub.add_parser(name);s.add_argument('--output',type=Path,required=True)
        s.add_argument('--pair',action='append',default=[]);s.add_argument('--artifact-file',type=Path)
        if name=='create':s.add_argument('--start',required=True);s.add_argument('--end',required=True)
    for name in ('poll','audit','forecast'):
        s=sub.add_parser(name);s.add_argument('--reference-file',type=Path,required=True)
        if name=='forecast':s.add_argument('--pair',required=True)
    args=p.parse_args(argv)
    if args.command in ('probe','create'):
        raw=read_file(args.artifact_file,maximum=65536) if args.artifact_file else None
        ledger=ReferenceLedger.create(args.output,pairs=args.pair,artifact_raw=raw,
            start=stamp(args.start) if args.command=='create' else None,
            end=stamp(args.end) if args.command=='create' else None)
        result=ledger.poll() if args.command=='probe' else ledger.receipt()
    else:
        value=parse(read_file(args.reference_file,maximum=65536));ref=value.get('reference',value)
        if args.command=='audit':result=audit_reference_ledger(ref)
        else:
            ledger=ReferenceLedger.open(ref)
            if args.command=='poll':result=ledger.poll()
            else:result=dict(forecast=ledger.forecast(args.pair),**ledger.receipt())
    print(json.dumps(result,sort_keys=True));return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Reference source capture failed: '+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
