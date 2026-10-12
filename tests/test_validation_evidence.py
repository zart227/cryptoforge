from datetime import UTC, datetime, timedelta
import json
import pytest
from cryptoforge.research_attempts import ResearchAttempts, identity
from cryptoforge.validation_evidence import select_registered_validation_reports
from cryptoforge.validation_threshold import select_validation_threshold
from cryptoforge.source_contract import source_hashes, assert_source_dependencies

NOW = datetime(2026,10,11,tzinfo=UTC)
START = NOW-timedelta(days=8)
END = NOW-timedelta(days=1)


def evidence(tmp_path, *, early=False, missing_sources=False):
    clock=[NOW]
    ledger=ResearchAttempts(tmp_path/'ledger.sqlite',clock=lambda:clock[0])
    policy=dict(validation_start=START.isoformat(),validation_end=END.isoformat(),
                minimum_trades=10,maximum_drawdown='.05')
    grid=[dict(family='threshold-test',threshold=value) for value in ('.5','.6')]
    manifest=dict(scope='validation_threshold_selection',grid=grid,selection_policy=policy,
        selection_source_hashes=source_hashes({'selector':select_validation_threshold,
            'evidence_verifier':select_registered_validation_reports,
            'source_guard':assert_source_dependencies}))
    if missing_sources:
        manifest.pop('selection_source_hashes')
    study=ledger.register(manifest,protocol_id='test',maximum_per_family=2)
    reports={}
    clock[0]=NOW+timedelta(seconds=3)
    for candidate in grid:
        payload=dict(candidate=candidate,study_sha256=study,role='validation',
            validation_start=START.isoformat(),validation_end=END.isoformat(),
            execution_started_at=(NOW+timedelta(seconds=-1 if early else 1)).isoformat(),
            execution_finished_at=(NOW+timedelta(seconds=2)).isoformat(),
            portfolio=dict(initial_cash=100,net_pnl=2,stress_net_pnl=1,
                           max_drawdown='.02',stress_max_drawdown='.03',trade_count=20,stress_trade_count=20))
        ledger.record(study,candidate,payload)
        path=tmp_path/(candidate['threshold']+'.json')
        path.write_text(json.dumps(payload))
        reports[identity(candidate)]=path
    return ledger.path,dict(study_sha256=study,reports=reports,
        validation_start=START,validation_end=END,minimum_trades=10,maximum_drawdown='.05')


def test_registered_evidence_is_verified_without_ledger_mutation(tmp_path):
    path,kwargs=evidence(tmp_path)
    before=path.read_bytes()
    result=select_registered_validation_reports(path,**kwargs)
    assert result['selected_threshold']=='0.6'
    assert result['registered_results_verified']
    assert result['report_checksums_verified_by_selector']
    assert path.read_bytes()==before


def test_changed_report_and_incomplete_grid_fail(tmp_path):
    path,kwargs=evidence(tmp_path)
    report=next(iter(kwargs['reports'].values()))
    payload=json.loads(report.read_text());payload['portfolio']['net_pnl']=100
    report.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='immutable'):
        select_registered_validation_reports(path,**kwargs)
    kwargs['reports'].pop(next(iter(kwargs['reports'])))
    with pytest.raises(ValueError,match='complete'):
        select_registered_validation_reports(path,**kwargs)


def test_backdated_execution_and_changed_selection_policy_fail(tmp_path):
    path,kwargs=evidence(tmp_path,early=True)
    with pytest.raises(ValueError,match='preregistration'):
        select_registered_validation_reports(path,**kwargs)
    kwargs['minimum_trades']=1
    with pytest.raises(ValueError,match='policy'):
        select_registered_validation_reports(path,**kwargs)


def test_legacy_manifest_without_original_selection_sources_is_rejected(tmp_path):
    path,kwargs=evidence(tmp_path,missing_sources=True)
    with pytest.raises(ValueError,match='source dependency'):
        select_registered_validation_reports(path,**kwargs)
