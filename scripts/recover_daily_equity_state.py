"""Transfer an explicitly reviewed same-day daily baseline without resetting loss."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

from cryptoforge.daily_risk_recovery import create_daily_backup, restore_daily_backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_subparsers(dest='operation', required=True)
    backup = operations.add_parser('backup')
    backup.add_argument('--state', type=Path, required=True)
    backup.add_argument('--output', type=Path, required=True)
    backup.add_argument('--account-scope', required=True,
        help='Operator-verified account scope SHA256; this tool cannot verify exchange identity.')
    backup.add_argument('--reviewed-state-sha256', required=True)
    restore = operations.add_parser('restore')
    restore.add_argument('--backup', type=Path, required=True)
    restore.add_argument('--state', type=Path, required=True)
    restore.add_argument('--account-scope', required=True)
    restore.add_argument('--expected-backup-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'backup':
            result = create_daily_backup(state_path=args.state, backup_path=args.output,
                account_scope=args.account_scope, reviewed_state_sha256=args.reviewed_state_sha256,
                now=datetime.now(UTC))
        else:
            result = restore_daily_backup(backup_path=args.backup, state_path=args.state,
                account_scope=args.account_scope, expected_backup_sha256=args.expected_backup_sha256,
                now=datetime.now(UTC))
    except (OSError, ValueError, TypeError, ArithmeticError) as exc:
        print(json.dumps(dict(status='blocked', error_type=type(exc).__name__,
            live_admission_granted=False)))
        return 1
    print(json.dumps(dict(status='completed', **result)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
