"""Preregister explicit virtual execution assumptions before eligible paper begins."""
import argparse
from datetime import UTC,datetime,timedelta
import hashlib
import json
from pathlib import Path

from cryptoforge.live_learning_protocol import load_protocol,time
from cryptoforge.paper_policy_design import validate_execution_design
from cryptoforge.paper_runtime import paper_runtime_hashes,paper_runtime_sources
from cryptoforge.training_snapshot import save_runtime_sources
from cryptoforge.prospective_shadow import ShadowLedger,validate_candidate
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cost-assumption-id',required=True,help='Named fee/slippage scenario; never claims actual execution costs.')
    parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args();now=datetime.now(UTC)
    protocol_path=args.protocol;protocol,study=load_cash_study(protocol_path);require_collection_freeze(study)
    manifest_path=study.candidate
    if not manifest_path.exists():raise ValueError('qualified observed frozen candidate required first')
    raw=manifest_path.read_bytes();manifest=json.loads(raw)
    ledger=ShadowLedger(study.predictions)
    first_test=time(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    registered=ledger.verify_freeze(raw)
    if not time(manifest['selected_at'])<=registered<first_test or registered>now:raise ValueError('invalid candidate registration')
    protocol_sha=study.protocol_sha256
    if manifest['protocol_sha256']!=protocol_sha:raise ValueError('candidate protocol changed')
    artifact_raw=Path(manifest['artifact_path']).read_bytes()
    if hashlib.sha256(artifact_raw).hexdigest()!=manifest['artifact_sha256']:raise ValueError('candidate artifact changed')
    validate_candidate(manifest,json.loads(artifact_raw),protocol,now=now)
    first_paper=time(protocol['windows']['paper']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    if now>=first_paper:raise ValueError('cannot select paper execution parameters after eligible paper starts')
    path=study.execution_policy;policy=json.loads(path.read_bytes())
    original=ledger.frozen_paper_policy(protocol_sha)
    if original:
        original_raw,receipt=original;stored=json.loads(original_raw)
        if receipt['candidate_sha256']!=manifest['artifact_sha256'] or stored['wallet']['cost_assumption_id']!=args.cost_assumption_id:
            raise ValueError('cannot change an already observed paper policy')
        if path.read_bytes()!=original_raw and policy.get('status')!='draft_execution_disabled':
            raise ValueError('existing frozen policy file was modified')
        if time(receipt['observed_at'])>=first_paper:raise ValueError('late policy registration')
        path.write_bytes(original_raw)
        receipt_path=path.with_suffix('.freeze.json')
        if receipt_path.exists() and json.loads(receipt_path.read_bytes())!=receipt:raise ValueError('policy receipt changed')
        receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps({'paper_policy_restored':True,'original_observed_at':receipt['observed_at'],'live_promotion_allowed':False}));return
    if policy['status']!='draft_execution_disabled':raise ValueError('paper policy already frozen')
    policy['wallet']['cost_assumption_id']=args.cost_assumption_id
    if not args.cost_assumption_id.strip():raise ValueError('explicit cost scenario required')
    validate_execution_design(policy)
    fingerprints=paper_runtime_hashes()
    policy['implementation_hashes']=fingerprints
    policy['runtime_source_bundle']=save_runtime_sources(path.parent/'paper-runtime-sources',paper_runtime_sources(),fingerprints)
    policy.update(status='frozen',enabled=True)
    data=(json.dumps(policy,indent=2)+'\n').encode()
    if paper_runtime_hashes()!=fingerprints:raise ValueError('paper runtime changed during policy preparation')
    receipt=ledger.freeze_paper_policy(data,protocol_sha=protocol_sha,candidate_sha=manifest['artifact_sha256'])
    # Ledger freeze is authoritative; changed/missing files never permit execution.
    staged=path.with_suffix('.tmp');staged.write_bytes(data);staged.replace(path)
    receipt_path=path.with_suffix('.freeze.json')
    with receipt_path.open('x') as stream:stream.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'paper_policy_frozen':True,'observed_at':receipt['observed_at'],'live_promotion_allowed':False}))


if __name__=='__main__':main()
