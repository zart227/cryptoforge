import json
from types import SimpleNamespace
import pytest
import scripts.preflight_cash_training as module


def test_preflight_only_reads_train_and_validation_cutoffs(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);source=tmp_path/'.local/state/cash-recovery-dataset.json'
    source.parent.mkdir(parents=True);source.write_text('{}')
    protocol={'target_version':'cash-target'}
    monkeypatch.setattr(module,'load_cash_study',lambda path:(protocol,SimpleNamespace(protocol_sha256='frozen')))
    monkeypatch.setattr(module,'require_collection_freeze',lambda study:None)
    requested=[]
    monkeypatch.setattr(module,'split_cutoff',lambda p,split,now:requested.append(split) or now)
    monkeypatch.setattr(module,'available_experiences',lambda *args,**kwargs:[])
    monkeypatch.setattr(module,'collection_is_healthy',lambda *args:True)
    monkeypatch.setattr(module,'evaluate_readiness',lambda *args,**kwargs:{
        'splits':{key:{} for key in ('train','validation','sealed_test','paper')},'sealed_test_data_ready':False})
    monkeypatch.setattr(module,'source_hashes',lambda deps:{})
    monkeypatch.setattr(module,'save_runtime_sources',lambda *args:{})
    monkeypatch.setattr(module,'assert_source_dependencies',lambda *args:None)
    result=module.preflight(tmp_path/'protocol.json',tmp_path/'output.json')
    assert requested==['train','validation']
    assert set(result['splits'])=={'train','validation'}
    assert not result['sealed_test_rewards_loaded'] and not result['paper_rewards_loaded']
    assert not result['fit_performed']


def test_existing_receipt_is_preserved_before_loading_protocol(tmp_path):
    output=tmp_path/'output.json';output.write_text('original')
    with pytest.raises(ValueError,match='immutable'):
        module.preflight(tmp_path/'missing.json',output)
    assert output.read_text()=='original'
