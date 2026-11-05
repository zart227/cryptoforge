"""Accounting integration with disposable synthetic journals and datasets."""
from copy import deepcopy
import sqlite3

import pytest

from cryptoforge import research_phase as phase, training_fit_reuse_budget as adapter
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.research_training_diagnostics import digest
from test_research_phase import migrated
from test_training_fit_reuse import EVIDENCE, inputs


def fixture(tmp_path, *, maximum=12, policy=None, initialize=True):
    budget, _, _ = migrated(tmp_path, **({'policy': policy} if policy is not None else {}))
    research = phase.PhaseResearchCoordinator.__new__(phase.PhaseResearchCoordinator)
    research.budget = budget
    research.paths = {'fit':tmp_path/'fit.sqlite', 'proposal':tmp_path/'proposal.sqlite',
        'semantic_fixture':tmp_path/'semantic_fixture.sqlite'}
    data, protocol, configs = inputs(tmp_path); protocol['maximum_per_family'] = maximum
    dataset = tmp_path/'development.json'
    if initialize:
        ledger = ResearchAttempts(research.paths['fit']); db = ledger._db()
        with db:
            db.execute('INSERT INTO budgets VALUES (?,?)', (digest(protocol), maximum))
            db.execute('INSERT INTO protocol_versions VALUES (?,?)', (protocol['version'], digest(protocol)))
        db.close()
    return research, dataset, protocol, configs


def execute(research, dataset, protocol, configs, **kwargs):
    return adapter._run_existing(research, dataset, protocol, configs, evidence_context=EVIDENCE,
        _allow_unqualified_fresh=True, **kwargs)


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute('SELECT status,count(*) FROM attempts GROUP BY status').fetchall()


def test_seven_native_effects_reserve_both_journals_before_one_worker_and_cache(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path); real = adapter.worker.run; calls = []
    def run(*a, **k):
        snap = research.budget.snapshot()
        assert snap['reserved_by_kind']['fit'] == 8  # one older synthetic action plus seven
        assert rows(research.paths['fit']) == [('reserved', 7)]
        assert len(list(tmp_path.glob('fit.sqlite.*.claim'))) == 7
        calls.append(1); return real(*a, **k)
    monkeypatch.setattr(adapter.worker, 'run', run)
    result = execute(research, dataset, protocol, configs)
    assert calls == [1] and result['fresh_logical_evaluations'] == 7
    assert result['batch_worker']['worker']['result']['actual_counts']['long_head_fits'] == 4
    assert sum(c['original_observed']['numeric_fits'] for c in result['calls']) == 4
    assert rows(research.paths['fit']) == [('completed', 7)]
    assert research.budget.snapshot()['reserved_by_kind']['fit'] == 8
    assert not result['new_limits_or_refunds'] and not result['study_approved']
    for config, call in zip(configs, result['calls'], strict=True):
        inputs = {'dataset_sha256':protocol['dataset_sha256'],'protocol_sha256':digest(protocol),'config':config}
        assert call['operation_key'] == research.budget._key('fit', research._identity(inputs), 0)
    again = execute(research, dataset, protocol, configs)
    assert calls == [1] and again['cached_logical_evaluations'] == 7 and again['batch_worker'] is None
    assert all(c['coordinator_cached'] and c['invocation_observed'] == phase.common.ZERO_USAGE for c in again['calls'])
    assert research.budget.snapshot()['reserved_by_kind']['fit'] == 8


def test_old_native_baseline_cache_and_six_fresh_configurations_share_worker(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path)
    baseline = research.fit(dataset, protocol)
    real = adapter.worker.run; batches = []
    def run(data, protocol, configs, **kwargs): batches.append(deepcopy(configs)); return real(data, protocol, configs, **kwargs)
    monkeypatch.setattr(adapter.worker, 'run', run)
    result = execute(research, dataset, protocol, configs)
    assert result['calls'][0]['coordinator_cached']
    assert result['legacy_cache_without_fit_reuse_context'] == 1
    assert result['calls'][0]['result']['artifact_sha256'] == baseline['result']['artifact_sha256']
    assert result['fresh_logical_evaluations'] == 6 and len(batches) == 1 and len(batches[0]) == 6
    assert result['batch_worker']['worker']['result']['actual_counts']['long_head_fits'] == 4
    assert rows(research.paths['fit']) == [('completed', 7)]


def test_common_exhaustion_never_reaches_inner_reservation_or_worker(tmp_path, monkeypatch):
    policy = deepcopy(phase.common.DEFAULT_POLICY); policy['maximum_by_kind']['fit'] = 2
    research, dataset, protocol, configs = fixture(tmp_path, policy=policy)
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('common admission must finish first'))
    with pytest.raises(RuntimeError): execute(research, dataset, protocol, configs)
    assert rows(research.paths['fit']) == [] and not list(tmp_path.glob('*.claim'))
    snapshot = research.budget.snapshot()
    assert snapshot['reserved_by_kind']['fit'] == 2 and snapshot['statuses']['failed'] == 1
    with pytest.raises(ValueError, match='no automatic retry'): execute(research, dataset, protocol, configs)


