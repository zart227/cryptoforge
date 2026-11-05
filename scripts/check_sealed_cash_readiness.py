"""Safe calendar-first preflight; no unfinished or holdout outcome payload reads."""
from datetime import UTC, datetime
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from cryptoforge.cash_study_paths import load_cash_study
from cryptoforge.cash_study_registry import require_collection_freeze
from cryptoforge.local_source_provenance import canonical, digest, _new_root, _write_new
from cryptoforge.sealed_cash_readiness import guarded_cash_readiness, bounded_available_experiences


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    protocol, study = load_cash_study(args.protocol)
    try:
        freeze = require_collection_freeze(study)
    except ValueError:
        freeze = 'missing_observed_prospective_freeze'
    paths = dict(sealed_cash_readiness=ROOT/'src/cryptoforge/sealed_cash_readiness.py',
        cli=Path(__file__), live_learning_protocol=ROOT/'src/cryptoforge/live_learning_protocol.py',
        cash_study_paths=ROOT/'src/cryptoforge/cash_study_paths.py',
        cash_study_registry=ROOT/'src/cryptoforge/cash_study_registry.py',
        local_source_provenance=ROOT/'src/cryptoforge/local_source_provenance.py',
        local_source_observer=ROOT/'src/cryptoforge/local_source_observer.py',
        backend=ROOT/'src/cryptoforge/backend.py',
        model_training=ROOT/'src/cryptoforge/model_training.py',
        cash_recovery=ROOT/'src/cryptoforge/cash_recovery.py')
    runtime = {name: digest(path.read_bytes()) for name, path in paths.items()}
    def load(split, cutoff):
        if freeze == 'missing_observed_prospective_freeze':
            raise ValueError('unobserved protocol cannot open cash outcome payloads')
        return bounded_available_experiences(ROOT/'.local/state/live-experience-memory.sqlite',
            target=protocol['target_version'], as_of=cutoff)
    # Source/collection qualification is intentionally absent from this CLI.
    # A current candle or calendar date alone cannot certify an eligible sample.
    result = guarded_cash_readiness(protocol, as_of=datetime.now(UTC), load_split=load)
    if runtime != {name: digest(path.read_bytes()) for name, path in paths.items()}:
        raise ValueError('readiness runtime changed during preflight')
    result.update(protocol_sha256=study.protocol_sha256, runtime=runtime, collection_freeze_status=freeze)
    if freeze == 'missing_observed_prospective_freeze':
        result['blocked_reasons'].append('collection_protocol_has_no_observed_freeze')
    root = _new_root(args.output)
    pin = _write_new(root/'preflight.json', result)
    sys.stdout.buffer.write(canonical(dict(root=str(root), report_sha256=pin,
        status=result['status'], inspected_splits=result['inspected_splits'],
        data_ready_for_offline_fit=result['data_ready_for_offline_fit'],
        live_promotion_allowed=False))+b'\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Sealed cash preflight failed: '+type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
