"""Inspect known durable paper-result ack recovery; explicit --apply-paper-ack."""
import argparse
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from cryptoforge.cash_ack_recovery import recover_cash_ack
from cryptoforge.local_source_provenance import canonical,parse,read_file

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--known-reference',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--apply-paper-ack',action='store_true')
    args=parser.parse_args(argv)
    value=recover_cash_ack(parse(read_file(args.known_reference,maximum=4096)),args.output,apply=args.apply_paper_ack)
    sys.stdout.buffer.write(canonical(value)+b'\n');return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print('Paper acknowledgement recovery blocked: '+type(exc).__name__,file=sys.stderr);raise SystemExit(1)