def test_inner_exhaustion_keeps_common_charges_and_claims_without_worker(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path, maximum=2)
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('inner budget must finish first'))
    with pytest.raises(RuntimeError): execute(research, dataset, protocol, configs)
    assert rows(research.paths['fit']) == [('failed', 2)]
    assert len(list(tmp_path.glob('fit.sqlite.*.claim'))) == 7
    assert research.budget.snapshot()['reserved_by_kind']['fit'] == 8
    with pytest.raises(ValueError, match='no automatic retry'): execute(research, dataset, protocol, configs)


@pytest.mark.parametrize('missing', ['journal', 'budget', 'version'])
def test_missing_journal_or_original_protocol_cannot_initialize_or_reserve(tmp_path, monkeypatch, missing):
    research, dataset, protocol, configs = fixture(tmp_path, initialize=missing != 'journal')
    if missing != 'journal':
        with sqlite3.connect(research.paths['fit']) as db:
            db.execute('DELETE FROM '+('budgets' if missing == 'budget' else 'protocol_versions'))
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('not admitted'))
    before = research.budget.path.read_bytes()
    with pytest.raises(ValueError): execute(research, dataset, protocol, configs)
    assert research.budget.path.read_bytes() == before and not list(tmp_path.glob('*.claim'))
    if missing == 'journal': assert not research.paths['fit'].exists()


@pytest.mark.parametrize('status', ['reserved', 'failed', 'completed'])
def test_inner_history_without_matching_common_cache_requires_reconciliation(tmp_path, monkeypatch, status):
    research, dataset, protocol, configs = fixture(tmp_path)
    data, _ = adapter.planner.load_development(dataset); candidate, manifest = adapter._manifest(data, protocol, configs[0])
    ledger = ResearchAttempts(research.paths['fit']); study = ledger.register(manifest, protocol_id=digest(protocol),
        maximum_per_family=protocol['maximum_per_family'],protocol_version=protocol['version'])
    if status != 'reserved': ledger.record(study,candidate,{'status':status},failed=status=='failed')
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('unreconciled history'))
    before = research.budget.path.read_bytes()
    with pytest.raises(ValueError, match='reconciliation'): execute(research, dataset, protocol, configs)
    assert research.budget.path.read_bytes() == before


@pytest.mark.parametrize('error,expected', [(ValueError, 'failed'), (phase.common.BudgetTimedOut, 'timed_out'),
    (phase.common.BudgetCancelled, 'cancelled')])
def test_worker_failure_keeps_both_journals_charged_and_no_retry(tmp_path, monkeypatch, error, expected):
    research, dataset, protocol, configs = fixture(tmp_path)
    def fail(*a, **k): raise error('synthetic private failure')
    monkeypatch.setattr(adapter.worker, 'run', fail)
    with pytest.raises(RuntimeError): execute(research, dataset, protocol, configs)
    assert rows(research.paths['fit']) == [('failed', 7)]
    assert research.budget.snapshot()['statuses'][expected] == 7
    assert b'synthetic private failure' not in research.budget.path.read_bytes()
    with pytest.raises(ValueError, match='no automatic retry'): execute(research, dataset, protocol, configs)


def test_existing_claim_without_row_blocks_before_common_reservation(tmp_path):
    research, dataset, protocol, configs = fixture(tmp_path)
    data, _ = adapter.planner.load_development(dataset); _, manifest = adapter._manifest(data, protocol, configs[0])
    claim = tmp_path/('fit.sqlite.'+adapter.identity(manifest)+'.claim'); claim.write_text('interrupted')
    before = research.budget.path.read_bytes()
    with pytest.raises(ValueError, match='prior_claim'): execute(research, dataset, protocol, configs)
    assert research.budget.path.read_bytes() == before and rows(research.paths['fit']) == []


def test_inconsistent_inner_and_common_completed_results_are_rejected(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path); execute(research, dataset, protocol, configs[:1])
    with sqlite3.connect(research.paths['fit']) as db: db.execute("UPDATE attempts SET payload='{}'")
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('damaged cache cannot refit'))
    before = research.budget.path.read_bytes()
    with pytest.raises((ValueError,KeyError)): execute(research, dataset, protocol, configs[:1])
    assert research.budget.path.read_bytes() == before


def test_invalid_batch_and_pre_cancel_do_not_reserve(tmp_path, monkeypatch):
    import threading
    research, dataset, protocol, configs = fixture(tmp_path); before = research.budget.path.read_bytes()
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('invalid batch cannot execute'))
    with pytest.raises(ValueError): execute(research, dataset, protocol, [configs[0], configs[0]])
    cancelled = threading.Event(); cancelled.set()
    with pytest.raises(phase.common.BudgetCancelled): execute(research, dataset, protocol, configs, cancel_event=cancelled)
    assert research.budget.path.read_bytes() == before and rows(research.paths['fit']) == []


