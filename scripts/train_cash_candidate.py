"""Manual offline fit; no registration, publication, orders or holdout reads."""
from datetime import UTC,datetime,timedelta
import argparse
import hashlib,json,os,tempfile
from pathlib import Path

from cryptoforge.cash_training import fit_cash_candidate,FIT_POLICY
from cryptoforge.experience_memory import available_experiences
from cryptoforge.live_learning_protocol import load_protocol,split_cutoff,collection_is_healthy,time
from cryptoforge.cash_study_paths import load_cash_study,DEFAULT_PROTOCOL
from cryptoforge.cash_study_registry import require_collection_freeze


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,default=DEFAULT_PROTOCOL)
    args=parser.parse_args(argv);now=datetime.now(UTC);protocol_path=args.protocol;protocol,study=load_cash_study(protocol_path)
    require_collection_freeze(study)
    fit_policy=Path('config/cash-training-fit-policy-v1.json');fit_raw=fit_policy.read_bytes()
    if hashlib.sha256(fit_raw).hexdigest()!=fit_policy.with_suffix('.sha256').read_text().strip() or json.loads(fit_raw)!=FIT_POLICY:
        raise ValueError('fixed fit policy checksum or implementation mismatch')
    output=study.training
    marker=output/'fit-report.json'
    if marker.exists():
        report=json.loads(marker.read_bytes());raw=report['artifact_payload'].encode()
        if (hashlib.sha256(raw).hexdigest()!=report['artifact_sha256'] or
            report['protocol_sha256']!=study.protocol_sha256):
            raise ValueError('original fit report identity mismatch')
        path=output/(report['artifact_sha256']+'.json')
        if path.exists() and path.read_bytes()!=raw:raise ValueError('original fitted artifact was changed')
        if not path.exists():
            with path.open('xb') as stream:stream.write(raw)
            path.chmod(0o600)
        print(json.dumps({'status':'original_fit_restored_no_new_fit','artifact':str(path.resolve()),'live_promotion_allowed':False}))
        return
    dataset=json.loads(Path('.local/state/cash-recovery-dataset.json').read_bytes())
    snapshots={split:available_experiences(Path('.local/state/live-experience-memory.sqlite'),
        target=protocol['target_version'],as_of=split_cutoff(protocol,split,now)) for split in ('train','validation')}
    from cryptoforge.research_protocol import assert_resources
    import shutil
    resource_policy=json.loads(Path('config/research-protocol-v1.json').read_bytes())
    memory={line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    assert_resources(resource_policy,memory['MemAvailable']/1024,shutil.disk_usage('.').free/1024**2)
    artifact=fit_cash_candidate(protocol,snapshots,as_of=now,source_healthy=collection_is_healthy(dataset,protocol,now))
    finished=datetime.now(UTC)
    if finished>=time(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds']):
        raise ValueError('fit completed after candidate deadline')
    artifact['trained_at']=finished.isoformat()
    if hashlib.sha256(protocol_path.read_bytes()).hexdigest()!=study.protocol_sha256:raise ValueError('frozen collection protocol changed during fit')
    artifact['config']['protocol_sha256']=study.protocol_sha256
    raw=(json.dumps(artifact,indent=2)+'\n').encode();sha=hashlib.sha256(raw).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    report={'status':'offline_fit_completed_no_registration','artifact_sha256':sha,
            'protocol_sha256':artifact['config']['protocol_sha256'],'trials':artifact['validation_search'],
            'artifact_payload':raw.decode(),'completed_at':artifact['trained_at'],'live_promotion_allowed':False}
    # A partial marker must never strand the one-fit record after a crash.
    fd,temporary=tempfile.mkstemp(dir=output,prefix='.fit-report-')
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(report,stream,indent=2);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,marker)  # exclusive, fully written publication
    finally:os.unlink(temporary)
    marker.chmod(0o600)
    path=output/(sha+'.json')
    with path.open('xb') as stream:stream.write(raw)
    path.chmod(0o600)
    print(json.dumps({'artifact':str(path.resolve()),'trials':len(artifact['validation_search']),'live_promotion_allowed':False}))


if __name__=='__main__':main()
