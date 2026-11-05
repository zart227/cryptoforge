"""Read-only indexed cash application metadata/full audit, sealed by original end."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.cash_application_v2 import SegmentedCashApplicationV2
from cryptoforge.local_source_provenance import canonical,parse,read_file

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',required=True,type=Path)
    args=p.parse_args(argv);result=SegmentedCashApplicationV2.audit_reference(parse(read_file(args.reference,maximum=4096)))
    sys.stdout.buffer.write(canonical(result)+b'\n');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('V2 cash receipt audit blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
