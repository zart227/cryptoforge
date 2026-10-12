from pathlib import Path
import json
import pytest
from cryptoforge.model_training import ModelTrainingRunner,write_model_artifact
from cryptoforge.primary_training_audit import audit_primary_artifact
from test_model_training import FakeReader,FakeSupabase,make_training_candles
from datetime import UTC,datetime


def trained(tmp_path):
    supabase=FakeSupabase()
    runner=ModelTrainingRunner(reader=FakeReader(make_training_candles()),supabase=supabase,
        artifact_dir=tmp_path,epochs=3,registry=type('Registry',(),{'latest':lambda self,**kwargs:None})())
    runner.run(['ETH/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    return next(tmp_path.glob('*.json')),supabase


def test_original_inputs_reproduce_both_heads_without_refit_or_publication(tmp_path):
    path,supabase=trained(tmp_path);before=len(supabase.upserts)
    report=audit_primary_artifact(path)
    assert report['status']=='exact_primary_inputs_and_metrics_verified'
    assert not report['refitting_performed'] and not report['publication_performed']
    assert len(supabase.upserts)==before
    assert report['split_counts']['test']==report['probability_diagnostics']['long']['test']['count']
    assert path.stat().st_mode & 0o777 == 0o600


def test_changed_normalizer_and_legacy_missing_inputs_are_not_verified(tmp_path):
    path,_=trained(tmp_path);artifact=json.loads(path.read_text())
    artifact['means'][0]+=1
    altered,_=write_model_artifact(artifact,tmp_path)
    with pytest.raises(ValueError,match='train-only'):audit_primary_artifact(altered)
    del artifact['config']['training_input_snapshot']
    legacy,_=write_model_artifact(artifact,tmp_path)
    with pytest.raises(ValueError,match='do not reconstruct'):audit_primary_artifact(legacy)


def test_source_change_during_fit_cannot_publish_even_if_metrics_pass(tmp_path,monkeypatch):
    import cryptoforge.source_contract as source
    original=source.source_hashes;calls=0
    def changed(functions):
        nonlocal calls
        calls+=1;result=original(functions)
        if calls>1:result['primary_training']='0'*64
        return result
    monkeypatch.setattr(source,'source_hashes',changed)
    supabase=FakeSupabase();runner=ModelTrainingRunner(reader=FakeReader(make_training_candles()),
        supabase=supabase,artifact_dir=tmp_path,epochs=1)
    with pytest.raises(ValueError,match='source changed'):
        runner.run(['ETH/USDT'],now=datetime(2026,9,29,15,5,tzinfo=UTC))
    assert not supabase.upserts and not list(tmp_path.glob('*.json'))


def test_interrupted_artifact_install_leaves_no_partial_model(tmp_path,monkeypatch):
    import os
    def failed(*args):raise OSError('interrupted atomic install')
    monkeypatch.setattr(os,'replace',failed)
    with pytest.raises(OSError):write_model_artifact({'model_version':'candidate'},tmp_path)
    assert not list(tmp_path.iterdir())


def test_source_drift_is_explicit_even_when_saved_numbers_still_reproduce(tmp_path,monkeypatch):
    import cryptoforge.primary_training_audit as audit
    path,_=trained(tmp_path)
    def changed(*args):raise ValueError('current source differs')
    monkeypatch.setattr(audit,'assert_source_dependencies',changed)
    with pytest.raises(ValueError,match='differs'):audit_primary_artifact(path)
    report=audit_primary_artifact(path,require_current_source=False)
    assert report['status']=='saved_inputs_and_metrics_match_current_numerics_source_differs'
    assert not report['current_source_matches_fitted_source'] and not report['archived_runtime_executed']
