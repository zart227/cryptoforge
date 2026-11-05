"""Export bounded allowlisted development facts; no LLM request or training."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.training_diagnostics import build_training_diagnostics, canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--study-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.is_symlink():
            raise ValueError('output symlink forbidden')
        output, ledger = args.output.resolve(), args.ledger.resolve()
        if (output.exists() or output == ledger or output in ledger.parents or ledger in output.parents
                or str(output) in {str(ledger)+suffix for suffix in ('-wal', '-shm', '-journal')}):
            raise ValueError('new independent diagnostics output required')
        result = build_training_diagnostics(args.ledger, study_sha256=args.study_sha256)
        publish_new(output, canonical(result)+b'\n')
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, sqlite3.Error) as exc:
        print(json.dumps(dict(status='training_diagnostics_blocked', error_type=type(exc).__name__,
            provider_requests=0, fitting_performed=False, live_promotion_allowed=False)))
        return 1
    print(json.dumps(dict(status='development_diagnostics_saved', report_sha256=result['report_sha256'],
        configurations=len(result['results']), provider_requests=0, fitting_performed=False,
        live_promotion_allowed=False, output=str(output))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
