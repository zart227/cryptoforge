"""Prepare a prospective virtual cash component and enforce its actual calendar."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from freeze_walk_forward_cash_selection import verify_abstention
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.source_contract import source_hashes, assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.walk_forward_cash_test import validate_cash_job, cash_test_status, evaluate_cash_reference
from cryptoforge.walk_forward_cash_selection import cash_selection_status
from cryptoforge.walk_forward import validate_fold
from cryptoforge.live_learning_protocol import time


def dependencies():
    return dict(job=validate_cash_job, status=cash_test_status, evaluation=evaluate_cash_reference,
        validation=verify_abstention, selection_clock=cash_selection_status, fold=validate_fold,
        timestamp=time, runner=Path(__file__).resolve())


def read_reference(reference):
    raw = Path(reference['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('original cash job input differs')
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'status', 'evaluate'))
    parser.add_argument('--job', type=Path, required=True)
    for name in ('plan', 'evidence', 'selection', 'output'):
        parser.add_argument('--'+name, type=Path)
    args = parser.parse_args(); observed = datetime.now(UTC); deps = dependencies()
    if args.operation == 'prepare':
        if args.job.exists(): parser.error('immutable cash reference job already exists')
        if not all((args.plan, args.evidence, args.selection)): parser.error('original plan/evidence/selection required')
        references = {}
        for name in ('plan', 'evidence', 'selection'):
            path = getattr(args, name); raw = path.read_bytes()
            references[name] = dict(path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest())
        plan_raw, evidence_raw, selection_raw = (read_reference(references[key]) for key in ('plan','evidence','selection'))
        fold = verify_abstention(plan_raw, evidence_raw, Path('.local/state/research-attempts.sqlite'), observed=observed)
        receipt = json.loads(selection_raw)
        if (receipt['fold'] != fold or receipt['plan_sha256'] != references['plan']['sha256']
                or receipt['evidence_sha256'] != references['evidence']['sha256']):
            raise ValueError('cash receipt does not bind original validation evidence')
        plan = json.loads(plan_raw); evidence = json.loads(evidence_raw)
        capitals = {study['manifest']['base_config']['capital'] for study in plan['studies']
            if study['manifest']['fold_index'] == evidence['fold_index']}
        if len(capitals) != 1: raise ValueError('one declared capital required')
        job = dict(schema_version='walk-forward-cash-reference-job-v1', scope='virtual_idle_cash_only',
            registered_at=observed.isoformat(), selection_receipt=receipt, initial_cash=capitals.pop(),
            original_inputs=references, live_promotion_allowed=False)
        validate_cash_job(job, observed)
        hashes = source_hashes(deps)
        job['implementation_hashes'] = hashes
        job['runtime_source_bundle'] = save_runtime_sources(args.job.parent/'cash-test-runtime', deps, hashes)
        assert_source_dependencies(hashes, deps)
        write_json_report(args.job, job)
    else:
        job = json.loads(args.job.read_bytes())
        assert_source_dependencies(job['implementation_hashes'], deps)
        originals = {key: read_reference(value) for key, value in job['original_inputs'].items()}
        if json.loads(originals['selection']) != job['selection_receipt']:
            raise ValueError('cash job selection payload differs')
        fold = verify_abstention(originals['plan'], originals['evidence'],
            Path('.local/state/research-attempts.sqlite'), observed=observed)
        if fold != job['selection_receipt']['fold']:
            raise ValueError('cash job fold differs from original selection')
        plan = json.loads(originals['plan']); evidence = json.loads(originals['evidence'])
        capitals = {study['manifest']['base_config']['capital'] for study in plan['studies']
            if study['manifest']['fold_index'] == evidence['fold_index']}
        if capitals != {job['initial_cash']}:
            raise ValueError('cash reference capital differs from declared protocol')
        validate_cash_job(job, observed)
    status = cash_test_status(job, observed)
    if args.operation == 'evaluate':
        result = evaluate_cash_reference(job, observed)
        if args.output is None or args.output.exists(): parser.error('new output path required')
        result['job_sha256'] = hashlib.sha256(args.job.read_bytes()).hexdigest()
        write_json_report(args.output, result)
    print(json.dumps(dict(status=status, observed_at=observed.isoformat(),
        test_end=job['selection_receipt']['fold']['test_end'],
        independent_profitability_established=False, live_promotion_allowed=False)))


if __name__ == '__main__': main()
