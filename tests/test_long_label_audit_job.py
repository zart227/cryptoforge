import json
from scripts.run_long_label_audit_job import register,read_job,run_job


def test_registered_job_is_fixed_and_original_sources_retained(tmp_path):
    path=register(tmp_path);receipt=read_job(path)
    assert receipt['manifest']['max_candles']==25919
    assert receipt['manifest']['live_promotion_allowed'] is False
    assert receipt['manifest']['parameter_search'] is False
    assert path.stat().st_mode & 0o777 == 0o600


def test_changed_job_is_blocked_before_launching_research(tmp_path):
    path=register(tmp_path);receipt=json.loads(path.read_bytes())
    receipt['manifest']['max_candles']=1000;path.write_text(json.dumps(receipt))
    result=run_job(path)
    assert result['status']=='blocked_contract_or_source' and not result['completed']
    assert not (path.parent/'report.json').exists()


def test_success_without_a_report_cannot_count_as_completion(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import scripts.run_long_label_audit_job as module
    path=register(tmp_path)
    monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stderr=''))
    result=run_job(path)
    assert result['status']=='blocked_contract_or_source' and not result['completed']


def test_partial_report_cannot_complete_full_registered_archive_job(tmp_path):
    path=register(tmp_path);job=read_job(path);manifest=job['manifest']
    expected={key:value for key,value in manifest['implementation_hashes'].items() if key!='job_runner'}
    report={'manual_review_complete':False,'portfolio_profitability_established':False,
        'implementation_hashes':expected,'pairs':[{'pair':pair,'candles':3500,'scope':'first_70_percent_development_train_only'} for pair in manifest['pairs']]}
    (path.parent/'report.json').write_text(json.dumps(report))
    result=run_job(path)
    assert not result['completed'] and result['status']=='blocked_contract_or_source'
