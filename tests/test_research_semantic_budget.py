from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import threading

import pytest

from cryptoforge import research_run_budget as module
from cryptoforge import llm_research_coordinator as coordinator
from cryptoforge.research_resource_budget import DEFAULT_RESOURCES, ZERO_TOKENS
from cryptoforge.research_semantic_budget import DEFAULT_SEMANTIC_POLICY, EXTENSION_TABLE, table_digest
from cryptoforge.training_diagnostics import canonical, digest
from test_research_run_budget import bindings, envelope


def base(tmp_path, **kwargs):
    return module.ResearchRunBudget(tmp_path/'common.sqlite', bindings(tmp_path), **kwargs)


def extended(tmp_path, *, semantic=None, ledger=None, **kwargs):
    return base(tmp_path, semantic_live_policy=deepcopy(DEFAULT_SEMANTIC_POLICY) if semantic is None else semantic,
        semantic_live_ledger=tmp_path/'live.sqlite' if ledger is None else ledger, **kwargs)


def initialized(tmp_path, **kwargs):
    base(tmp_path, **kwargs).run('fit', {'initial': True}, lambda: envelope('fit'))
    return extended(tmp_path, **kwargs)


def live(*, observed=True, tokens=None):
    return {'result': {'origin': 'synthetic_accounting_fixture'},
        'observed': {**module.ZERO_USAGE, 'local_llm_completions': int(observed)},
        **({'tokens': tokens} if tokens is not None else {})}


def rows(path):
    with sqlite3.connect(path) as db:
        return {name: db.execute(f'SELECT * FROM {name} ORDER BY 1').fetchall() for name in
            ('coordinated_policy', 'coordinated_actions', 'coordinated_resource_policy', 'coordinated_resources')}


def test_explicit_migration_preserves_all_existing_rows_and_is_idempotent(tmp_path):
    old = base(tmp_path)
    old.run('fit', {'initial': True}, lambda: envelope('fit'))
    old.run('proposal', {}, lambda: envelope('proposal'))
    old.run('semantic_fixture', {}, lambda: envelope('semantic_fixture'), questions=3)
    original_rows, snapshot = rows(old.path), old.snapshot()
    research = extended(tmp_path)
    result = research.migrate_semantic_budget()
    assert not result['already_migrated'] and not result['action_reserved']
    assert result['inference_requests'] == 0 and not result['live_transport_enabled']
    assert rows(old.path) == original_rows
    assert result['extension']['migration']['legacy_action_count'] == 3
    with sqlite3.connect(old.path) as db:
        for table, checksum in result['extension']['migration']['legacy_tables_sha256'].items():
            assert table_digest(db, table) == checksum
    updated = research.snapshot()
    assert updated['total_reserved_actions'] == snapshot['total_reserved_actions'] == 3
    assert updated['resources'] == snapshot['resources']
    assert updated['manifest'] == snapshot['manifest']
    assert updated['reserved_semantic_questions'] == 3
    before = old.path.read_bytes()
    assert research.migrate_semantic_budget()['already_migrated']
    assert old.path.read_bytes() == before
    assert not (tmp_path/'live.sqlite').exists()
    with pytest.raises(ValueError, match='explicit semantic-live'): old.snapshot()
    with pytest.raises(ValueError, match='explicit semantic-live'):
        old.run('fit', {'new': True}, lambda: pytest.fail('no unconfigured access'))


def test_configuration_never_migrates_implicitly_or_creates_a_missing_journal(tmp_path):
    research = extended(tmp_path)
    with pytest.raises(ValueError, match='existing'): research.migrate_semantic_budget()
    with pytest.raises(ValueError, match='existing'): research.run('semantic_live', {}, lambda: live(), questions=1)
    assert not research.path.exists()
    old = base(tmp_path); old.run('fit', {}, lambda: envelope('fit'))
    before = old.path.read_bytes()
    with pytest.raises(ValueError, match='explicit semantic budget migration'): research.snapshot()
    with pytest.raises(ValueError, match='explicit semantic budget migration'):
        research.run('semantic_live', {}, lambda: pytest.fail('no implicit migration'), questions=1)
    assert old.path.read_bytes() == before


