import json
from scripts import retry_portfolio_replay as job


def configure(tmp_path,monkeypatch):
    monkeypatch.setattr(job,'REQUEST',tmp_path/'request.json')
    monkeypatch.setattr(job,'STATUS',tmp_path/'status.json')
    monkeypatch.setattr(job,'OUTPUT',tmp_path/'output.json')
    monkeypatch.setattr(job,'hashes',lambda:{'source':'original'})


def test_source_change_does_not_launch_new_experiment(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch);job.main(['--register-only'])
    monkeypatch.setattr(job,'hashes',lambda:{'source':'changed'})
    monkeypatch.setattr(job.subprocess,'run',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('must not execute')))
    job.main([])
    assert json.loads(job.STATUS.read_bytes())['status']=='queued_source_changed_review_required'


def test_modified_command_is_not_executed(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch);job.main(['--register-only'])
    request=json.loads(job.REQUEST.read_bytes());request['command']=['-c','raise RuntimeError()'];job.REQUEST.write_text(json.dumps(request))
    monkeypatch.setattr(job.subprocess,'run',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('must not execute')))
    job.main([])
    assert json.loads(job.STATUS.read_bytes())['status']=='queued_request_changed_review_required'


def test_resource_defer_keeps_queue_without_creating_result(tmp_path,monkeypatch):
    from types import SimpleNamespace
    configure(tmp_path,monkeypatch)
    monkeypatch.setattr(job.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1,stderr='insufficient resources: defer research',stdout=''))
    job.main([])
    assert json.loads(job.STATUS.read_bytes())['status']=='deferred_by_resource_or_worker_guard'
    assert not job.OUTPUT.exists()
