from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading

import pytest

from cryptoforge import research_code_budget as code, research_code_preview as preview
from cryptoforge import research_run_budget as common
from cryptoforge.research_resource_budget import DEFAULT_RESOURCES, ZERO_TOKENS
from cryptoforge.research_semantic_budget import DEFAULT_SEMANTIC_POLICY
from cryptoforge.training_diagnostics import canonical, digest
from test_research_run_budget import bindings, envelope
from test_research_code_preview import proposal, PATCH


def base(tmp_path, *, semantic=True, configured=False, **kwargs):
    return common.ResearchRunBudget(tmp_path / 'common.sqlite', bindings(tmp_path),
        **({'semantic_live_ledger': tmp_path / 'live.sqlite',
            'semantic_live_policy': deepcopy(DEFAULT_SEMANTIC_POLICY)} if semantic else {}),
        **({'code_check_policy': deepcopy(code.POLICY)} if configured else {}), **kwargs)


def initialized(tmp_path, **kwargs):
    initial = base(tmp_path, semantic=False, **kwargs)
    initial.run('fit', {'initial': True}, lambda: envelope('fit'))
    base(tmp_path, **kwargs).migrate_semantic_budget()
    return base(tmp_path, configured=True, **kwargs)


def migrated(tmp_path, **kwargs):
    budget = initialized(tmp_path, **kwargs); code.migrate(budget)
    return budget


def bundle(tmp_path, name='preview', item=None):
    directory = tmp_path / name
    preview.stage_preview(directory, proposal() if item is None else item, preview.POLICY)
    return directory


def history(path):
    with sqlite3.connect(path) as db:
        return {table: code.history_digest(db, table) for table in code.HISTORY_TABLES}


def test_migration_is_additive_atomic_idempotent_and_creates_no_inner_journal(tmp_path):
    budget = initialized(tmp_path)
    old = base(tmp_path)
    old.run('semantic_live', {}, lambda: {'result': {'origin': 'synthetic_accounting'},
        'observed': dict(common.ZERO_USAGE)}, questions=3)
    before = history(budget.path); snapshot = old.snapshot()
    result = code.migrate(budget)
    assert not result['already_migrated'] and not result['action_reserved']
    assert result['extension']['migration']['prior_action_count'] == 2
    assert result['extension']['migration']['prior_tables_sha256'] == before
    assert history(budget.path) == before
    after = budget.snapshot()
    assert after['total_reserved_actions'] == 2 and after['reserved_semantic_questions'] == 3
    assert after['resources'] == snapshot['resources'] and after['manifest'] == snapshot['manifest']
    assert after['schema_version'] == 'coordinated-research-budget-snapshot-v3'
    raw = budget.path.read_bytes()
    assert code.migrate(budget)['already_migrated'] and budget.path.read_bytes() == raw
    assert not (tmp_path / 'live.sqlite').exists()
    assert all(not path.exists() for path in bindings(tmp_path).values())
    with pytest.raises(ValueError, match='explicit code policy'): old.snapshot()
    with pytest.raises(ValueError, match='explicit code policy'):
        old.run('fit', {'new': True}, lambda: pytest.fail('unconfigured writer'))
    assert budget.path.read_bytes() == raw


def test_code_configuration_never_creates_or_implicitly_migrates_a_journal(tmp_path):
    budget = base(tmp_path, configured=True)
    with pytest.raises(ValueError, match='existing'): code.migrate(budget)
    with pytest.raises(ValueError, match='existing'):
        budget.run('code_check', {}, lambda: pytest.fail('missing journal'))
    assert not budget.path.exists()
    budget = initialized(tmp_path); before = budget.path.read_bytes()
    with pytest.raises(ValueError, match='explicit code budget migration'): budget.snapshot()
    with pytest.raises(ValueError, match='explicit code budget migration'):
        code.check_preview(budget, bundle(tmp_path))
    assert budget.path.read_bytes() == before