def test_pre_resource_legacy_migration_backfills_without_changing_actions_or_manifest(tmp_path):
    old = base(tmp_path); old.run('proposal', {}, lambda: envelope('proposal', actual=True))
    before_rows = rows(old.path)
    with sqlite3.connect(old.path) as db:
        db.execute('DROP TABLE coordinated_resources'); db.execute('DROP TABLE coordinated_resource_policy')
    research = extended(tmp_path)
    result = research.migrate_semantic_budget()
    assert result['extension']['migration']['resource_backfilled']
    after = rows(old.path)
    for table in ('coordinated_policy', 'coordinated_actions'): assert after[table] == before_rows[table]
    snapshot = research.snapshot()['resources']
    assert snapshot['legacy_unmeasured_actions'] == 1 and snapshot['unmeasured_wall_actions'] == 1
    assert snapshot['reserved_allocations'] == {'input_tokens': 32000, 'output_tokens': 2048, 'wall_ms': 65000}
    assert snapshot['unknown_token_actions_by_field'] == {key: 1 for key in ZERO_TOKENS}


@pytest.mark.parametrize('exception,status', [(RuntimeError, 'failed'), (module.BudgetCancelled, 'cancelled'),
    (module.BudgetTimedOut, 'timed_out')])
def test_prior_failures_remain_charged_through_migration(tmp_path, exception, status):
    old = base(tmp_path)
    def fail(): raise exception('private')
    with pytest.raises(RuntimeError): old.run('proposal', {}, fail)
    before = rows(old.path)
    research = extended(tmp_path); research.migrate_semantic_budget()
    assert rows(old.path) == before
    assert research.snapshot()['statuses'] == {status: 1}
    assert research.snapshot()['resources']['unknown_token_actions_by_field']['input_tokens'] == 1
    with pytest.raises(ValueError, match='no automatic retry'): research.run('proposal', {}, lambda: envelope('proposal'))


def test_unfinished_reservation_blocks_migration_without_erasing_or_resolving_it(tmp_path):
    old = base(tmp_path)
    def crash(): raise SystemExit('interrupted')
    with pytest.raises(SystemExit): old.run('fit', {}, crash)
    before = old.path.read_bytes()
    with pytest.raises(ValueError, match='unfinished common reservations'): extended(tmp_path).migrate_semantic_budget()
    assert old.path.read_bytes() == before and old.snapshot()['statuses'] == {'reserved': 1}


def test_migration_refuses_an_active_handler_and_can_proceed_after_it_finishes(tmp_path):
    old = base(tmp_path); started, release = threading.Event(), threading.Event()
    def operation():
        started.set(); assert release.wait(timeout=5); return envelope('fit')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(old.run, 'fit', {}, operation)
        try:
            assert started.wait(timeout=5)
            with pytest.raises(ValueError, match='unfinished common reservations'):
                extended(tmp_path).migrate_semantic_budget()
        finally:
            release.set()
        future.result(timeout=5)
    assert not extended(tmp_path).migrate_semantic_budget()['already_migrated']


@pytest.mark.parametrize('change', ['binding', 'maximum', 'input', 'output', 'wall', 'base_policy', 'resources'])
def test_migrated_configuration_is_immutable_and_cannot_be_omitted_or_replaced(tmp_path, change):
    research = initialized(tmp_path); research.migrate_semantic_budget(); before = research.path.read_bytes()
    kwargs = {}; semantic = deepcopy(DEFAULT_SEMANTIC_POLICY)
    if change == 'binding': kwargs['ledger'] = tmp_path/'replacement.sqlite'
    elif change == 'maximum': semantic['maximum_actions'] += 1
    elif change == 'input': semantic['input_tokens'] += 1
    elif change == 'output': semantic['output_tokens'] += 1
    elif change == 'wall': semantic['wall_ms'] += 1
    elif change == 'base_policy': kwargs['policy'] = {**module.DEFAULT_POLICY, 'total_actions': 25}
    else: kwargs['resource_policy'] = {**DEFAULT_RESOURCES, 'total_wall_ms': 700000}
    changed = extended(tmp_path, semantic=semantic, **kwargs)
    for operation in (changed.snapshot, changed.migrate_semantic_budget,
                      lambda: changed.run('fit', {}, lambda: pytest.fail('config mismatch'))):
        with pytest.raises(ValueError): operation()
    assert research.path.read_bytes() == before


