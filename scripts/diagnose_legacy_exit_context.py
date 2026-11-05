"""Replay saved exchange and database evidence of overwritten legacy exits."""
import argparse
import hashlib
import json
from pathlib import Path

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.legacy_decision_overwrite import diagnose_case
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a new report path')
    cases, sources = [], {}
    for path in sorted(args.evidence_dir.glob('*.json')):
        raw = path.read_bytes()
        evidence = json.loads(raw)
        if 'case' not in evidence:
            continue
        cases.append(diagnose_case(evidence))
        sources[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
    if not cases or len({c['order_id'] for c in cases}) != len(cases):
        raise ValueError('nonempty distinct order evidence required')
    deps = {'diagnosis': diagnose_case, 'runner': Path(__file__).resolve()}
    hashes = source_hashes(deps)
    report = {'cases': cases, 'case_count': len(cases), 'input_sha256': sources,
              'implementation_hashes': hashes,
              'runtime_source_bundle': save_runtime_sources(args.output.parent/'runtime', deps, hashes),
              'original_exit_reasons_recovered': False, 'remote_writes': False,
              'orders_placed': False}
    write_json_report(args.output, report)
    print(json.dumps({'cases': len(cases), 'exact_candle_key_matches': len(cases),
                      'original_exit_reasons_recovered': False}))


if __name__ == '__main__':
    main()
