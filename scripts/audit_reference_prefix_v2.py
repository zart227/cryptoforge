"""Read-only independent replay of a new incremental cash source index."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.reference_prefix_v2 import ReferencePrefixV2
from cryptoforge.local_source_provenance import canonical,parse,read_file

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--scratch-parent',required=True,type=Path);args=p.parse_args(argv)
    obj=ReferencePrefixV2.open(parse(read_file(args.reference,maximum=4096)))
    sys.stdout.buffer.write(canonical(obj.audit(scratch_parent=args.scratch_parent))+b'\n');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Incremental reference audit blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
