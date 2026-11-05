import json
from types import SimpleNamespace
from cryptoforge.strategy_extension_study import freeze_study
from cryptoforge.research_attempts import ResearchAttempts
import scripts.run_extension_study_job as module


def fixture(tmp_path):
    receipt=freeze_study(tmp_path,ResearchAttempts(tmp_path/'ledger.sqlite'))
    path=tmp_path/receipt['study_sha256']/'protocol.json';path.parent.mkdir();path.write_text(json.dumps(receipt))
    return path


def test_resource_deferral_does_not_count_as_completed_evaluation(tmp_path,monkeypatch):
    path=fixture(tmp_path)
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1,stderr='insufficient resources: defer research'))
    result=module.run(path)
    assert result['status']=='deferred_resource_or_worker_guard' and not result['completed']
    assert not path.with_name('results.json').exists()


def test_successful_process_without_grid_evidence_is_blocked(tmp_path,monkeypatch):
    path=fixture(tmp_path)
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stderr=''))
    result=module.run(path)
    assert result['status']=='blocked_contract_or_source' and not result['completed']
