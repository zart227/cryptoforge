"""Register, inspect or explicitly step/run an isolated checkpointed paper coordinator."""
import argparse
from pathlib import Path
import os
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from cryptoforge.paired_cached_coordinator import PairedCachedCoordinator,PairedCoordinatorPolicy
from cryptoforge.local_source_provenance import canonical,parse,read_file
from database_backend import read_env

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('register');s.add_argument('--root',type=Path,required=True);s.add_argument('--spec',type=Path,required=True)
    for name in ('inspect','inspect-known','step','run','recover','audit'):
        s=sub.add_parser(name);s.add_argument('--reference',type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=='register':
        spec=parse(read_file(args.spec,maximum=65536))
        if 'policy' in spec:spec['policy']=PairedCoordinatorPolicy(**spec['policy'])
        obj=PairedCachedCoordinator.create(args.root,**spec,backend_env=dict(os.environ,**read_env(ROOT/'.env')))
        value=obj.inspect()
    else:
        reference=parse(read_file(args.reference,maximum=4096))
        if args.command=='recover':value=PairedCachedCoordinator.recover(reference)
        elif args.command=='inspect-known':value=PairedCachedCoordinator.inspect_reference(reference)
        else:
            obj=PairedCachedCoordinator.open(reference)
            value=obj.step() if args.command=='step' else obj.run() if args.command=='run' else obj.audit() if args.command=='audit' else obj.inspect()
    sys.stdout.buffer.write(canonical(value)+b'\n');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Cached paired coordinator blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
