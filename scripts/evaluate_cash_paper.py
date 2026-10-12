"""Evaluate conditional simulation evidence after the preregistered paper end."""
from cryptoforge.atomic_reports import write_json_report
from datetime import UTC,datetime,timedelta
import argparse
import hashlib,json
from pathlib import Path

from cryptoforge.live_learning_protocol import load_protocol,time
from cryptoforge.prospective_shadow import ShadowLedger
from cryptoforge.paper_acceptance import evaluate_paper,AcceptanceRegistry
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args();now=datetime.now(UTC);p=args.protocol;protocol,study=load_cash_study(p);require_collection_freeze(study)
    policy_path=study.acceptance_policy;raw=policy_path.read_bytes();policy=json.loads(raw)
    frozen=False;receipt_path=policy_path.with_suffix('.freeze.json')
    if receipt_path.exists():
        receipt=json.loads(receipt_path.read_bytes())
        registry=AcceptanceRegistry(study.acceptance_registry)
        try:
            registry.verify(raw,receipt)
            first=time(protocol['windows']['paper']['start'])+timedelta(seconds=protocol['embargo_seconds'])
            frozen=(receipt['protocol_sha256']==study.protocol_sha256 and time(receipt['observed_at'])<first)
        except (ValueError,KeyError):frozen=False
    source=study.paper_results
    roles=json.loads(source.read_bytes()).get('roles',{}) if source.exists() else {}
    result=evaluate_paper(roles.get('candidate'),roles.get('baseline_control'),roles.get('stress_candidate'),policy,
        window_start=time(protocol['windows']['paper']['start'])+timedelta(seconds=protocol['embargo_seconds']),
        window_end=time(protocol['windows']['paper']['end_exclusive']),as_of=now,preregistered=frozen)
    result['protocol_version']=protocol['protocol_version']
    out=study.paper_acceptance;out.parent.mkdir(parents=True,exist_ok=True)
    write_json_report(out,result)
    print(json.dumps({'status':result['status'],'paper_evidence_pass':result['paper_evidence_pass'],
                     'live_promotion_allowed':False,'output':str(out.resolve())}))


if __name__=='__main__':main()
