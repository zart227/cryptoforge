"""Freeze research-only evaluation criteria before paper outcomes exist."""
from datetime import UTC,datetime,timedelta
import argparse
import hashlib,json
from pathlib import Path

from cryptoforge.live_learning_protocol import load_protocol,time
from cryptoforge.paper_acceptance import AcceptanceRegistry
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args(argv);p=args.protocol;protocol,study=load_cash_study(p);require_collection_freeze(study)
    registry=AcceptanceRegistry(study.acceptance_registry)
    protocol_sha=study.protocol_sha256
    registered=registry.registered(protocol_sha)
    now=datetime.now(UTC)
    first=time(protocol['windows']['paper']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    if not registered and now>=first:raise ValueError('cannot choose acceptance criteria after eligible paper begins')
    path=study.acceptance_policy
    policy=json.loads(path.read_bytes() if path.exists() else registered[0])
    if not registered and policy['status']!='draft_not_preregistered':raise ValueError('acceptance policy already frozen')
    if policy['protocol_version']!=protocol['protocol_version']:raise ValueError('acceptance protocol mismatch')
    policy['status']='frozen';raw=(json.dumps(policy,indent=2)+'\n').encode()
    if registered:
        original,receipt=registered
        if raw!=original:raise ValueError('recovery cannot change registered criteria')
        if time(receipt['observed_at'])>=first:raise ValueError('registration was too late')
        raw=original
    else:receipt=registry.freeze(raw,protocol_sha=protocol_sha)
    receipt_path=path.with_suffix('.freeze.json')
    if receipt_path.exists():
        if json.loads(receipt_path.read_bytes())!=receipt:raise ValueError('existing receipt differs from registration')
    staged=path.with_suffix('.tmp');staged.write_bytes(raw);staged.replace(path)
    if not receipt_path.exists():
        staged_receipt=receipt_path.with_suffix('.tmp')
        staged_receipt.write_text(json.dumps(receipt,indent=2)+'\n');staged_receipt.replace(receipt_path)
    print(json.dumps({'research_criteria_frozen':True,'observed_at':receipt['observed_at'],'live_promotion_allowed':False}))


if __name__=='__main__':main()
