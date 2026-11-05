"""Observe a future-only price feature study; never publish a live model."""
import argparse,json
from pathlib import Path
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.feature_migration_study import FeatureMigrationStudy
from cryptoforge.primary_training_audit import audit_primary_artifact


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--pairs',nargs='+',required=True)
    args=parser.parse_args(argv)
    audit_primary_artifact(args.artifact,require_current_source=True)
    study=FeatureMigrationStudy(Path('.local/state/feature-migrations/registry.sqlite'))
    receipt=study.freeze(version=args.version,artifact_raw=args.artifact.read_bytes(),pairs=args.pairs)
    path=study.path.parent/receipt['protocol_sha256']/'protocol.json'
    if path.exists():
        if json.loads(path.read_bytes())!=receipt:raise ValueError('original migration receipt file changed')
    else:write_json_report(path,receipt)
    print(json.dumps({'protocol_sha256':receipt['protocol_sha256'],'protocol_path':str(path),
        'comparison_scope':'future_price_endpoints_only','live_promotion_allowed':False}))
    return 0


if __name__=='__main__':raise SystemExit(main())