def test_public_entry_refuses_fresh_work_without_reservation_but_can_read_cache(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path); before = research.budget.path.read_bytes()
    with monkeypatch.context() as guard:
        guard.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('public path is cache only'))
        with pytest.raises(ValueError, match='fresh_fit_disabled'):
            adapter.run_existing(research, dataset, protocol, configs[:1], evidence_context=EVIDENCE)
    assert research.budget.path.read_bytes() == before and rows(research.paths['fit']) == []
    execute(research, dataset, protocol, configs[:1]); before = research.budget.path.read_bytes()
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('public cache cannot refit'))
    cached = adapter.run_existing(research, dataset, protocol, configs[:1], evidence_context=EVIDENCE)
    assert cached['cached_logical_evaluations'] == 1 and cached['batch_worker'] is None
    assert research.budget.path.read_bytes() == before


def test_cache_context_change_is_rejected_without_new_model_work(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path); execute(research, dataset, protocol, configs[:1])
    before = research.budget.path.read_bytes()
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('context change cannot refit'))
    with pytest.raises(ValueError, match='context_changed'):
        adapter.run_existing(research, dataset, protocol, configs[:1], evidence_context={**EVIDENCE,'raw_source_manifest_sha256':'f'*64})
    assert research.budget.path.read_bytes() == before


def test_process_exit_leaves_reservations_and_claims_immutable(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path)
    def crash(*a, **k): raise SystemExit(3)
    monkeypatch.setattr(adapter.worker, 'run', crash)
    with pytest.raises(SystemExit): execute(research, dataset, protocol, configs)
    assert rows(research.paths['fit']) == [('reserved', 7)]
    assert research.budget.snapshot()['statuses']['reserved'] == 7
    assert len(list(tmp_path.glob('fit.sqlite.*.claim'))) == 7
    with pytest.raises(ValueError, match='no automatic retry'): execute(research, dataset, protocol, configs)


def test_effect_in_different_native_study_cannot_be_recomputed(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path)
    data, _ = adapter.planner.load_development(dataset)
    candidate, manifest = adapter._manifest(data, protocol, configs[0])
    second, _ = adapter._manifest(data, protocol, configs[1])
    manifest['grid'] = [candidate, second]
    ResearchAttempts(research.paths['fit']).register(manifest, protocol_id=digest(protocol),
        maximum_per_family=protocol['maximum_per_family'],protocol_version=protocol['version'])
    before = research.budget.path.read_bytes()
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('duplicate effect cannot refit'))
    with pytest.raises(ValueError, match='other_study'): execute(research, dataset, protocol, configs)
    assert research.budget.path.read_bytes() == before


def test_partial_inner_record_failure_keeps_completed_and_failed_history(tmp_path, monkeypatch):
    research, dataset, protocol, configs = fixture(tmp_path); original = adapter.ExistingAttempts.record; count = []
    def interrupted(self, study, candidate, payload, *, failed=False):
        if not failed:
            count.append(1)
            if len(count) == 3: raise OSError('synthetic disk failure')
        return original(self, study, candidate, payload, failed=failed)
    monkeypatch.setattr(adapter.ExistingAttempts, 'record', interrupted)
    with pytest.raises(RuntimeError): execute(research, dataset, protocol, configs)
    assert sorted(rows(research.paths['fit'])) == [('completed', 2), ('failed', 5)]
    assert research.budget.snapshot()['statuses']['failed'] == 7
    with pytest.raises(ValueError, match='no automatic retry'): execute(research, dataset, protocol, configs)


def test_native_proposal_fit_reuses_batch_result_under_original_effect_key(tmp_path, monkeypatch):
    from test_llm_training_experiments import proposal
    research, dataset, protocol, configs = fixture(tmp_path)
    baseline = research.fit(dataset, protocol)
    config = next(c for c in configs if c == {'l2': .1, 'threshold': .6})
    batch = execute(research, dataset, protocol, [config]); saved = batch['calls'][0]
    before = research.budget.snapshot()['total_reserved_actions']
    monkeypatch.setattr(adapter.worker, 'run', lambda *a, **k: pytest.fail('native cache must not launch batch'))
    monkeypatch.setattr(adapter.planner, 'execute_fit', lambda *a, **k: pytest.fail('native cache must not refit'))
    native = research.fit(dataset, protocol, proposal=proposal(),
        report=baseline['result']['reports']['validation']['diagnostics'])
    assert native['coordinator_cached'] and native['operation_key'] == saved['operation_key']
    assert native['result']['artifact_sha256'] == saved['result']['artifact_sha256']
    assert native['invocation_observed'] == phase.common.ZERO_USAGE
    assert research.budget.snapshot()['total_reserved_actions'] == before
