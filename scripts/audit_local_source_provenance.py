"""Read-only local PostgreSQL provenance; no study/model/trading activation."""
import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from database_backend import read_env
from cryptoforge.local_source_observer import LocalPostgresObserver
from cryptoforge.local_source_provenance import (
    audit_observation, bound_contract, canonical, digest, freeze_contract,
    migration_snapshot, parse, publish_observation, read_file, stamp, validate_observation,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    def source_args(p):
        p.add_argument('--output', type=Path, required=True)
        p.add_argument('--migration-dir', type=Path, default=ROOT / '.local/database-transfer')
        p.add_argument('--pair', default='BTC/USDT')
        p.add_argument('--timeframe', default='5m')
        p.add_argument('--limit', type=int, default=120)
    source_args(sub.add_parser('probe'))
    capture = sub.add_parser('capture'); source_args(capture)
    audit = sub.add_parser('audit')
    audit.add_argument('--root', type=Path, required=True)
    audit.add_argument('--observation-sha256', required=True)
    audit.add_argument('--completion-sha256', required=True)
    for p in (capture, audit):
        p.add_argument('--contract-root', type=Path, required=p is capture)
        p.add_argument('--contract-sha256')
        p.add_argument('--registration-sha256')
    register = sub.add_parser('register')
    register.add_argument('--output', type=Path, required=True)
    register.add_argument('--probe-root', type=Path, required=True)
    register.add_argument('--observation-sha256', required=True)
    register.add_argument('--completion-sha256', required=True)
    register.add_argument('--study-sha256', required=True)
    register.add_argument('--pair', action='append', required=True)
    register.add_argument('--start', required=True)
    register.add_argument('--end', required=True)
    args = parser.parse_args(argv)
    reference = None
    if getattr(args, 'contract_root', None):
        reference = dict(root=str(args.contract_root), contract_sha256=args.contract_sha256,
                         registration_sha256=args.registration_sha256)
    if args.command == 'audit':
        result = audit_observation(args.root, expected_observation_sha256=args.observation_sha256,
                                   expected_completion_sha256=args.completion_sha256, contract=reference)
    else:
        env = {**os.environ, **read_env(ROOT / '.env')}
        if args.command == 'register':
            audit_observation(args.probe_root, expected_observation_sha256=args.observation_sha256,
                               expected_completion_sha256=args.completion_sha256)
            probe = parse(read_file(args.probe_root / 'observation.json'))
            facts = validate_observation(probe['observation'])
            result = freeze_contract(args.output, backend_env=env, migration=probe['migration'],
                identity=facts['identity'], study_sha256=args.study_sha256, pairs=sorted(set(args.pair)),
                start=stamp(args.start), end=stamp(args.end), expected_migration_sha256=probe['migration_sha256'],
                expected_identity_sha256=facts['identity_sha256'])
        else:
            contract = bound_contract(reference)
            if contract and not stamp(contract['start']) <= datetime.now(UTC) < stamp(contract['end']):
                raise ValueError('original registered source window is not open')
            migration = migration_snapshot(args.migration_dir)
            observer = LocalPostgresObserver(ROOT)
            observation = observer.read(pair=args.pair, timeframe=args.timeframe, limit=args.limit)
            result = publish_observation(args.output, observation=observation, migration=migration,
                                         backend_env=env, contract=reference)
            result['audit'] = audit_observation(args.output,
                expected_observation_sha256=result['observation_sha256'],
                expected_completion_sha256=result['completion_sha256'], contract=reference)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Docker/psql/env diagnostics may contain credentials; do not relay them.
        print('Local source provenance failed: ' + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
