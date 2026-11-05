"""Bounded foreground reference coordinator; never a live trading service."""
import argparse
import json
from pathlib import Path
import sys
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptoforge.local_source_provenance import read_file, parse, stamp
from cryptoforge.reference_coordinator import ReferenceCoordinator


def _reference(path):
    value = parse(read_file(path, maximum=1024*1024))
    return value.get('reference', value)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create')
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--pair', action='append', default=[])
    create.add_argument('--artifact-file', type=Path)
    create.add_argument('--start')
    create.add_argument('--end')
    create.add_argument('--diagnostic-input-consumers', action='store_true')
    for name in ('step', 'run', 'audit', 'recover'):
        command = sub.add_parser(name)
        command.add_argument('--reference-file', type=Path, required=True)
        if name == 'run':
            command.add_argument('--steps', type=int, required=True)
            command.add_argument('--seconds', type=int, required=True)
    args = p.parse_args(argv)
    if args.command == 'create':
        obj = ReferenceCoordinator.create(args.output, pairs=args.pair,
            artifact_raw=read_file(args.artifact_file, maximum=65536) if args.artifact_file else None,
            start=stamp(args.start) if args.start else None, end=stamp(args.end) if args.end else None,
            diagnostic_consumers=args.diagnostic_input_consumers)
        result = obj.receipt()
    elif args.command == 'recover':
        result = ReferenceCoordinator.recover(_reference(args.reference_file))
    else:
        obj = ReferenceCoordinator.open(_reference(args.reference_file))
        if args.command == 'audit':
            result = obj.audit()
        elif args.command == 'step':
            result = obj.step()
        else:
            policy = obj.policy
            if not 1 <= args.steps <= policy.maximum_steps or not 1 <= args.seconds <= policy.maximum_run_seconds:
                raise ValueError('run bounds exceed frozen coordinator policy')
            started = monotonic()
            count = 0
            # Bounds govern admission of another pass. Each component operation has
            # its own frozen timeout; an in-flight operation is never killed here.
            while count < args.steps and monotonic()-started < args.seconds:
                result = obj.step()
                count += 1
                print(json.dumps(dict(result, run_step=count), sort_keys=True), flush=True)
                remaining = args.seconds-(monotonic()-started)
                if count < args.steps and remaining > 0:
                    sleep(min(policy.minimum_step_seconds, remaining))
            return 0
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Reference coordinator failed: '+type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
