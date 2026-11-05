"""Recheck registered evidence and freeze abstention only in its observed window."""
import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from cryptoforge.validation_evidence import select_registered_validation_reports
from cryptoforge.research_attempts import identity
from cryptoforge.walk_forward_cash_selection import cash_selection_status, freeze_cash_selection
from cryptoforge.live_learning_protocol import time


def verify_abstention(plan_raw, evidence_raw, ledger, *, observed=None):
    plan, evidence = json.loads(plan_raw), json.loads(evidence_raw)
    observed = observed or datetime.now(UTC)
    if time(evidence['observed_at']) > observed or time(plan['observed_at']) > observed:
        raise ValueError('selection evidence unavailable at observed clock')
    if evidence['plan_sha256'] != hashlib.sha256(plan_raw).hexdigest():
        raise ValueError('selection plan identity mismatch')
    if (evidence['test_rewards_read'] is not False or evidence['winner'] is not None
            or evidence['no_candidate_cash_only'] is not True):
        raise ValueError('verified abstention required; model selection is unsupported here')
    studies = [study for study in plan['studies']
               if study['manifest']['fold_index'] == evidence['fold_index']]
    if len(studies) != 2 or {study['manifest']['training_policy']['class_balance'] for study in studies} != {True, False}:
        raise ValueError('both declared heads required')
    heads = evidence['heads']
    if len(heads) != 2 or {head['study_sha256'] for head in heads} != {study['study_sha256'] for study in studies}:
        raise ValueError('complete original head evidence required')
    fold = studies[0]['manifest']['fold']
    from datetime import timedelta
    boundary = time(fold['test_start']) - timedelta(seconds=fold['embargo'])
    for study in studies:
        manifest = study['manifest']
        if identity(manifest) != study['study_sha256']:
            raise ValueError('registered declaration identity differs')
        if manifest['fold'] != fold or manifest['calendar_sha256'] != plan['calendar_sha256']:
            raise ValueError('inconsistent declared calendar')
        head = next(item for item in heads if item['study_sha256'] == study['study_sha256'])
        if head['class_balance'] != manifest['training_policy']['class_balance']:
            raise ValueError('head identity differs')
        paths = {}
        for report in head['reports']:
            path = Path(report['path']); raw = path.read_bytes(); payload = json.loads(raw)
            if (hashlib.sha256(raw).hexdigest() != report['sha256'] or payload != report['payload']
                    or payload['test_rewards_read'] is not False):
                raise ValueError('original report differs')
            if time(payload['evaluation_information_end']) >= boundary:
                raise ValueError('unpurged validation information')
            key = identity(payload['candidate'])
            if key in paths:
                raise ValueError('duplicate validation candidate')
            paths[key] = path
        if set(paths) != {identity(candidate) for candidate in manifest['grid']}:
            raise ValueError('complete declared grid required')
        policy = manifest['selection_policy']
        selected = select_registered_validation_reports(ledger, study_sha256=study['study_sha256'],
            reports=paths, validation_start=datetime.fromisoformat(policy['validation_start']),
            validation_end=datetime.fromisoformat(policy['validation_end']),
            minimum_trades=policy['minimum_trades'], maximum_drawdown=policy['maximum_drawdown'])
        if selected != head['selection'] or selected['selected_report_sha256'] is not None:
            raise ValueError('registered selection is not abstention')
    return fold


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'evidence', 'receipt'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--ledger', type=Path, default=Path('.local/state/research-attempts.sqlite'))
    args = parser.parse_args()
    plan_raw, evidence_raw = args.plan.read_bytes(), args.evidence.read_bytes()
    fold = verify_abstention(plan_raw, evidence_raw, args.ledger)
    observed = datetime.now(UTC)
    status = cash_selection_status(fold, observed)
    if status == 'ready_to_freeze' or args.receipt.exists():
        receipt = freeze_cash_selection(args.receipt, fold=fold, observed=observed,
            plan_sha256=hashlib.sha256(plan_raw).hexdigest(), evidence_sha256=hashlib.sha256(evidence_raw).hexdigest())
        status = 'frozen_no_candidate_cash_only'
    print(json.dumps(dict(status=status, observed_at=observed.isoformat(),
        selection_start=fold['test_start'], test_end=fold['test_end'],
        independent_profitability_established=False, live_promotion_allowed=False)))
    if status == 'selection_deadline_missed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
