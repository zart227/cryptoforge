import hashlib,json
from pathlib import Path
from scripts import backtest_archive_portfolio as replay


def test_fixed_replay_is_registered_and_repeated_result_is_not_recalculated(tmp_path,monkeypatch):
    import cryptoforge.research_protocol as research
    monkeypatch.chdir(tmp_path)
    source=tmp_path/'ETHUSDT-5.json'
    rows=[{'symbol':'ETHUSDT','interval':'5','start_ms':1767225600000+i*300000,'open':'100','high':'101','low':'99','close':'100','volume':'1000','turnover':'100000'} for i in range(200)]
    source.write_text(json.dumps(rows))
    protocol=json.loads((Path(__file__).resolve().parents[1]/'config/research-protocol-v1.json').read_bytes())
    protocol['datasets']=[{'pair':'ETH/USDT','path':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}]
    monkeypatch.setattr(research,'prepare_research',lambda:protocol)
    calls=[];original=replay.simulate_portfolio
    def track(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(replay,'simulate_portfolio',track)
    output=tmp_path/'replay.json'
    argv=['--pair','ETH/USDT','--directory',str(tmp_path),'--max-candles','200','--detailed-equity','--output',str(output)]
    replay.main(argv);first=output.read_bytes()
    report=json.loads(first)
    assert report['research_study_sha256'] and report['summary']['live_eligible'] is False
    assert len(report['result']['equity_snapshots'])==200
    replay.main(argv)
    assert output.read_bytes()==first and len(calls)==1