def test_migration_requires_v2_and_complete_resource_accounting(tmp_path):
    old = base(tmp_path, semantic=False); old.run('fit', {}, lambda: envelope('fit'))
    raw = old.path.read_bytes()
    with pytest.raises(ValueError): code.migrate(base(tmp_path, configured=True))
    assert old.path.read_bytes() == raw
    base(tmp_path).migrate_semantic_budget()
    with sqlite3.connect(old.path) as db: db.execute('DROP TABLE coordinated_resources')
    raw = old.path.read_bytes()
    with pytest.raises(ValueError): code.migrate(base(tmp_path, configured=True))
    assert old.path.read_bytes() == raw


def test_effect_cache_survives_exhaustion_copies_and_rewording_with_original_provenance(tmp_path):
    limits = {**common.DEFAULT_POLICY, 'total_actions': 2}
    budget = migrated(tmp_path, policy=limits)
    first = code.check_preview(budget, bundle(tmp_path))
    item = proposal(); item['hypothesis'] = 'Another wording'; item['evidence_ids'] = ['b' * 64]
    other = bundle(tmp_path, 'copy', item)
    cached = code.check_preview(budget, other)
    assert first['operation_key'] == cached['operation_key'] and cached['coordinator_cached']
    assert first['result'] == cached['result']
    assert cached['current_preview_sha256'] != cached['result']['preview_sha256']
    assert cached['current_preview_revalidated'] and not cached['admission_is_execution_permission']
    assert cached['invocation_resources']['handler_wall_ms'] == 0
    assert cached['invocation_resources']['tokens'] == ZERO_TOKENS
    assert cached['result']['attempt_budget_reserved'] and not cached['result']['candidate_execution_budget_reserved']
    assert not cached['result']['candidate_executed'] and not cached['result']['syntax_checked']
    snapshot = budget.snapshot()
    assert snapshot['reserved_by_kind'] == {'fit': 1, 'code_check': 1}
    assert snapshot['resources']['reserved_allocations'] == {'input_tokens': 0, 'output_tokens': 0, 'wall_ms': 30000}
    assert snapshot['observed_completed_work'] == common.ZERO_USAGE
    with pytest.raises(ValueError, match='common research action budget'):
        budget.run('fit', {'new': True}, lambda: pytest.fail('common exhaustion'))


@pytest.mark.parametrize('exception,status', [(RuntimeError, 'failed'), (common.BudgetCancelled, 'cancelled'),
    (KeyboardInterrupt, 'cancelled'), (common.BudgetTimedOut, 'timed_out'), (SystemExit, 'reserved')])
def test_failure_cancel_timeout_and_process_exit_keep_all_reservations_and_block_retry(tmp_path, exception, status):
    budget = migrated(tmp_path)
    def fail(): raise exception('private candidate contents')
    with pytest.raises((RuntimeError, SystemExit)):
        budget.run('code_check', {'candidate': 'one'}, fail)
    snapshot = budget.snapshot()
    assert snapshot['statuses'] == {'completed': 1, status: 1}
    assert snapshot['resources']['reserved_allocations']['wall_ms'] == 30000
    assert snapshot['resources']['unknown_token_actions_by_field'] == ZERO_TOKENS
    raw = budget.path.read_bytes()
    with pytest.raises(ValueError, match='no automatic retry'):
        base(tmp_path, configured=True).run('code_check', {'candidate': 'one'}, lambda: pytest.fail('retry'))
    assert budget.path.read_bytes() == raw
    with sqlite3.connect(budget.path) as db:
        assert 'private candidate contents' not in repr(db.execute('SELECT * FROM coordinated_actions').fetchall())


@pytest.mark.parametrize('exception', [RuntimeError, common.BudgetCancelled, common.BudgetTimedOut])
def test_prior_failures_are_preserved_and_charged_by_migration(tmp_path, exception):
    initial = base(tmp_path, semantic=False)
    def fail(): raise exception('private')
    with pytest.raises(RuntimeError): initial.run('proposal', {}, fail)
    base(tmp_path).migrate_semantic_budget()
    before = history(initial.path)
    budget = base(tmp_path, configured=True); code.migrate(budget)
    assert history(initial.path) == before and budget.snapshot()['total_reserved_actions'] == 1


def test_unfinished_common_work_blocks_migration_without_repair_or_refund(tmp_path):
    configured = initialized(tmp_path)
    def crash(): raise SystemExit('unfinished')
    with pytest.raises(SystemExit): base(tmp_path).run('fit', {'second': True}, crash)
    before = configured.path.read_bytes()
    with pytest.raises(ValueError, match='unfinished'): code.migrate(configured)
    assert configured.path.read_bytes() == before


