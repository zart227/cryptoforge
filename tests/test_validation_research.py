import json
from dataclasses import replace
from decimal import Decimal as D

from test_trade_simulator import history
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from scripts.audit_trade_labels import verify_trade
from scripts.search_validation_portfolio import main


def test_independent_audit_recomputes_outcomes():
    rows=history(count=100)
    rows[37]=replace(rows[37],high=D(105),low=D(97))
    config=SimulationConfig(hold_bars=3)
    labels=build_trade_labels('ETH/USDT',rows,config)
    for label in labels[:20]:
        verify_trade(label,rows,config)


def test_validation_search_ignores_outer_test_and_persists_protocol(monkeypatch,tmp_path):
    monkeypatch.setattr("cryptoforge.research_protocol.prepare_research",lambda: {'protocol_version':'synthetic-v1','search_limits':{'max_configurations_per_family':100}})
    monkeypatch.chdir(tmp_path)
    rows=history(count=1000)
    monkeypatch.setattr('scripts.search_validation_portfolio.ArchiveReader.read_candles',lambda *a,**k:rows)
    path=tmp_path/'report.json'
    monkeypatch.setattr('sys.argv',['search','--pair','ETH/USDT','--output',str(path)])
    main()
    first=json.loads(path.read_text())
    assert first['outer_test_evaluated'] is False
    assert first['live_eligible'] is False
    assert len(first['results'])==18
    assert path.with_suffix('.protocol.json').exists()
    # Deliberately corrupt unseen test prices: validation must remain identical.
    rows[850:]=[replace(c,open=D(-1),close=D(-1)) for c in rows[850:]]
    main()
    assert json.loads(path.read_text())==first


def test_repeated_search_restores_trials_without_reevaluating_them(monkeypatch,tmp_path):
    import scripts.search_validation_portfolio as script
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('cryptoforge.research_protocol.prepare_research',lambda:{'protocol_version':'synthetic-v1','search_limits':{'max_configurations_per_family':100}})
    rows=history(count=1000)
    monkeypatch.setattr(script.ArchiveReader,'read_candles',lambda *a,**k:rows)
    monkeypatch.setattr('sys.argv',['search','--pair','ETH/USDT','--output',str(tmp_path/'result.json')])
    original=script.simulate_portfolio;calls=[]
    def counted(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(script,'simulate_portfolio',counted)
    script.main();first=len(calls);script.main()
    assert first==37 and len(calls)==38  # repeat only validates the input grid


def test_rsi_dependency_change_invalidates_cached_study(monkeypatch,tmp_path):
    import scripts.search_validation_portfolio as script
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('cryptoforge.research_protocol.prepare_research',lambda:{'protocol_version':'synthetic-v1','search_limits':{'max_configurations_per_family':100}})
    rows=history(count=1000);path=tmp_path/'report.json'
    monkeypatch.setattr(script.ArchiveReader,'read_candles',lambda *a,**k:rows)
    monkeypatch.setattr('sys.argv',['search','--pair','ETH/USDT','--output',str(path)])
    script.main();first=json.loads(path.read_text())
    monkeypatch.setattr(script.strategy_module,'rsi',lambda values,period:D('50'))
    script.main();second=json.loads(path.read_text())
    assert first['research_study_sha256']!=second['research_study_sha256']
    assert first['implementation_hashes']['rsi_dependency']!=second['implementation_hashes']['rsi_dependency']
    assert second['effective_configuration_budget_usage']=={'trend':12,'breakout':12,'reversion':12}


def test_entry_conflict_filter_is_optional_and_does_not_read_future(monkeypatch):
    import scripts.search_validation_portfolio as script
    rows=history(count=200);seen=[]
    monkeypatch.setattr(script,'signal',lambda rows,index,spec:True)
    def exit_observation(window):seen.append(window);return True,['overbought']
    monkeypatch.setattr(script,'exit_signal',exit_observation)
    spec=script.StrategySpec('trend',12,.001)
    assert script.research_entry_allowed(rows,150,spec)
    assert not seen
    assert not script.research_entry_allowed(rows,150,spec,'no_exit_conflict')
    assert len(seen[0])==120 and seen[0][-1]==rows[150]
    rows[151:]=[replace(c,close=D('99999')) for c in rows[151:]]
    assert not script.research_entry_allowed(rows,150,spec,'no_exit_conflict')
    assert seen[0]==seen[1]


def test_conflict_study_has_paired_grid_and_preserves_hidden_test(monkeypatch,tmp_path):
    import scripts.search_validation_portfolio as script
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('cryptoforge.research_protocol.prepare_research',lambda:{'protocol_version':'synthetic-v1','search_limits':{'max_configurations_per_family':100}})
    rows=history(count=1000);path=tmp_path/'report.json'
    monkeypatch.setattr(script.ArchiveReader,'read_candles',lambda *a,**k:rows)
    monkeypatch.setattr('sys.argv',['search','--pair','ETH/USDT','--entry-conflict-study','--output',str(path)])
    script.main();report=json.loads(path.read_text())
    assert len(report['results'])==36 and report['outer_test_evaluated'] is False
    assert {r['parameters']['entry_filter'] for r in report['results']}=={None,'no_exit_conflict'}