def test_live_kind_shares_total_cap_and_preserves_cache_after_exhaustion(tmp_path):
    policy = {**module.DEFAULT_POLICY, 'total_actions': 2}
    research = initialized(tmp_path, policy=policy); research.migrate_semantic_budget()
    calls = []
    def operation(): calls.append(True); return live(tokens={'input_tokens': 123, 'output_tokens': 7, 'total_tokens': 130})
    first = research.run('semantic_live', {}, operation, questions=2)
    with pytest.raises(ValueError, match='common research action budget'):
        research.run('fit', {'new': True}, lambda: pytest.fail('must reject first'))
    repeated = research.run('semantic_live', {}, operation, questions=2)
    assert repeated['coordinator_cached'] and len(calls) == 1
    assert repeated['invocation_observed'] == module.ZERO_USAGE and repeated['invocation_resources']['tokens'] == ZERO_TOKENS
    assert first['original_resources']['tokens']['input_tokens'] == 123
    snapshot = research.snapshot()
    assert snapshot['reserved_by_kind'] == {'fit': 1, 'semantic_live': 1}
    assert snapshot['reserved_semantic_questions'] == 2
    assert snapshot['resources']['reserved_allocations'] == {'input_tokens': 32000, 'output_tokens': 2048, 'wall_ms': 60000}


def test_fixtures_and_live_share_question_cap_but_have_separate_kind_caps(tmp_path):
    policy = {**module.DEFAULT_POLICY, 'semantic_questions': 3}
    old = base(tmp_path, policy=policy)
    old.run('semantic_fixture', {}, lambda: envelope('semantic_fixture'), questions=2)
    research = extended(tmp_path, policy=policy, semantic={**DEFAULT_SEMANTIC_POLICY, 'maximum_actions': 1})
    research.migrate_semantic_budget()
    with pytest.raises(ValueError, match='kind or question'):
        research.run('semantic_live', {'too_many': True}, lambda: pytest.fail('question admission'), questions=2)
    research.run('semantic_live', {}, lambda: live(observed=False), questions=1)
    with pytest.raises(ValueError, match='kind or question'):
        research.run('semantic_live', {'second': True}, lambda: pytest.fail('kind admission'), questions=1)
    research.run('fit', {}, lambda: envelope('fit'))
    assert research.snapshot()['reserved_semantic_questions'] == 3


def test_utc_day_does_not_reset_shared_lifetime_limits(tmp_path):
    day = datetime(2026, 10, 18, tzinfo=timezone.utc)
    policy = {**module.DEFAULT_POLICY, 'daily_actions': 1, 'total_actions': 2}
    research = initialized(tmp_path, policy=policy, clock=lambda: day); research.migrate_semantic_budget()
    with pytest.raises(ValueError, match='common research action budget'):
        research.run('semantic_live', {}, lambda: pytest.fail('daily cap'), questions=1)
    later = extended(tmp_path, policy=policy, clock=lambda: day+timedelta(days=1))
    later.run('semantic_live', {}, lambda: live(observed=False), questions=1)
    final = extended(tmp_path, policy=policy, clock=lambda: day+timedelta(days=2))
    with pytest.raises(ValueError, match='common research action budget'):
        final.run('fit', {}, lambda: pytest.fail('lifetime cap'))


@pytest.mark.parametrize('resource', ['input_tokens', 'output_tokens', 'wall_ms'])
def test_semantic_reserves_from_existing_resource_totals_before_callback(tmp_path, resource):
    limit = {'input_tokens': 63999, 'output_tokens': 4095, 'wall_ms': 99999}[resource]
    resources = {**DEFAULT_RESOURCES, 'total_'+resource: limit}
    old = base(tmp_path, resource_policy=resources); old.run('proposal', {}, lambda: envelope('proposal'))
    research = extended(tmp_path, resource_policy=resources); research.migrate_semantic_budget()
    with pytest.raises(ValueError, match='resource allocation budget'):
        research.run('semantic_live', {}, lambda: pytest.fail('resource admission'), questions=1)
    assert research.snapshot()['total_reserved_actions'] == 1