def test_migration_refuses_running_handler_until_terminal_commit(tmp_path):
    configured = initialized(tmp_path); started, release = threading.Event(), threading.Event()
    def operation():
        started.set(); assert release.wait(timeout=5); return envelope('fit')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(base(tmp_path).run, 'fit', {'second': True}, operation)
        try:
            assert started.wait(timeout=5)
            with pytest.raises(ValueError, match='unfinished'): code.migrate(configured)
        finally: release.set()
        future.result(timeout=5)
    assert not code.migrate(configured)['already_migrated']


def test_concurrent_migrations_add_one_record_and_never_change_prior_rows(tmp_path):
    configured = initialized(tmp_path); before = history(configured.path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(code.migrate, base(tmp_path, configured=True)) for _ in range(2)]
        assert sorted(f.result(timeout=5)['already_migrated'] for f in futures) == [False, True]
    assert history(configured.path) == before


def test_interrupted_migration_rolls_back_ddl_and_record_together(tmp_path, monkeypatch):
    budget = initialized(tmp_path); raw = budget.path.read_bytes()
    original = code.check_extension
    def interrupted(*args, **kwargs):
        result = original(*args, **kwargs); raise SystemExit('interrupted')
    monkeypatch.setattr(code, 'check_extension', interrupted)
    with pytest.raises(SystemExit): code.migrate(budget)
    assert budget.path.read_bytes() == raw
    monkeypatch.setattr(code, 'check_extension', original)
    assert base(tmp_path).snapshot()['total_reserved_actions'] == 1


@pytest.mark.parametrize('sql', ["UPDATE coordinated_actions SET payload='{}'",
    "UPDATE coordinated_actions SET status='unknown'", "UPDATE coordinated_actions SET questions=-1",
    "UPDATE coordinated_actions SET kind='code_check'", 'DELETE FROM coordinated_resources',
    "UPDATE coordinated_semantic_extension SET payload='{}'",
    'CREATE TRIGGER foreign_trigger AFTER UPDATE ON coordinated_actions BEGIN SELECT 1; END'])
def test_corrupt_history_is_rejected_without_migration_or_repair(tmp_path, sql):
    budget = initialized(tmp_path)
    with sqlite3.connect(budget.path) as db: db.execute(sql)
    raw = budget.path.read_bytes()
    with pytest.raises((ValueError, KeyError)): code.migrate(budget)
    assert budget.path.read_bytes() == raw


@pytest.mark.parametrize('sql', ["UPDATE coordinated_code_extension SET payload='{}'",
    'DELETE FROM coordinated_code_extension', 'DROP TABLE coordinated_resources'])
def test_corrupt_extension_blocks_status_and_fresh_work(tmp_path, sql):
    budget = migrated(tmp_path)
    with sqlite3.connect(budget.path) as db: db.execute(sql)
    raw = budget.path.read_bytes()
    with pytest.raises(ValueError): budget.snapshot()
    with pytest.raises(ValueError): budget.run('fit', {'new': True}, lambda: pytest.fail('corrupt'))
    assert budget.path.read_bytes() == raw


@pytest.mark.parametrize('field,value', [('maximum_actions', 4), ('wall_ms', 6000), ('input_tokens', 1),
    ('candidate_execution_enabled', True), ('candidate_execution_enabled', 0), ('free_only', 1),
    ('stage', 'execute'), ('extra_command', 'python candidate.py')])
def test_code_policy_cannot_be_broadened_or_disguised_as_execution(tmp_path, field, value):
    with pytest.raises(ValueError, match='fixed preview-only'):
        common.ResearchRunBudget(tmp_path / 'common.sqlite', bindings(tmp_path),
            semantic_live_ledger=tmp_path / 'live.sqlite', semantic_live_policy=DEFAULT_SEMANTIC_POLICY,
            code_check_policy={**code.POLICY, field: value})
    assert not (tmp_path / 'common.sqlite').exists()


