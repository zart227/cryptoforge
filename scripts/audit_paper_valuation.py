"""Read-only audit of a NEW paper valuation capture, sealed until its end."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.paper_valuation_capture import audit_valuation_capture, canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--expected-protocol-sha256', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_valuation_capture(args.root, expected_protocol_sha256=args.expected_protocol_sha256)
        if args.output is not None:
            output, root = args.output.absolute(), args.root.absolute()
            if output.resolve() != output or output == root or root in output.parents or output in root.parents:
                raise ValueError('new audit output must be outside capture sources')
            publish_new(output, canonical(result) + b'\n')
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, sqlite3.Error):
        print(json.dumps(dict(status='paper_valuation_blocked', live_admission_granted=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
