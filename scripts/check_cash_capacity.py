"""Metadata-only short/long cash capacity estimate; never executes a study."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.cash_capacity_preflight import capacity_preflight
from cryptoforge.local_source_provenance import canonical,parse,read_file

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--requested-start');p.add_argument('--requested-end');p.add_argument('--output',type=Path)
    p.add_argument('--require-capacity',action='store_true')
    args=p.parse_args(argv);reference=parse(read_file(args.reference,maximum=4096))
    result=capacity_preflight(reference,requested_start=args.requested_start,requested_end=args.requested_end)
    raw=canonical(result)+b'\n'
    if args.output:
        path=args.output.absolute();root=Path(reference['root']).absolute()
        if path.resolve()!=path or root==path or root in path.parents:raise ValueError('capacity output must be new and outside original evidence')
        with path.open('xb') as stream:stream.write(raw)
        path.chmod(0o600)
    sys.stdout.buffer.write(raw)
    return 2 if args.require_capacity and not result['count_and_budget_capacity_pass'] else 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Cash capacity preflight blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