def test_mutating_in_memory_policy_or_implementation_cannot_widen_frozen_admission(tmp_path, monkeypatch):
    budget = migrated(tmp_path); raw = budget.path.read_bytes()
    budget.code_policy['maximum_actions'] = 30
    with pytest.raises(ValueError): budget.run('code_check', {}, lambda: pytest.fail('mutable cap'))
    assert budget.path.read_bytes() == raw
    budget.code_policy = deepcopy(code.POLICY)
    original = code.implementation()
    monkeypatch.setattr(code, 'implementation', lambda: {**original, 'research_code_preview.py': '0' * 64})
    with pytest.raises(ValueError): budget.snapshot()
    assert budget.path.read_bytes() == raw


def test_code_cap_is_separate_but_never_resets_over_utc_days(tmp_path):
    day = datetime(2026, 10, 20, tzinfo=timezone.utc)
    budget = migrated(tmp_path, clock=lambda: day)
    for index in range(3):
        base(tmp_path, configured=True, clock=lambda: day + timedelta(days=index)).run(
            'code_check', {'index': index}, lambda: envelope('fit'))
    later = base(tmp_path, configured=True, clock=lambda: day + timedelta(days=4))
    with pytest.raises(ValueError, match='kind or question'):
        later.run('code_check', {'index': 4}, lambda: pytest.fail('code lifetime cap'))
    later.run('fit', {'second': True}, lambda: envelope('fit'))
    assert budget.snapshot()['reserved_by_kind'] == {'fit': 2, 'code_check': 3}


@pytest.mark.parametrize('limit', ['actions', 'wall'])
def test_code_and_fit_compete_atomically_for_last_common_slot(tmp_path, limit):
    policy = {**common.DEFAULT_POLICY, 'total_actions': 2 if limit == 'actions' else 24}
    resources = {**DEFAULT_RESOURCES, 'total_wall_ms': 50000 if limit == 'wall' else 600000}
    budget = migrated(tmp_path, policy=policy, resource_policy=resources)
    barrier = threading.Barrier(2); calls = []
    def attempt(kind):
        barrier.wait(timeout=5)
        def operation(): calls.append(kind); return envelope('fit')
        try:
            base(tmp_path, configured=True, policy=policy, resource_policy=resources).run(kind, {}, operation)
            return 'completed'
        except ValueError as error:
            assert ('common research action budget' if limit == 'actions' else 'resource allocation budget') in str(error)
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, kind) for kind in ('code_check', 'fit')]
        assert sorted(f.result(timeout=5) for f in futures) == ['completed', 'rejected']
    assert len(calls) == 1 and budget.snapshot()['total_reserved_actions'] == 2


def test_wall_overrun_blocks_fresh_work_but_not_completed_cache(tmp_path):
    budget = migrated(tmp_path); ticks = iter([0, 5001_000_000]); budget.timer = lambda: next(ticks)
    result = budget.run('code_check', {}, lambda: envelope('fit'))
    assert result['original_resources']['handler_wall_ms'] == 5001
    assert budget.snapshot()['resources']['overrun_actions'] == 1
    with pytest.raises(ValueError, match='overrun'):
        budget.run('fit', {'new': True}, lambda: pytest.fail('overrun'))
    assert budget.run('code_check', {}, lambda: pytest.fail('cache'))['coordinator_cached']


@pytest.mark.parametrize('observed', list(common.ZERO_USAGE))
def test_code_check_cannot_masquerade_as_provider_fit_or_fixture(tmp_path, observed):
    budget = migrated(tmp_path)
    with pytest.raises(RuntimeError):
        budget.run('code_check', {}, lambda: {'result': {}, 'observed': {**common.ZERO_USAGE, observed: 1}})
    assert budget.snapshot()['statuses'] == {'completed': 1, 'failed': 1}


def test_pre_cancel_creates_no_reservation_and_invalid_preview_is_never_executed(tmp_path):
    budget = migrated(tmp_path); directory = bundle(tmp_path); cancel = threading.Event(); cancel.set()
    raw = budget.path.read_bytes()
    with pytest.raises(common.BudgetCancelled): code.check_preview(budget, directory, cancel_event=cancel)
    assert budget.path.read_bytes() == raw
    code.check_preview(budget, directory)
    (directory / 'candidate/research/feature_candidate.py').write_text('raise RuntimeError("side effect")\n')
    raw = budget.path.read_bytes()
    with pytest.raises(ValueError, match='private source copy changed'): code.check_preview(budget, directory)
    assert budget.path.read_bytes() == raw


