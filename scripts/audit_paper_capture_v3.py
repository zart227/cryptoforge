"""Read-only source audit for NEW v3 captures; sealed until the registered end."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.paper_capture_v3 import audit_segmented_capture
from cryptoforge.paper_valuation_capture import canonical


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
                raise ValueError('new output must be outside v3 sources')
            if output.exists():
                raise FileExistsError('v3 audit output already exists')
        result = audit_segmented_capture(args.root, expected_registration_sha256=args.expected_registration_sha256,
                                          expected_seal_sha256=args.expected_seal_sha256)
        if args.output is not None:
            publish_new(output, canonical(result)+b'\n')
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, IndexError, ArithmeticError, sqlite3.Error):
        print(json.dumps(dict(status='segmented_paper_capture_blocked', live_admission_granted=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
