"""Read-only train/validation readiness; sealed rewards are never loaded."""
import argparse,hashlib,json
from datetime import datetime,UTC
from pathlib import Path
from cryptoforge.cash_study_paths import load_cash_study
from cryptoforge.cash_study_registry import require_collection_freeze
from cryptoforge.experience_memory import available_experiences
from cryptoforge.live_learning_protocol import evaluate_readiness,collection_is_healthy,split_cutoff
from cryptoforge.source_contract import source_hashes,assert_source_dependencies
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw
from cryptoforge.atomic_reports import write_json_report


def preflight(protocol_path,output):
    if output.exists():raise ValueError('immutable preflight output already exists')
    protocol,study=load_cash_study(protocol_path);require_collection_freeze(study)
    now=datetime.now(UTC)
    dataset_raw=Path('.local/state/cash-recovery-dataset.json').read_bytes();dataset=json.loads(dataset_raw)
    memory=Path('.local/state/live-experience-memory.sqlite')
    snapshots={split:available_experiences(memory,target=protocol['target_version'],as_of=split_cutoff(protocol,split,now))
               for split in ('train','validation')}
    healthy=collection_is_healthy(dataset,protocol,now)
    deps={'readiness':evaluate_readiness,'collection_health':collection_is_healthy,'memory':available_experiences,'runner':Path(__file__).resolve()}
    hashes=source_hashes(deps)
    result=evaluate_readiness(protocol,snapshots,as_of=now,source_healthy=healthy)
    # Holdout readiness is intentionally unassessed, never a missing-label failure.
    result['splits']={key:result['splits'][key] for key in ('train','validation')}
    result.pop('sealed_test_data_ready',None)
    result.update(protocol_sha256=study.protocol_sha256,source_collection_healthy=healthy,
        collection_snapshot_sha256=hashlib.sha256(dataset_raw).hexdigest(),
        collection_input_snapshot=_save_raw(output.parent/'cash-preflight-inputs',dataset_raw),
        input_snapshot=_save_raw(output.parent/'cash-preflight-inputs',json.dumps(snapshots,sort_keys=True).encode()),
        implementation_hashes=hashes,runtime_source_bundle=save_runtime_sources(output.parent/'cash-preflight-runtime',deps,hashes),
        sealed_test_rewards_loaded=False,paper_rewards_loaded=False,fit_performed=False,
        scope='current_train_validation_readiness_not_holdout_or_paper_admission')
    assert_source_dependencies(hashes,deps);write_json_report(output,result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=Path('config/live-cash-recovery-closed-protocol-v1.json'))
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=preflight(args.protocol,args.output)
    print(json.dumps({'fit_ready':result['data_ready_for_offline_fit'],'source_healthy':result['source_collection_healthy'],
        'splits':result['splits'],'blocked_reasons':result['blocked_reasons']}))


if __name__=='__main__':main()
