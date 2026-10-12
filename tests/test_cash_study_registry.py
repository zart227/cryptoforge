from copy import deepcopy
from datetime import timedelta
import hashlib,json
import pytest
from cryptoforge.cash_study_paths import DEFAULT_PROTOCOL,cash_study_paths
from cryptoforge.cash_study_registry import CashStudyRegistry,require_collection_freeze
from cryptoforge.live_learning_protocol import load_protocol,time


def protocol():
    p=load_protocol(DEFAULT_PROTOCOL);p=deepcopy(p)
    p.update(protocol_version='closed-v1',input_candle_state='closed_only',feature_input_contract={
        'feature_version':'candle-v1','timeframe':'5m','input_candle_state':'closed_only',
        'calculation_contract':'bounded-window-candle-v1','lookback_candles':120})
    return p


def test_observed_freeze_recovers_original_and_version_cannot_change(tmp_path):
    p=protocol();now=time(p['frozen_at'])+timedelta(seconds=1)
    registry=CashStudyRegistry(tmp_path/'registry.sqlite',clock=lambda:now)
    raw=json.dumps(p).encode();receipt=registry.freeze(raw)
    registry.clock=lambda:now+timedelta(days=100)
    assert registry.freeze(raw)==receipt and registry.by_version(p['protocol_version'])==receipt
    assert registry.path.stat().st_mode & 0o777 == 0o600
    p['feature_input_contract']['lookback_candles']=36;registry.clock=lambda:now
    with pytest.raises(ValueError,match='version already'):registry.freeze(json.dumps(p).encode())


def test_backdated_or_future_freeze_creates_no_registry(tmp_path):
    p=protocol();stamp=time(p['frozen_at'])
    for now in (stamp-timedelta(seconds=1),stamp+timedelta(seconds=6)):
        registry=CashStudyRegistry(tmp_path/'registry.sqlite',clock=lambda:now)
        with pytest.raises(ValueError,match='retrospectively'):registry.freeze(json.dumps(p).encode())
        assert not registry.path.exists()


def test_protocol_aliases_share_one_namespace_and_unobserved_new_fit_is_blocked(tmp_path):
    raw=DEFAULT_PROTOCOL.read_bytes()
    a=tmp_path/'original.json';b=tmp_path/'alias.json'
    for path in (a,b):path.write_bytes(raw);path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    assert cash_study_paths(a,state_root=tmp_path)==cash_study_paths(b,state_root=tmp_path)
    p=protocol();raw=json.dumps(p).encode();b.write_bytes(raw);b.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    study=cash_study_paths(b,state_root=tmp_path)
    legacy=cash_study_paths(a,state_root=tmp_path)
    assert study.paper_role_paths('candidate')!=legacy.paper_role_paths('candidate')
    assert study.acceptance_registry!=legacy.acceptance_registry
    assert study.execution_policy!=legacy.execution_policy
    with pytest.raises(ValueError,match='no observed'):require_collection_freeze(study,registry_path=tmp_path/'registry.sqlite')
    registry=CashStudyRegistry(tmp_path/'registry.sqlite',clock=lambda:time(p['frozen_at']))
    registry.freeze(raw)
    assert require_collection_freeze(study,registry_path=registry.path)=='observed_prospective_collection_freeze'
    assert not study.root.exists()