def test_candidate_side_effects_are_copied_without_import_compile_or_execution(tmp_path):
    budget = migrated(tmp_path); marker = tmp_path / 'forbidden'
    base_text = f"open({str(marker)!r}, 'w').write('base executed')\n"
    candidate = base_text.replace('base executed', 'candidate executed')
    patch = '--- a/research/feature_candidate.py\n+++ b/research/feature_candidate.py\n@@ -1 +1 @@\n-' + base_text + '+' + candidate
    directory = bundle(tmp_path, item=proposal(base_text, patch))
    result = code.check_preview(budget, directory)
    assert result['result']['exact_preview_verified'] and not marker.exists()
    assert not result['result']['candidate_executed'] and not result['result']['syntax_checked']


def test_preview_change_after_reservation_is_failed_and_charged(tmp_path, monkeypatch):
    budget = migrated(tmp_path); directory = bundle(tmp_path); original = preview.read_preview; reads = []
    def changed(path):
        reads.append(True)
        result = original(path)
        if len(reads) == 2: result['preview_sha256'] = '0' * 64
        return result
    monkeypatch.setattr(preview, 'read_preview', changed)
    with pytest.raises(RuntimeError): code.check_preview(budget, directory)
    assert budget.snapshot()['statuses'] == {'completed': 1, 'failed': 1}
    monkeypatch.setattr(preview, 'read_preview', original)
    item = proposal(); item['hypothesis'] = 'Reworded failure'; item['evidence_ids'] = ['b' * 64]
    with pytest.raises(ValueError, match='no automatic retry'):
        code.check_preview(budget, bundle(tmp_path, 'retry-copy', item))


def test_pre_extension_cache_is_preserved_without_new_action_or_resource_reservation(tmp_path):
    budget = initialized(tmp_path)
    previous = base(tmp_path).run('fit', {'cached': True}, lambda: envelope('fit', actual=True))
    code.migrate(budget)
    raw = budget.path.read_bytes()
    cached = budget.run('fit', {'cached': True}, lambda: pytest.fail('prior fit cache'))
    assert cached['coordinator_cached'] and cached['operation_key'] == previous['operation_key']
    assert budget.path.read_bytes() == raw and budget.snapshot()['total_reserved_actions'] == 2


@pytest.mark.parametrize('questions', [1, True, 1.5])
def test_code_cannot_consume_or_disguise_semantic_questions(tmp_path, questions):
    budget = migrated(tmp_path); raw = budget.path.read_bytes()
    with pytest.raises(ValueError, match='question count'):
        budget.run('code_check', {}, lambda: pytest.fail('question misuse'), questions=questions)
    assert budget.path.read_bytes() == raw


def test_same_candidate_concurrency_never_starts_a_second_handler(tmp_path):
    budget = migrated(tmp_path); started, release = threading.Event(), threading.Event(); calls = []
    def operation():
        calls.append(True); started.set(); assert release.wait(timeout=5); return envelope('fit')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(budget.run, 'code_check', {'same': True}, operation)
        try:
            assert started.wait(timeout=5)
            with pytest.raises(ValueError, match='no automatic retry'):
                base(tmp_path, configured=True).run('code_check', {'same': True}, lambda: pytest.fail('duplicate'))
        finally: release.set()
        first = future.result(timeout=5)
    repeated = base(tmp_path, configured=True).run('code_check', {'same': True}, lambda: pytest.fail('cached'))
    assert repeated['coordinator_cached'] and repeated['operation_key'] == first['operation_key']
    assert len(calls) == 1 and budget.snapshot()['total_reserved_actions'] == 2


def test_cancellation_after_reservation_is_charged_before_second_preview_read(tmp_path, monkeypatch):
    budget = migrated(tmp_path); directory = bundle(tmp_path); event = threading.Event()
    original = budget.run
    def admission(*args, **kwargs):
        operation = args[2]
        def cancel(): event.set(); return operation()
        return original(args[0], args[1], cancel, **kwargs)
    monkeypatch.setattr(budget, 'run', admission)
    with pytest.raises(common.BudgetCancelled): code.check_preview(budget, directory, cancel_event=event)
    assert budget.snapshot()['statuses'] == {'completed': 1, 'cancelled': 1}


