"""Report a future prospective shadow candidate; never invent past predictions."""
from cryptoforge.atomic_reports import write_json_report
from datetime import UTC,datetime,timedelta
import argparse
import hashlib
import json
from pathlib import Path

from cryptoforge.experience_memory import available_experiences
from cryptoforge.live_learning_protocol import load_protocol,split_cutoff
from cryptoforge.prospective_shadow import ShadowLedger,validate_candidate,compare_factual_cohort
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args(argv);now=datetime.now(UTC);protocol_path=args.protocol
    protocol,study=load_cash_study(protocol_path);require_collection_freeze(study);manifest_path=study.candidate
    result={'as_of':now.isoformat(),'protocol_version':protocol['protocol_version'],
            'full_paper_execution_harness_implemented':False,'paper_wallet_kernel_implemented':True,
            'paper_result_exporter_implemented':True,'paper_acceptance_gates_implemented':True,
            'paper_worker_implemented':True,'paper_worker_connected':False,'paper_activation_gate_implemented':True,'live_promotion_allowed':False}
    if not manifest_path.exists():
        result.update(status='waiting_for_qualified_frozen_candidate',recorded_opportunities=0,
                      historical_replay_allowed=False)
    else:
        try:
            raw=manifest_path.read_bytes();manifest=json.loads(raw)
            ledger=ShadowLedger(study.predictions)
            observed_registration=ledger.verify_freeze(raw)
            first_test=datetime.fromisoformat(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds'])
            if not datetime.fromisoformat(manifest['selected_at'])<=observed_registration<first_test or observed_registration>now:
                raise ValueError('candidate registration time mismatch')
            if manifest['protocol_sha256']!=study.protocol_sha256:
                raise ValueError('candidate protocol checksum mismatch')
            artifact_raw=Path(manifest['artifact_path']).read_bytes()
            if hashlib.sha256(artifact_raw).hexdigest()!=manifest['artifact_sha256']:
                raise ValueError('candidate checksum mismatch')
            validate_candidate(manifest,json.loads(artifact_raw),protocol,now=now)
            predictions=ledger.rows();reports={}
            for split in ('sealed_test','paper'):
                outcomes=available_experiences(Path('.local/state/live-experience-memory.sqlite'),
                    target=protocol['target_version'],as_of=split_cutoff(protocol,split,now))
                reports[split]=compare_factual_cohort(predictions,outcomes,protocol,
                    candidate_sha=manifest['artifact_sha256'],split=split,as_of=now)
            result.update(status='prospective_factual_shadow_only',reports=reports)
        except Exception as exc:
            result.update(status='invalid_candidate_or_evidence',error=type(exc).__name__)
    output=study.shadow_report;output.parent.mkdir(parents=True,exist_ok=True)
    write_json_report(output,result)
    print(json.dumps({'status':result['status'],'promotion_allowed':False,'output':str(output.resolve())}))


if __name__=='__main__':main()
