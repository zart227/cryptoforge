"""Inspect one incomplete feeder cycle without invoking it or changing files."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cryptoforge.feeder_incomplete_inspection import inspect_incomplete_feeder


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--registration-sha256', required=True)
    p.add_argument('--cycle', required=True)
    args = p.parse_args()
    ref = dict(root=str(args.root.absolute()), manifest_sha256=args.manifest_sha256,
               registration_sha256=args.registration_sha256)
    print(json.dumps(inspect_incomplete_feeder(ref, args.cycle), sort_keys=True))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Incomplete feeder inspection blocked: ' + type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
