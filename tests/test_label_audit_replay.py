from dataclasses import asdict
from pathlib import Path
import json,pytest
from scripts.replay_label_audit import replay_report
from cryptoforge.source_contract import net_research_sources,source_hashes
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw
from cryptoforge.trade_labels import build_trade_labels
from cryptoforge.trade_simulator import SimulationConfig
from test_trade_simulator import history


def fixture(tmp_path):
    cfg=SimulationConfig();rows=history(count=100);label=build_trade_labels('ETH/USDT',rows,cfg)[0]
    used=[row for row in rows if label.signal_time<=row.open_time<=label.trade.exit_time]
    encode=lambda value:json.dumps(value,sort_keys=True,default=str).encode()
    ref=_save_raw(tmp_path,encode([asdict(row) for row in used]))
    deps=net_research_sources('label_builder',build_trade_labels,runner=Path(__file__).resolve().parents[1]/'scripts/audit_trade_labels.py')
    hashes=source_hashes(deps)
    report={'config':asdict(cfg),'implementation_hashes':hashes,'runtime_source_bundle':save_runtime_sources(tmp_path,deps,hashes),
        'pairs':[{'pair':label.pair,'audited_samples':1,'samples':[asdict(label)],'sample_source_references':[{'pair':label.pair,
            'signal_time':label.signal_time.isoformat(),'input_sha256':ref['sha256'],'input_reference':ref}]}]}
    path=tmp_path/'report.json';path.write_bytes(encode(report))
    return path


def test_source_case_replay_preserves_report_without_claiming_manual_review(tmp_path):
    path=fixture(tmp_path);before=path.read_bytes();result=replay_report(path)
    assert result['replayed_cases']==1 and path.read_bytes()==before
    assert not result['manual_review_completed'] and not result['historical_execution_certified']


def test_changed_saved_outcome_is_detected_against_original_window(tmp_path):
    path=fixture(tmp_path);report=json.loads(path.read_bytes())
    report['pairs'][0]['samples'][0]['trade']['ambiguous']=True
    path.write_text(json.dumps(report))
    with pytest.raises(AssertionError):replay_report(path)


def test_wrong_trade_market_cannot_use_matching_other_pair_prices(tmp_path):
    path=fixture(tmp_path);report=json.loads(path.read_bytes())
    report['pairs'][0]['samples'][0]['trade']['pair']='BTC/USDT'
    path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='market identity'):replay_report(path)