@pytest.mark.parametrize('resource', ['input_tokens', 'output_tokens', 'wall_ms', 'total_only'])
def test_semantic_overrun_blocks_new_work_but_not_its_completed_cache(tmp_path, resource):
    research = initialized(tmp_path); research.migrate_semantic_budget()
    ticks = iter([0, (35001 if resource == 'wall_ms' else 1)*1_000_000]); research.timer = lambda: next(ticks)
    tokens = {'input_tokens': 32001 if resource == 'input_tokens' else 100,
              'output_tokens': 2049 if resource == 'output_tokens' else 1}
    tokens['total_tokens'] = sum(tokens.values())
    if resource == 'total_only': tokens = {'input_tokens': None, 'output_tokens': None, 'total_tokens': 50000}
    research.run('semantic_live', {}, lambda: live(tokens=tokens), questions=1)
    assert research.snapshot()['resources']['overrun_actions'] == 1
    with pytest.raises(ValueError, match='overrun'): research.run('fit', {}, lambda: pytest.fail('overrun'))
    assert research.run('semantic_live', {}, lambda: pytest.fail('cached'), questions=1)['coordinator_cached']


@pytest.mark.parametrize('exception,status', [(RuntimeError, 'failed'), (module.BudgetCancelled, 'cancelled'),
    (module.BudgetTimedOut, 'timed_out'), (SystemExit, 'reserved')])
def test_semantic_failures_keep_question_token_and_time_reservations(tmp_path, exception, status):
    research = initialized(tmp_path); research.migrate_semantic_budget()
    def fail(): raise exception('private provider body')
    with pytest.raises((RuntimeError, SystemExit)): research.run('semantic_live', {}, fail, questions=4)
    snapshot = research.snapshot()
    assert snapshot['statuses'] == {'completed': 1, status: 1}
    assert snapshot['reserved_semantic_questions'] == 4
    assert snapshot['resources']['reserved_allocations']['input_tokens'] == 32000
    assert snapshot['resources']['unknown_token_actions_by_field'] == {key: 1 for key in ZERO_TOKENS}
    with pytest.raises(ValueError, match='no automatic retry'):
        research.run('semantic_live', {}, lambda: pytest.fail('no retry'), questions=4)
    with sqlite3.connect(research.path) as db:
        assert 'private provider body' not in repr(db.execute('SELECT * FROM coordinated_actions').fetchall())


@pytest.mark.parametrize('limit', ['actions', 'wall'])
def test_mixed_semantic_and_fit_cannot_both_take_last_common_slot(tmp_path, limit):
    policy = {**module.DEFAULT_POLICY, 'total_actions': 2 if limit == 'actions' else 24}
    resources = {**DEFAULT_RESOURCES, 'total_wall_ms': 60000 if limit == 'wall' else 600000}
    research = initialized(tmp_path, policy=policy, resource_policy=resources); research.migrate_semantic_budget()
    barrier = threading.Barrier(2); calls = []
    def attempt(kind):
        barrier.wait(timeout=5)
        def operation(): calls.append(kind); return live(observed=False) if kind == 'semantic_live' else envelope('fit')
        try:
            extended(tmp_path, policy=policy, resource_policy=resources).run(kind, {}, operation, questions=int(kind == 'semantic_live'))
            return 'completed'
        except ValueError as exc:
            assert ('common research action budget' if limit == 'actions' else 'resource allocation budget') in str(exc)
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, kind) for kind in ('semantic_live', 'fit')]
        assert sorted(f.result(timeout=5) for f in futures) == ['completed', 'rejected']
    assert len(calls) == 1 and research.snapshot()['total_reserved_actions'] == 2


