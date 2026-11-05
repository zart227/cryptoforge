import json
import scripts.run_stop_case_audit_job as module


def test_changed_ingestion_blocks_before_subprocess(tmp_path, monkeypatch):
    pointer = tmp_path/'ingestion.json'; pointer.write_text('{}')
    job = tmp_path/'job.json'
    job.write_text(json.dumps({'implementation_hashes': {}, 'runtime_source_bundle': {},
                              'ingestion': str(pointer), 'ingestion_sha256': 'wrong'}))
    monkeypatch.setattr(module, 'assert_source_dependencies', lambda *args: None)
    monkeypatch.setattr(module, 'load_runtime_sources', lambda *args: None)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not start')))
    status = module.run(job)
    assert status['status'] == 'blocked_contract_or_audit'
    assert status['error'] == 'fixed ingestion pointer changed'
    assert not status['completed']


def test_duplicate_output_cases_do_not_count_as_complete(monkeypatch):
    ingestion = {'cases': [{'case_id': 'a', 'source_sample': {'pair': 'BTC/USDT'}}], 'selected_case_count': 1}
    monkeypatch.setattr(module, '_load', lambda ref: ingestion)
    report = {'original_ingestion_receipt': 'ref', 'cases': [
        {'case_id': 'a', 'pair': 'BTC/USDT'}, {'case_id': 'a', 'pair': 'BTC/USDT'}], 'completed_cases': 2}
    import pytest
    with pytest.raises(ValueError, match='complete unique'):
        module.verify_report(report, {}, {'receipt': 'ref'})
