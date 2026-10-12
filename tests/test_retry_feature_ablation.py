import hashlib,json
from pathlib import Path
import pytest
from scripts import retry_feature_ablation as retry


def setup(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path('config').mkdir();Path('.local/state').mkdir(parents=True)
    raw_original=b'{"study_sha256":"synthetic-original"}'
    Path(retry.ARGS[4]).write_bytes(raw_original)
    protocol={'resources':{'min_available_memory_mb':10**12,'min_free_disk_mb':2048},
        'ablation_policy':{'implementation_hashes':{},
            'original_report_sha256':hashlib.sha256(raw_original).hexdigest()}}
    raw=json.dumps(protocol).encode();Path(retry.ARGS[2]).write_bytes(raw)
    monkeypatch.setattr(retry,'PROTOCOL_SHA',hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(retry,'dependencies',lambda:{})
    def no_child(*args,**kwargs):raise AssertionError('resource-deferred study cannot launch child')
    monkeypatch.setattr(retry.subprocess,'run',no_child)


def test_resource_defer_preserves_observed_request_and_does_not_fit(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    assert retry.main(['--register-only'])==0
    request=Path('.local/state/pending-feature-ablation-request-v1.json');before=request.read_bytes()
    assert retry.main([])==0
    status=json.loads(Path('.local/state/pending-feature-ablation-status.json').read_bytes())
    assert status['status']=='deferred_by_resource_guard'
    assert not status['completed'] and not status['live_promotion_allowed']
    assert request.read_bytes()==before
    assert not Path(retry.ARGS[6]).exists()


def test_changed_recorded_command_is_rejected_before_child(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch);retry.main(['--register-only'])
    path=Path('.local/state/pending-feature-ablation-request-v1.json')
    request=json.loads(path.read_bytes());request['binding']['arguments'].append('--unapproved')
    path.write_text(json.dumps(request))
    with pytest.raises(ValueError,match='binding changed'):retry.main([])
