#!/usr/bin/env python3
"""Emit a new immutable-by-convention read-only forecast inventory receipt."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from cryptoforge.forecast_retention_preflight import assess_retention


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--cutoff', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).absolute()
    if output.resolve() != output or not output.parent.is_dir():
        raise ValueError('canonical output path in an existing directory required')
    report = assess_retention(args.manifest, args.manifest_sha256, as_of=args.as_of, cutoff=args.cutoff)
    manifest_path = Path(args.manifest).absolute()
    # Never add files alongside the source or the sealed standalone snapshot.
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.manifest_sha256:
        raise ValueError('manifest changed before receipt creation')
    manifest = json.loads(raw)
    if output.parent in (manifest_path.parent, Path(manifest['source']).parent):
        raise ValueError('separate receipt directory required')
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2, ensure_ascii=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'output': str(output), 'buckets': report['buckets'], 'split_readiness': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
