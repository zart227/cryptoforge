"""Prepare/review/apply a UID binding without modifying the credential-bound journal."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.account_migration import apply_migration, prepare_migration
from cryptoforge.bybit_private import BybitPrivateClient


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    operations=parser.add_subparsers(dest='operation',required=True)
    prepare=operations.add_parser('prepare')
    for name in ('journal','account-policy','lock-directory','backup','plan'):
        prepare.add_argument('--'+name,type=Path,required=True)
    prepare.add_argument('--review-reference',required=True)
    apply=operations.add_parser('apply')
    apply.add_argument('--plan',type=Path,required=True)
    apply.add_argument('--reviewed-plan-sha256',required=True)
    args=parser.parse_args(argv)
    try:
        client=BybitPrivateClient.from_env()
        if args.operation=='prepare':
            result=prepare_migration(journal_path=args.journal,client=client,policy_path=args.account_policy,
                lock_directory=args.lock_directory,backup_path=args.backup,plan_path=args.plan,
                review_reference=args.review_reference)
        else:
            result=apply_migration(plan_path=args.plan,reviewed_plan_sha256=args.reviewed_plan_sha256,client=client)
    except (OSError,ValueError,TypeError,KeyError,ArithmeticError,sqlite3.Error) as error:
        print(json.dumps(dict(status='blocked',error_type=type(error).__name__,live_admission_granted=False)))
        return 1
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
