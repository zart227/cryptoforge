"""Register a qualified local candidate before holdout, never publish it live."""
import argparse
from datetime import UTC,datetime
import hashlib
import json
from pathlib import Path

from cryptoforge.experience_memory import available_experiences
from cryptoforge.live_learning_protocol import load_protocol,evaluate_readiness,collection_is_healthy,split_cutoff,SPLITS
from cryptoforge.prospective_shadow import ShadowLedger,validate_candidate
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args();now=datetime.now(UTC)
    path=args.protocol;protocol,study=load_cash_study(path);require_collection_freeze(study)
    dataset=json.loads(Path('.local/state/cash-recovery-dataset.json').read_bytes())
    memory=Path('.local/state/live-experience-memory.sqlite')
    snapshots={split:available_experiences(memory,target=protocol['target_version'],as_of=split_cutoff(protocol,split,now)) for split in SPLITS}
    ready=evaluate_readiness(protocol,snapshots,as_of=now,source_healthy=collection_is_healthy(dataset,protocol,now))
    if not ready['data_ready_for_offline_fit']:raise ValueError('candidate registration requires completed qualified train/validation')
    artifact_raw=args.artifact.read_bytes();artifact=json.loads(artifact_raw)
    from cryptoforge.cash_training import verify_fit_provenance
    report=json.loads((study.training/'fit-report.json').read_bytes())
    if report['protocol_sha256']!=study.protocol_sha256:raise ValueError('fit protocol differs from registration protocol')
    verify_fit_provenance(artifact_raw,report,protocol,{split:snapshots[split] for split in ('train','validation')},
        as_of=now,source_healthy=collection_is_healthy(dataset,protocol,now))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=study.protocol_sha256:raise ValueError('frozen collection protocol changed during registration')
    manifest={'protocol_version':protocol['protocol_version'],'protocol_sha256':study.protocol_sha256,
        'protocol_path':str(path.resolve()),
        'artifact_path':str(args.artifact.resolve()),'artifact_sha256':hashlib.sha256(artifact_raw).hexdigest(),
        'selected_at':now.isoformat(),'threshold':protocol['configuration_budget']['thresholds'][0],
        'live_eligible':False,'mode':'prospective_shadow_factual_cohort_only'}
    validate_candidate(manifest,artifact,protocol,now=now)
    raw=(json.dumps(manifest,indent=2)+'\n').encode();out=study.candidate
    if out.exists():raise ValueError('candidate already frozen; do not replace it after viewing outcomes')
    out.parent.mkdir(parents=True,exist_ok=True)
    # Freeze observed registration before exposing the immutable manifest.
    ledger=ShadowLedger(study.predictions)
    original=ledger.frozen_manifest(manifest['protocol_sha256'])
    if original:
        stored=json.loads(original)
        if stored['artifact_sha256']!=manifest['artifact_sha256']:
            raise ValueError('protocol already has a different frozen candidate')
        original_artifact=Path(stored['artifact_path'])
        if not original_artifact.exists() or hashlib.sha256(original_artifact.read_bytes()).hexdigest()!=stored['artifact_sha256']:
            raise ValueError('original frozen artifact must remain available unchanged')
        raw=original;manifest=stored
        validate_candidate(manifest,artifact,protocol,now=now)
    else:
        ledger.freeze_candidate(raw,registered_at=now)
    with out.open('xb') as stream:stream.write(raw)
    out.chmod(0o600)
    print(json.dumps({'candidate_sha256':manifest['artifact_sha256'],'registered_at':ledger.verify_freeze(raw).isoformat(),
                     'live_eligible':False,'artifact':str(args.artifact.resolve())}))


if __name__=='__main__':main()
