from dataclasses import asdict
from datetime import timedelta
import hashlib,json
from pathlib import Path
from scripts import evaluate_net_portfolio as runner
from cryptoforge.net_regression import NetRegressor
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.trade_simulator import SimulationConfig
import cryptoforge.research_protocol as protocol_module
from test_trade_simulator import history


def test_registered_runner_exports_symmetric_stress_and_reuses_results(tmp_path,monkeypatch,capsys):
    # Synthetic orchestration test; archive/resource/model receipts are fixtures.
    monkeypatch.chdir(tmp_path)
    rows=history(count=80)
    cfg=SimulationConfig()
    model=asdict(NetRegressor((0.,)*7,(1.,)*7,(0.,)*7,0.,'spot-long-trade-net-v2',.01))
    ranges={'ETH/USDT':{'validation_start':rows[40].open_time.isoformat(),
                       'development_end':(rows[-1].open_time+timedelta(minutes=5)).isoformat()}}
    digest=hashlib.sha256(json.dumps([asdict(row) for row in rows],default=str,sort_keys=True).encode()).hexdigest()
    source={'protocol_sha256':'a'*64,'study_sha256':'b'*64,'implementation_hashes':{},
        'results':[{'parameters':{'ridge':'.01'},'model':model}],'selected_ridge':'.01',
        'base_config':json.loads(json.dumps(asdict(cfg),default=str)),
        'ranges':ranges,'dataset_sha256':{'ETH/USDT':digest}}
    protocol={'protocol_version':'synthetic-paired-v1','baseline_pairs':['ETH/USDT'],
        'net_head_policy':{'max_candles_per_pair':2000},'portfolio_diagnostic_policy':{
            'source_net_protocol_sha256':'a'*64,'source_net_study_sha256':'b'*64,
            'net_entry_threshold':'0','live_promotion_allowed':False,
            'frozen_model_sha256':hashlib.sha256(json.dumps(model,sort_keys=True).encode()).hexdigest(),
            'scope':'synthetic-development-orchestration'}}
    Path('config').mkdir();Path('.local/state').mkdir(parents=True)
    path=Path('config/net-portfolio-diagnostic-v2.json')
    path.write_text(json.dumps(protocol))
    path.with_suffix('.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    Path('.local/state/archive-net-head-report.json').write_text(json.dumps(source))
    monkeypatch.setattr(protocol_module,'prepare_research',lambda path:protocol)
    monkeypatch.setattr(runner,'assert_source_dependencies',lambda *args:{})
    class Reader:
        def __init__(self,*args,**kwargs):pass
        def read_candles(self,*args,**kwargs):return rows
    monkeypatch.setattr(runner,'ArchiveReader',Reader)
    original=runner.compare_filtered_portfolios;calls=[]
    def compare(*args,**kwargs):
        ledger=ResearchAttempts(Path('.local/state/research-attempts.sqlite'))
        assert ledger.budget_usage(hashlib.sha256(path.read_bytes()).hexdigest())=={'frozen-net-portfolio':1}
        calls.append(1)
        return original(*args,**kwargs)
    monkeypatch.setattr(runner,'compare_filtered_portfolios',compare)
    runner.main();capsys.readouterr()
    first=json.loads(Path('.local/state/net-portfolio-diagnostic.json').read_text())
    assert set(first['roles'])=={'candidate','baseline_all_bar','stress_candidate','stress_baseline_all_bar'}
    assert 'stress_filtered_minus_baseline' in first['paired_differences']
    assert first['roles']['candidate']['no_trade_sample']
    assert not first['live_promotion_allowed']
    runner.main();capsys.readouterr()
    second=json.loads(Path('.local/state/net-portfolio-diagnostic.json').read_text())
    assert len(calls)==1
    assert first['roles']==second['roles'] and first['paired_differences']==second['paired_differences']
