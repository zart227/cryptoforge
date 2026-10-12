import json
from datetime import datetime
from pathlib import Path
import pytest
from unittest.mock import Mock

from cryptoforge.research_protocol import validate_protocol,assert_development_range,assert_resources,assert_executor_compatible


def protocol():
    return json.loads(Path('config/research-protocol-v1.json').read_text())


def test_frozen_protocol_ranges_and_resource_gate():
    p=protocol();validate_protocol(p)
    end=datetime.fromisoformat(p['data_policy']['development_end'])
    assert_development_range(p,end,end)
    with pytest.raises(ValueError,match='development'):
        reserved=datetime.fromisoformat(p['data_policy']['final_reserved_start'])
        assert_development_range(p,reserved,reserved)
    with pytest.raises(ValueError,match='resources'):
        assert_resources(p,100,10000)
    with pytest.raises(ValueError,match='resources'):
        assert_resources(p,10000,100)
    assert_resources(p,10000,10000)


def test_archive_trade_target_incompatible_with_current_executor():
    artifact={'feature_version':'candle-v1','threshold':0.5,
              'config':{'timeframe':'5m','horizon_candles':3,'target_version':'spot-long-trade-net-v1'}}
    with pytest.raises(ValueError,match='incompatible'):
        assert_executor_compatible(artifact,feature_version='candle-v1',timeframe='5m',
                                   horizon=3,threshold=0.5,target_version='fixed-future-return-v1')


def test_exit_does_not_call_failed_model_registry():
    from test_executor_exit_minimum import make_executor
    executor,bybit,now=make_executor(holding='0.06')
    registry=Mock();registry.latest.side_effect=RuntimeError('research unavailable')
    executor.active_model_registry=registry;executor.ml_mode='gate'
    decision=executor.run_once('HYPE/USDT',live=True,now=now)
    assert decision.decision=='approve_exit'
    registry.latest.assert_not_called()


def test_worker_limits_and_exclusive_lock(monkeypatch,tmp_path):
    import hashlib
    import resource
    import signal
    import os
    from cryptoforge.research_protocol import prepare_research
    p=protocol()
    dataset=tmp_path/'dataset.json';dataset.write_text('[]')
    p['datasets']=[{'pair':'BTC/USDT','path':str(dataset),'sha256':hashlib.sha256(dataset.read_bytes()).hexdigest()}]
    path=tmp_path/'protocol.json';path.write_text(json.dumps(p))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('cryptoforge.research_protocol.assert_resources',lambda *a:None)
    calls=[]
    monkeypatch.setattr(resource,'setrlimit',lambda key,value:calls.append((key,value)))
    monkeypatch.setattr(signal,'signal',lambda *a:None)
    monkeypatch.setattr(signal,'alarm',lambda *a:None)
    monkeypatch.setattr(os,'nice',lambda *a:None)
    prepare_research(str(path))
    assert {key for key,value in calls}=={resource.RLIMIT_AS,resource.RLIMIT_FSIZE}
    with pytest.raises(ValueError,match='another offline'):
        prepare_research(str(path))
