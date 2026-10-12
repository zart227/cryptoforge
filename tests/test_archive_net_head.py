from dataclasses import replace
from pathlib import Path
import json,shutil
from test_trade_simulator import history


def test_archive_net_head_preserves_fixed_budget_no_test_and_no_live_publication(tmp_path,monkeypatch):
    from scripts.evaluate_archive_net_head import main,ArchiveReader
    config=tmp_path/'config';config.mkdir()
    for name in ('net-regression-research-v2.json','net-regression-research-v2.sha256'):
        shutil.copy(Path('config')/name,config/name)
    protocol=json.loads((config/'net-regression-research-v2.json').read_bytes())
    monkeypatch.setattr('cryptoforge.research_protocol.prepare_research',lambda path:protocol)
    rows=history(count=1000)
    monkeypatch.setattr(ArchiveReader,'read_candles',lambda self,pair,**kwargs:[replace(row,pair=pair,symbol=pair.replace('/','')) for row in rows])
    monkeypatch.chdir(tmp_path);monkeypatch.setattr('sys.argv',['net-head'])
    main();path=tmp_path/'.local/state/archive-net-head-report.json';report=json.loads(path.read_bytes())
    assert len(report['results'])==3 and report['outer_test_evaluated'] is False
    assert report['historical_reserved_final_compatible'] is False and not report['live_promotion_allowed']
    assert report['train_count']>100 and report['validation_count']>100
    assert all(result['model']['live_eligible'] is False for result in report['results'])
    rows[850:]=[replace(row,open=-row.open) for row in rows[850:]]
    main();second=json.loads(path.read_bytes());second.pop('as_of');report.pop('as_of')
    assert second==report
