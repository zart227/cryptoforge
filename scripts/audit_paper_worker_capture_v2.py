"""Read-only paper worker source audit, sealed until the original end."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.evidence_segments import canonical
from cryptoforge.paper_worker_capture_v2 import audit_worker_capture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected-registration-sha256', required=True)
    parser.add_argument('--expected-seal-sha256')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            output, root = args.output.absolute(), args.root.absolute()
            if output.resolve() != output or output == root or root in output.parents or output in root.parents:
                raise ValueError('new output must be outside worker sources')
            if output.exists():raise FileExistsError('worker audit output already exists')
        result = audit_worker_capture(args.root, expected_registration_sha256=args.expected_registration_sha256,
            expected_seal_sha256=args.expected_seal_sha256)
        if args.output is not None:publish_new(output, canonical(result)+b'\n')
        print(json.dumps(result));return 0
    except (OSError, ValueError, TypeError, KeyError, IndexError, ArithmeticError, sqlite3.Error):
        print(json.dumps(dict(status='paper_worker_capture_blocked', live_admission_granted=False)));return 1


if __name__ == '__main__':raise SystemExit(main())
