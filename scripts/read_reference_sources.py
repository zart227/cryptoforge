"""Freeze or inspect shared reference inputs without producing trading decisions."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from cryptoforge.local_source_provenance import parse, read_file
from cryptoforge.reference_source_reader import (
    ReferenceMarketReader, ROLES, MAX_ORIGINAL_ARTIFACT_BYTES, audit_frame, capture_frame,
    freeze_reader, prepare_inference_artifact, audit_inference_artifact,
)


def descriptor(path):
    value = parse(read_file(path, maximum=65536))
    return value.get('reference', value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare-artifact')
    prepare.add_argument('--artifact-file', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    check_artifact = sub.add_parser('audit-artifact')
    check_artifact.add_argument('--artifact-reference-file', type=Path, required=True)
    for name in ('register', 'capture'):
        command = sub.add_parser(name)
        command.add_argument('--source-reference-file', type=Path, required=True)
        command.add_argument('--output', type=Path, required=True)
        if name == 'capture':
            command.add_argument('--reader-reference-file', type=Path)
    for name in ('audit', 'inspect'):
        command = sub.add_parser(name)
        command.add_argument('--frame-reference-file', type=Path, required=True)
        command.add_argument('--reader-reference-file', type=Path)
        if name == 'inspect':
            command.add_argument('--role', choices=ROLES, required=True)
            command.add_argument('--pair')
    args = parser.parse_args(argv)
    reader = descriptor(args.reader_reference_file) if getattr(args, 'reader_reference_file', None) else None
    if args.command == 'prepare-artifact':
        result = prepare_inference_artifact(args.output, read_file(args.artifact_file, maximum=MAX_ORIGINAL_ARTIFACT_BYTES))
    elif args.command == 'audit-artifact':
        result = audit_inference_artifact(descriptor(args.artifact_reference_file))
    elif args.command == 'register':
        result = freeze_reader(args.output, descriptor(args.source_reference_file))
    elif args.command == 'capture':
        result = capture_frame(args.output, descriptor(args.source_reference_file), reader_reference=reader)
    elif args.command == 'audit':
        result = audit_frame(descriptor(args.frame_reference_file), reader_reference=reader)
    else:
        source = ReferenceMarketReader.open(descriptor(args.frame_reference_file), role=args.role, reader_reference=reader)
        result = dict(status=source.status(), price_forecasts=source.original_forecasts())
        if args.pair:
            rows = source.read_candles(args.pair)
            result['candles'] = [dict(pair=r.pair, open_time=r.open_time.isoformat(), close=str(r.close),
                observed_at=r.cache_observed_at.isoformat()) for r in rows]
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Reference reader failed: ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
