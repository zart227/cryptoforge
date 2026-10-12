from datetime import timedelta
from pathlib import Path
import json
import pytest
from cryptoforge.walk_forward import folds
from cryptoforge.walk_forward_selection import FoldSelections
from test_walk_forward import START


def fixture(tmp_path):
    fold=folds(START,START+timedelta(days=365))[0];now=fold.test_start+timedelta(hours=1)
    raw=json.dumps({'trained_at':now.isoformat(),'live_eligible':False,'weights':[1],
        'config':{'fit_information_end':(fold.test_start-timedelta(days=2)).isoformat()}}).encode()
    return fold,now,raw,FoldSelections(tmp_path/'selection.sqlite',clock=lambda:now)


def test_freeze_is_actual_and_only_original_selection_can_be_recovered(tmp_path):
    fold,now,raw,registry=fixture(tmp_path);record=registry.freeze('a'*64,fold,raw)
    assert record['observed_at']==now.isoformat() and not record['live_promotion_allowed']
    assert registry.path.stat().st_mode & 0o777 == 0o600
    registry.clock=lambda:fold.test_end
    assert registry.freeze('a'*64,fold,raw)==record
    with pytest.raises(ValueError,match='cannot change'):registry.freeze('a'*64,fold,raw.replace(b'[1]',b'[2]'))


def test_early_late_and_unpurged_freezes_do_not_create_a_registry(tmp_path):
    fold,now,raw,registry=fixture(tmp_path)
    for stamp in (fold.test_start-timedelta(seconds=1),fold.test_start+fold.embargo):
        registry.clock=lambda:stamp
        with pytest.raises(ValueError,match='before eligible'):registry.freeze('a'*64,fold,raw)
        assert not registry.path.exists()
    registry.clock=lambda:now;artifact=json.loads(raw)
    artifact['config']['fit_information_end']=(fold.test_start-timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError,match='unpurged'):registry.freeze('a'*64,fold,json.dumps(artifact).encode())
    assert not registry.path.exists()


def test_same_test_interval_cannot_have_two_selected_models(tmp_path):
    from dataclasses import replace
    fold,now,raw,registry=fixture(tmp_path);registry.freeze('a'*64,fold,raw)
    changed_train=replace(fold,train_start=fold.train_start+timedelta(days=1))
    with pytest.raises(ValueError,match='one selection'):registry.freeze('a'*64,changed_train,raw)


def test_timezone_alias_does_not_create_a_second_test_selection(tmp_path):
    from dataclasses import replace
    from datetime import datetime,timezone
    fold,now,raw,registry=fixture(tmp_path);original=registry.freeze('a'*64,fold,raw)
    zone=timezone(timedelta(hours=3))
    fields={key:getattr(fold,key).astimezone(zone) for key in ('train_start','train_end','validation_start','validation_end','test_start','test_end')}
    alias=replace(fold,**fields)
    assert registry.freeze('a'*64,alias,raw)==original
