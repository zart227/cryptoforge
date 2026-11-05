"""Sealed, bounded read-only cash/FIFO/valuation replay of v4 captures."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.evidence_segments import canonical
from cryptoforge.paper_streaming_replay import audit_streaming_paper


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--expected-registration-sha256',required=True)
    parser.add_argument('--expected-seal-sha256')
    parser.add_argument('--replay-root',type=Path)
    parser.add_argument('--expected-replay-registration-sha256')
    parser.add_argument('--scratch-parent',type=Path)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            output = args.output.absolute()
            if output.resolve() != output or output.exists():raise ValueError('new nonsymlink replay output required')
            for path in (args.root,args.replay_root):
                if path is not None:
                    root = path.absolute()
                    if output == root or root in output.parents or output in root.parents:
                        raise ValueError('replay output must be outside sources')
        result = audit_streaming_paper(args.root,expected_registration_sha256=args.expected_registration_sha256,
            expected_seal_sha256=args.expected_seal_sha256,replay_root=args.replay_root,
            expected_replay_registration_sha256=args.expected_replay_registration_sha256,scratch_parent=args.scratch_parent)
        if args.output is not None:publish_new(args.output,canonical(result)+b'\n')
        print(json.dumps(result));return 0
    except (OSError,ValueError,TypeError,KeyError,IndexError,ArithmeticError,sqlite3.Error):
        print(json.dumps(dict(status='streaming_paper_replay_blocked',live_admission_granted=False)));return 1


if __name__ == '__main__':raise SystemExit(main())
