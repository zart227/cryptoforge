"""Fail-closed activation gates for the independent virtual worker."""
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from cryptoforge.live_learning_protocol import time
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.prospective_shadow import ShadowLedger,validate_candidate


def load_activation(protocol_path,policy_path,manifest_path,shadow_path,*,now):
    from cryptoforge.cash_study_paths import load_cash_study
    from cryptoforge.cash_study_registry import require_collection_freeze
    protocol,study=load_cash_study(protocol_path);require_collection_freeze(study)
    if not manifest_path.exists():return {'enabled':False,'status':'waiting_for_qualified_candidate'}
    if not policy_path.exists():return {'enabled':False,'status':'missing_paper_policy'}
    policy=json.loads(policy_path.read_bytes())
    if policy.get('status')!='frozen' or policy.get('enabled') is not True:
        return {'enabled':False,'status':'paper_policy_not_frozen'}
    # A separate freeze receipt is created by the policy preregistration step.
    receipt_path=policy_path.with_suffix('.freeze.json')
    if not receipt_path.exists():return {'enabled':False,'status':'paper_policy_has_no_observed_freeze'}
    receipt=json.loads(receipt_path.read_bytes());raw_policy=policy_path.read_bytes()
    if hashlib.sha256(raw_policy).hexdigest()!=receipt['policy_sha256']:
        raise ValueError('paper policy changed after its freeze')
    first_paper=time(protocol['windows']['paper']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    frozen=time(receipt['observed_at'])
    if not time(protocol['frozen_at'])<=frozen<first_paper or frozen>now:
        raise ValueError('paper policy must be observed before eligible paper window')
    raw=manifest_path.read_bytes();manifest=json.loads(raw);ledger=ShadowLedger(shadow_path)
    ledger.verify_paper_policy(raw_policy,receipt)
    from cryptoforge.paper_runtime import verify_paper_runtime
    verify_paper_runtime(policy)
    actual_registration=ledger.verify_freeze(raw)
    first_test=time(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    if not time(manifest['selected_at'])<=actual_registration<first_test or actual_registration>now:
        raise ValueError('candidate registration is late or unverified')
    protocol_sha=study.protocol_sha256
    if manifest['protocol_sha256']!=protocol_sha or receipt['protocol_sha256']!=protocol_sha:
        raise ValueError('paper protocol checksum mismatch')
    if receipt['candidate_sha256']!=manifest['artifact_sha256']:
        raise ValueError('paper policy belongs to another candidate')
    artifact_raw=Path(manifest['artifact_path']).read_bytes()
    if hashlib.sha256(artifact_raw).hexdigest()!=manifest['artifact_sha256']:
        raise ValueError('paper candidate artifact changed')
    validate_candidate(manifest,json.loads(artifact_raw),protocol,now=now)
    if policy.get('protocol_version')!=protocol['protocol_version'] or policy.get('live_promotion_allowed') is not False:
        raise ValueError('paper policy must remain isolated from live promotion')
    from cryptoforge.paper_acceptance import AcceptanceRegistry
    acceptance_path=policy_path.with_name('paper-acceptance-policy-v1.json')
    acceptance_receipt_path=acceptance_path.with_suffix('.freeze.json')
    if not acceptance_path.exists() or not acceptance_receipt_path.exists():
        return {'enabled':False,'status':'missing_observed_acceptance_criteria'}
    acceptance_raw=acceptance_path.read_bytes();acceptance=json.loads(acceptance_raw)
    acceptance_receipt=json.loads(acceptance_receipt_path.read_bytes())
    AcceptanceRegistry(shadow_path.parent/'paper-acceptance-registry.sqlite').verify(acceptance_raw,acceptance_receipt)
    if (acceptance['status']!='frozen' or acceptance['allow_real_promotion'] is not False or
        acceptance_receipt['protocol_sha256']!=protocol_sha or not time(acceptance_receipt['observed_at'])<first_paper):
        raise ValueError('unregistered or late paper acceptance criteria')
    from cryptoforge.paper_policy_design import validate_execution_design
    config=validate_execution_design(policy)
    end=time(protocol['windows']['paper']['end_exclusive'])
    if not first_paper<=now<end:return {'enabled':False,'status':'outside_paper_window'}
    return {'enabled':True,'status':'eligible_virtual_worker','policy':policy,'protocol':protocol,'manifest':manifest,
            'config':config,'acceptance':acceptance,'window_start':first_paper,'window_end':end,
            'entry_cutoff':end-timedelta(seconds=protocol['embargo_seconds'])}
