"""Audit original local research evidence; never grant live trading permission."""
import argparse
import json
from pathlib import Path
import sqlite3

from cryptoforge.cash_study_paths import load_cash_study
from cryptoforge.daily_risk_recovery import publish_new
from cryptoforge.strategy_evidence import audit_strategy_evidence, canonical


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--expected-artifact-sha256', required=True)
    parser.add_argument('--state-root', type=Path, default=Path('.local/state'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        result = audit_strategy_evidence(args.protocol,
            expected_artifact_sha256=args.expected_artifact_sha256, state_root=args.state_root)
        if args.output is not None:
            if args.output.is_symlink():
                raise ValueError('audit output cannot be a symlink')
            output = args.output.resolve()
            _, study = load_cash_study(args.protocol, state_root=args.state_root.resolve())
            protected = {Path(row['path']) for row in result['input_files']}
            protected.update((study.candidate.resolve(), study.execution_policy.resolve(),
                study.acceptance_policy.resolve(), study.paper_results.resolve(), study.paper_acceptance.resolve(),
                study.predictions.resolve(), study.acceptance_registry.resolve(),
                study.execution_policy.with_suffix('.freeze.json').resolve(),
                study.acceptance_policy.with_suffix('.freeze.json').resolve(),
                (args.state_root/'cash-study-registry.sqlite').resolve()))
            for role in ('candidate', 'baseline_control', 'stress_candidate'):
                protected.update(path.resolve() for path in study.paper_role_paths(role))
            if output.exists() or output.is_symlink() or any(
                    output == path or output in path.parents or path in output.parents or str(output) in
                    {str(path) + suffix for suffix in ('-wal', '-shm', '-journal')} for path in protected):
                raise ValueError('audit output must be a new path distinct from all evidence inputs')
            publish_new(output, canonical(result) + b'\n')
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError, sqlite3.Error) as exc:
        print(json.dumps(dict(status='strategy_evidence_blocked', error_type=type(exc).__name__,
            live_admission_granted=False, live_profitability_established=False)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