def test_cli_explicit_migration_private_receipts_and_read_only_status(tmp_path):
    budget = initialized(tmp_path)
    semantic = tmp_path / 'semantic-policy.json'; semantic.write_text(canonical(DEFAULT_SEMANTIC_POLICY))
    policy = tmp_path / 'code-policy.json'; policy.write_text(canonical(code.POLICY))
    args = ['--database', str(budget.path), '--proposal-ledger', str(tmp_path / 'proposal.sqlite'),
        '--semantic-ledger', str(tmp_path / 'semantic_fixture.sqlite'), '--fit-ledger', str(tmp_path / 'fit.sqlite'),
        '--semantic-live-ledger', str(tmp_path / 'live.sqlite'), '--semantic-live-policy', str(semantic), '--code-policy', str(policy)]
    raw = budget.path.read_bytes()
    assert code.main([*args, '--output', str(tmp_path / 'pending.json'), 'status']) == 1
    assert budget.path.read_bytes() == raw
    before = history(budget.path)
    assert code.main([*args, '--output', str(tmp_path / 'migration.json'), 'migrate-code-budget']) == 0
    assert history(budget.path) == before
    directory = bundle(tmp_path)
    output = tmp_path / 'check.json'
    assert code.main([*args, '--output', str(output), 'code-check', '--preview', str(directory)]) == 0
    result = json.loads(output.read_text())
    assert result['status'] == 'completed' and result['result']['kind'] == 'code_check'
    assert output.stat().st_mode & 0o777 == 0o600
    raw = budget.path.read_bytes()
    assert code.main([*args, '--output', str(tmp_path / 'status.json'), 'status']) == 0
    assert budget.path.read_bytes() == raw
    from cryptoforge import llm_research_coordinator as coordinator
    ordinary = [value for value in args]
    ordinary[ordinary.index('--code-policy')] = '--code-check-policy'
    assert coordinator.main([*ordinary, '--output', str(tmp_path / 'coordinator-status.json'), 'status']) == 0
    assert budget.path.read_bytes() == raw
    for destination in (budget.path, policy, directory / 'new-result.json'):
        with pytest.raises(SystemExit):
            code.main([*args, '--output', str(destination), 'code-check', '--preview', str(directory)])


def test_checked_in_policy_matches_immutable_snapshot():
    assert json.loads(Path('config/coordinated-code-check-budget-v3.json').read_text()) == code.POLICY


def test_existing_coordinator_fit_and_proposal_share_v3_budget_and_keep_pre_migration_cache(tmp_path):
    from cryptoforge.llm_research_coordinator import ResearchCoordinator
    from cryptoforge.training_experiment_planner import freeze_protocol
    from test_llm_training_study import inputs
    dataset, item = inputs(tmp_path)
    protocol = freeze_protocol(dataset, version='synthetic-code-budget-integration-v3', epochs=3)
    paths = bindings(tmp_path)
    args = {'proposal_ledger': paths['proposal'], 'semantic_ledger': paths['semantic_fixture'], 'fit_ledger': paths['fit']}
    first = ResearchCoordinator(tmp_path / 'common.sqlite', **args).fit(dataset, protocol)
    semantic_args = {'semantic_live_ledger': tmp_path / 'live.sqlite', 'semantic_live_policy': DEFAULT_SEMANTIC_POLICY}
    ResearchCoordinator(tmp_path / 'common.sqlite', **args, **semantic_args).budget.migrate_semantic_budget()
    research = ResearchCoordinator(tmp_path / 'common.sqlite', **args, **semantic_args, code_check_policy=code.POLICY)
    code.migrate(research.budget)
    code.check_preview(research.budget, bundle(tmp_path))
    cached = research.fit(dataset, protocol)
    assert cached['coordinator_cached'] and cached['operation_key'] == first['operation_key']
    advice = research.propose(first['result']['reports']['validation']['diagnostics'], mock=item)
    assert advice['result']['advice']['provider'] == 'mock'
    assert research.budget.snapshot()['reserved_by_kind'] == {'fit': 1, 'code_check': 1, 'proposal': 1}
    assert not paths['proposal'].exists()
