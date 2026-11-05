"""Register, inspect or explicitly run a short isolated paired paper rehearsal."""
import argparse
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from cryptoforge.local_source_provenance import canonical,parse,read_file
from cryptoforge.paired_cash_rehearsal import PairedCashRehearsal
from database_backend import read_env

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('register');s.add_argument('--root',required=True,type=Path);s.add_argument('--spec',required=True,type=Path)
    for name in ('inspect','run'):
        s=sub.add_parser(name);s.add_argument('--reference',required=True,type=Path)
    args=p.parse_args(argv)
    if args.command=='register':
        spec=parse(read_file(args.spec,maximum=65536));obj=PairedCashRehearsal.create(args.root,**spec,backend_env=dict(os.environ,**read_env(ROOT/'.env')))
        value=obj.inspect()
    else:
        obj=PairedCashRehearsal.open(parse(read_file(args.reference,maximum=4096)))
        value=obj.run() if args.command=='run' else obj.inspect()
    sys.stdout.buffer.write(canonical(value)+b'\n');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Paired cash rehearsal blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
