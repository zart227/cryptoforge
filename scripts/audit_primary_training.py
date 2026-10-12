"""Verify a primary artifact using its original local input snapshot, read-only."""
import argparse,json
from pathlib import Path
from cryptoforge.primary_training_audit import audit_primary_artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--sha256',help='Optional full artifact checksum from its registry receipt.')
    parser.add_argument('--allow-current-runtime-difference',action='store_true',
        help='Verify inputs and recomputed numbers while explicitly reporting source drift; never executes archived code.')
    args=parser.parse_args()
    try:report=audit_primary_artifact(args.artifact,expected_sha256=args.sha256,
        require_current_source=not args.allow_current_runtime_difference)
    except (ValueError,OSError,EOFError) as exc:parser.exit(2,f'primary_training_audit unavailable: {exc}\n')
    print(json.dumps({key:value for key,value in report.items() if key!='probability_diagnostics'},sort_keys=True))


if __name__=='__main__':main()