def test_concurrent_migrations_are_one_atomic_extension_without_new_actions(tmp_path):
    research = initialized(tmp_path); before = rows(research.path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(extended(tmp_path).migrate_semantic_budget) for _ in range(2)]
        assert sorted(f.result(timeout=5)['already_migrated'] for f in futures) == [False, True]
    assert rows(research.path) == before and research.snapshot()['total_reserved_actions'] == 1


def test_migration_rolls_back_extension_and_backfill_together_on_failure(tmp_path, monkeypatch):
    research = initialized(tmp_path)
    with sqlite3.connect(research.path) as db:
        db.execute('DROP TABLE coordinated_resources'); db.execute('DROP TABLE coordinated_resource_policy')
    before = research.path.read_bytes(); create = module.create_extension
    def interrupted(*args, **kwargs): create(*args, **kwargs); raise RuntimeError('migration interrupted')
    monkeypatch.setattr(module, 'create_extension', interrupted)
    with pytest.raises(RuntimeError): research.migrate_semantic_budget()
    assert research.path.read_bytes() == before
    assert base(tmp_path).snapshot()['resource_accounting'] == 'legacy_unmeasured_not_initialized'


@pytest.mark.parametrize('sql', ["UPDATE coordinated_actions SET payload='{}'",
    "UPDATE coordinated_actions SET questions=-1", "UPDATE coordinated_actions SET status='unknown'",
    'DROP TABLE coordinated_resource_policy', "UPDATE coordinated_resources SET allocation='{}'",
    'CREATE TRIGGER foreign_trigger AFTER UPDATE ON coordinated_actions BEGIN SELECT 1; END'])
def test_corrupted_history_is_not_migrated_or_repaired(tmp_path, sql):
    research = initialized(tmp_path)
    with sqlite3.connect(research.path) as db: db.execute(sql)
    before = research.path.read_bytes()
    with pytest.raises(ValueError): research.migrate_semantic_budget()
    assert research.path.read_bytes() == before
    with sqlite3.connect(research.path) as db:
        assert db.execute('SELECT count(*) FROM sqlite_master WHERE name=?', (EXTENSION_TABLE,)).fetchone()[0] == 0


@pytest.mark.parametrize('sql', ["UPDATE coordinated_semantic_extension SET payload='{}'",
    'DELETE FROM coordinated_semantic_extension', 'DROP TABLE coordinated_resources'])
def test_corrupted_extension_or_coverage_is_rejected_without_fresh_work(tmp_path, sql):
    research = initialized(tmp_path); research.migrate_semantic_budget()
    with sqlite3.connect(research.path) as db: db.execute(sql)
    before = research.path.read_bytes()
    with pytest.raises(ValueError): research.snapshot()
    with pytest.raises(ValueError): research.run('fit', {}, lambda: pytest.fail('corrupt journal'))
    assert research.path.read_bytes() == before


def test_json_boolean_cannot_be_replaced_by_equal_python_integer_in_extension(tmp_path):
    research = initialized(tmp_path); research.migrate_semantic_budget()
    with sqlite3.connect(research.path) as db:
        payload = json.loads(db.execute('SELECT payload FROM coordinated_semantic_extension').fetchone()[0])
        payload['configuration']['policy']['free_only'] = 1
        db.execute('UPDATE coordinated_semantic_extension SET payload=?,sha=?', (canonical(payload), digest(payload)))
    with pytest.raises(ValueError, match='persisted semantic'): research.snapshot()


def test_pre_cancelled_semantic_action_never_consumes_an_allocation(tmp_path):
    research = initialized(tmp_path); research.migrate_semantic_budget()
    before = research.path.read_bytes(); cancel = threading.Event(); cancel.set()
    with pytest.raises(module.BudgetCancelled):
        research.run('semantic_live', {}, lambda: pytest.fail('pre-cancelled'), questions=1, cancel_event=cancel)
    assert research.path.read_bytes() == before and research.snapshot()['total_reserved_actions'] == 1


