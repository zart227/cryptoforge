from dataclasses import replace
from datetime import UTC, datetime, timedelta
import pytest
import cryptoforge.train_window_study as study_module
from cryptoforge.model_training import TrainingExample
from cryptoforge.research_attempts import ResearchAttempts

END=datetime(2026,10,10,tzinfo=UTC)


def examples():
    train=[TrainingExample('BTC/USDT',END-timedelta(days=day),(float(day),)+(0.,)*6,
        1,0,.01*day,END-timedelta(hours=1)) for day in (4,3,2,1)]
    validation=[replace(train[0],open_time=END+timedelta(hours=hour),
        label_end_time=END+timedelta(hours=hour+1)) for hour in (1,2)]
    return train,validation


def options(tmp_path):
    return dict(grid=[dict(window_days=4,half_life_days=None),
                      dict(window_days=2,half_life_days=1)],train_end=END,
        validation_end=END+timedelta(days=1),target_version='spot-long-trade-net-v2',ridge=.01,
        ledger=ResearchAttempts(tmp_path/'study.sqlite'),protocol_id='test-window',
        protocol_version='test-window-v1',maximum_per_family=2)


def test_registration_precedes_fit_and_repeat_uses_immutable_results(tmp_path,monkeypatch):
    kwargs=options(tmp_path);train,validation=examples()
    original=study_module.fit_net_regressor
    calls=[]
    def fit(*args,**params):
        assert kwargs['ledger'].budget_usage('test-window') == {'ridge-net-training-window':2}
        calls.append(1)
        return original(*args,**params)
    # Preserve source manifest across instrumentation; production hashes real functions.
    sources=study_module.window_study_sources()
    dependencies=study_module.window_study_dependencies()
    monkeypatch.setattr(study_module,'window_study_sources',lambda:sources)
    monkeypatch.setattr(study_module,'window_study_dependencies',lambda:dependencies)
    monkeypatch.setattr(study_module,'fit_net_regressor',fit)
    report=study_module.run_train_window_study(train,validation,**kwargs)
    assert len(calls)==2
    assert report == study_module.run_train_window_study(train,validation,**kwargs)
    assert len(calls)==2
    assert [row['train_count'] for row in report['results']] == [4,2]
    assert not report['selection_performed'] and not report['live_promotion_allowed']


def test_overlap_and_equivalent_duplicate_grid_rejected_before_registration(tmp_path):
    train,validation=examples();kwargs=options(tmp_path)
    validation[0]=replace(validation[0],open_time=END)
    with pytest.raises(ValueError,match='follow train'):
        study_module.run_train_window_study(train,validation,**kwargs)
    assert not kwargs['ledger'].path.exists()
    train,validation=examples()
    kwargs['grid']=[dict(window_days=4,half_life_days=None),dict(window_days=4.,half_life_days=None)]
    with pytest.raises(ValueError,match='duplicate effective'):
        study_module.run_train_window_study(train,validation,**kwargs)
    assert not kwargs['ledger'].path.exists()


def test_changed_validation_snapshot_changes_study_without_extra_configuration_budget(tmp_path):
    train,validation=examples();kwargs=options(tmp_path)
    first=study_module.run_train_window_study(train,validation,**kwargs)
    validation[0]=replace(validation[0],future_return=.05)
    second=study_module.run_train_window_study(train,validation,**kwargs)
    assert first['study_sha256'] != second['study_sha256']
    assert kwargs['ledger'].budget_usage('test-window') == {'ridge-net-training-window':2}


def test_source_change_during_fit_records_failure_and_blocks_silent_retry(tmp_path,monkeypatch):
    train,validation=examples();kwargs=options(tmp_path)
    sources=study_module.window_study_sources()
    calls=[]
    def hashes():
        calls.append(1)
        return sources if len(calls)==1 else {**sources,'net_head':'changed'}
    monkeypatch.setattr(study_module,'window_study_sources',hashes)
    with pytest.raises(ValueError,match='source changed'):
        study_module.run_train_window_study(train,validation,**kwargs)
    monkeypatch.setattr(study_module,'window_study_sources',lambda:sources)
    with pytest.raises(ValueError,match='prior failed attempt'):
        study_module.run_train_window_study(train,validation,**kwargs)
