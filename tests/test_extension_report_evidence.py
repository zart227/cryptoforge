from datetime import datetime,UTC
from pathlib import Path
import pytest
from cryptoforge.strategy_extension_study import freeze_study,evaluate_candidate
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.extension_report_evidence import verify_extension_report
from test_trade_simulator import history


def fixture(tmp_path):
    ledger=ResearchAttempts(tmp_path/'ledger.sqlite');receipt=freeze_study(tmp_path,ledger);manifest=receipt['manifest']
    results=[]
    for candidate in manifest['grid']:
        started=datetime.now(UTC)
        result=evaluate_candidate({'ETH/USDT':history(count=180)},manifest,candidate)
        result.update(study_sha256=receipt['study_sha256'],execution_started_at=started.isoformat(),execution_finished_at=datetime.now(UTC).isoformat())
        ledger.record(receipt['study_sha256'],candidate,result);results.append(result)
    return {'manifest':manifest,'study_sha256':receipt['study_sha256'],'results':results,'completed_configurations':4},ledger.path


def test_complete_registered_extension_reports_are_verified_readonly(tmp_path):
    report,path=fixture(tmp_path);before=path.read_bytes()
    result=verify_extension_report(report,path)
    assert result['verified_configurations']==4 and path.read_bytes()==before
    assert not result['live_promotion_allowed']


def test_changed_or_partial_results_cannot_be_accepted_as_complete(tmp_path):
    report,path=fixture(tmp_path)
    report['results'][0]['roles']['filtered']['net_pnl']='1'
    with pytest.raises(ValueError,match='completed attempt'):verify_extension_report(report,path)
    report['results'].pop()
    with pytest.raises(ValueError,match='complete'):verify_extension_report(report,path)