def test_pre_migration_completed_cache_remains_usable_without_new_reservation(tmp_path):
    old = base(tmp_path); first = old.run('fit', {}, lambda: envelope('fit', actual=True))
    research = extended(tmp_path); research.migrate_semantic_budget()
    repeated = research.run('fit', {}, lambda: pytest.fail('pre-migration cache'))
    assert repeated['coordinator_cached'] and repeated['operation_key'] == first['operation_key']
    assert repeated['invocation_observed'] == module.ZERO_USAGE and research.snapshot()['total_reserved_actions'] == 1
    before = research.path.read_bytes(); research.snapshot(); assert research.path.read_bytes() == before


@pytest.mark.parametrize('field,value', [('free_only', False), ('maximum_actions', True),
    ('input_tokens', 0), ('wall_ms', 600001), ('transport', 'paid_cloud')])
def test_invalid_extension_config_cannot_initialize_any_journal(tmp_path, field, value):
    with pytest.raises(ValueError): extended(tmp_path, semantic={**DEFAULT_SEMANTIC_POLICY, field: value})
    assert not (tmp_path/'common.sqlite').exists()


@pytest.mark.parametrize('ledger', ['common.sqlite', 'proposal.sqlite', 'semantic_fixture.sqlite', 'fit.sqlite'])
def test_live_binding_must_be_separate_from_every_existing_journal(tmp_path, ledger):
    with pytest.raises(ValueError, match='five separate'): extended(tmp_path, ledger=tmp_path/ledger)


@pytest.mark.parametrize('questions', [0, 17, True, 1.5])
def test_live_questions_are_bounded_before_any_reservation(tmp_path, questions):
    research = initialized(tmp_path); research.migrate_semantic_budget(); before = research.path.read_bytes()
    with pytest.raises(ValueError, match='question count'):
        research.run('semantic_live', {}, lambda: pytest.fail('question shape'), questions=questions)
    assert research.path.read_bytes() == before


@pytest.mark.parametrize('observed', ['remote_completions', 'fixture_workers', 'numeric_fits'])
def test_live_kind_cannot_mislabel_remote_or_fixture_work_as_local(tmp_path, observed):
    research = initialized(tmp_path); research.migrate_semantic_budget()
    with pytest.raises(RuntimeError):
        research.run('semantic_live', {}, lambda: {'result': {}, 'observed': {**module.ZERO_USAGE, observed: 1}}, questions=1)
    assert research.snapshot()['statuses'] == {'completed': 1, 'failed': 1}


def test_cli_explicit_migration_and_read_only_status_live_requires_explicit_inputs(tmp_path):
    research = initialized(tmp_path); before = rows(research.path)
    config = tmp_path/'semantic-policy.json'; config.write_text(canonical(DEFAULT_SEMANTIC_POLICY))
    common = ['--database', str(research.path), '--proposal-ledger', str(tmp_path/'proposal.sqlite'),
        '--semantic-ledger', str(tmp_path/'semantic_fixture.sqlite'), '--fit-ledger', str(tmp_path/'fit.sqlite'),
        '--semantic-live-ledger', str(tmp_path/'live.sqlite'), '--semantic-live-policy', str(config)]
    pending = tmp_path/'not-migrated.json'
    assert coordinator.main([*common, '--output', str(pending), 'status']) == 1
    assert rows(research.path) == before
    output = tmp_path/'migration.json'
    assert coordinator.main([*common, '--output', str(output), 'migrate-semantic-budget']) == 0
    receipt = json.loads(output.read_text())
    assert receipt['status'] == 'completed' and receipt['call'] is None
    assert not receipt['migration']['action_reserved'] and receipt['budget']['total_reserved_actions'] == 1
    assert rows(research.path) == before and output.stat().st_mode & 0o777 == 0o600
    before_bytes = research.path.read_bytes()
    assert coordinator.main([*common, '--output', str(tmp_path/'status.json'), 'status']) == 0
    assert research.path.read_bytes() == before_bytes and not (tmp_path/'live.sqlite').exists()
    with pytest.raises(SystemExit):
        coordinator.main([*common, '--output', str(tmp_path/'no-live.json'), 'semantic-live'])
    assert not (tmp_path/'no-live.json').exists()
