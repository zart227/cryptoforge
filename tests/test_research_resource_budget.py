from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3
import threading
import pytest

from test_research_run_budget import bindings, envelope
from cryptoforge.research_resource_budget import DEFAULT_RESOURCES, ZERO_TOKENS, provider_tokens
from cryptoforge.research_run_budget import ResearchRunBudget, BudgetCancelled, BudgetTimedOut


def limits(**changes):
    return {**deepcopy(DEFAULT_RESOURCES), **changes}


def budget(tmp_path, **kwargs):
    return ResearchRunBudget(tmp_path/'common.sqlite', bindings(tmp_path), **kwargs)


def test_reported_tokens_time_and_outer_cache_remain_separate(tmp_path):
    ticks = iter([1_000_000, 8_500_001]); research = budget(tmp_path, timer=lambda: next(ticks))
    value = {**envelope('proposal', actual=True), 'tokens': {'input_tokens': 123, 'output_tokens': 7, 'total_tokens': 130}}
    first = research.run('proposal', {}, lambda: value)
    repeated = research.run('proposal', {}, lambda: pytest.fail('cached'))
    assert first['original_resources']['handler_wall_ms'] == 8
    assert repeated['original_resources'] == first['original_resources']
    assert repeated['invocation_resources']['tokens'] == ZERO_TOKENS
    assert repeated['invocation_resources']['handler_wall_ms'] == 0
    snapshot = research.snapshot()['resources']
    assert snapshot['provider_tokens_known_subtotal'] == value['tokens']
    assert snapshot['reserved_allocations'] == {'input_tokens': 32000, 'output_tokens': 2048, 'wall_ms': 65000}
    assert snapshot['measured_handler_wall_ms_subtotal'] == 8
    assert not snapshot['hard_consumption_cap'] and not snapshot['billing_audited']


def test_partial_usage_is_unknown_instead_of_zero(tmp_path):
    research = budget(tmp_path)
    research.run('proposal', {'id': 1}, lambda: envelope('proposal', actual=True))
    research.run('proposal', {'id': 2}, lambda: {**envelope('proposal', actual=True),
        'tokens': {'input_tokens': 42, 'output_tokens': None, 'total_tokens': None}})
    snapshot = research.snapshot()['resources']
    assert snapshot['provider_tokens_known_subtotal'] == {'input_tokens': 42, 'output_tokens': 0, 'total_tokens': 0}
    assert snapshot['unknown_token_actions_by_field'] == {'input_tokens': 1, 'output_tokens': 2, 'total_tokens': 2}


@pytest.mark.parametrize('kind', ['fit', 'semantic_fixture', 'proposal'])
def test_offline_handlers_keep_full_allocation_with_zero_tokens(tmp_path, kind):
    research = budget(tmp_path)
    call = research.run(kind, {}, lambda: envelope(kind), questions=3 if kind == 'semantic_fixture' else 0)
    assert call['original_resources']['tokens'] == ZERO_TOKENS
    snapshot = research.snapshot()['resources']
    assert snapshot['unknown_token_actions_by_field'] == ZERO_TOKENS
    assert snapshot['reserved_allocations']['wall_ms'] == DEFAULT_RESOURCES['wall_ms_by_kind'][kind]
    assert snapshot['reserved_allocations']['input_tokens'] == (32000 if kind == 'proposal' else 0)


@pytest.mark.parametrize('error,status', [(RuntimeError, 'failed'), (BudgetCancelled, 'cancelled'), (BudgetTimedOut, 'timed_out')])
def test_failed_external_attempt_has_measured_time_unknown_tokens_no_refund(tmp_path, error, status):
    ticks = iter([0, 20_000_001]); research = budget(tmp_path, timer=lambda: next(ticks))
    def fail(): raise error('private failure')
    with pytest.raises(RuntimeError): research.run('proposal', {}, fail)
    snapshot = research.snapshot()
    assert snapshot['statuses'] == {status: 1}
    assert snapshot['resources']['measured_handler_wall_ms_subtotal'] == 21
    assert snapshot['resources']['unknown_token_actions_by_field'] == {name: 1 for name in ZERO_TOKENS}
    assert snapshot['resources']['reserved_allocations']['output_tokens'] == 2048
    with pytest.raises(ValueError, match='no automatic retry'): research.run('proposal', {}, lambda: envelope('proposal'))


def test_abrupt_exit_keeps_reservation_and_unknown_time(tmp_path):
    research = budget(tmp_path)
    def fail(): raise SystemExit('private crash')
    with pytest.raises(SystemExit): research.run('proposal', {}, fail)
    snapshot = research.snapshot()['resources']
    assert snapshot['unmeasured_wall_actions'] == 1
    assert snapshot['unknown_token_actions_by_field']['input_tokens'] == 1
    assert snapshot['reserved_allocations']['wall_ms'] == 65000


@pytest.mark.parametrize('field,value', [('total_input_tokens', 31999), ('total_output_tokens', 2047), ('total_wall_ms', 64999)])
def test_resource_admission_precedes_callback_and_freezes_denied_first_policy(tmp_path, field, value):
    research = budget(tmp_path, resource_policy=limits(**{field: value}))
    with pytest.raises(ValueError, match='resource allocation budget'): research.run('proposal', {}, lambda: pytest.fail('must not run'))
    assert research.snapshot()['total_reserved_actions'] == 0
    with pytest.raises(ValueError, match='resource policy changed'): budget(tmp_path).run('fit', {}, lambda: envelope('fit'))


def test_resource_limits_are_lifetime_and_cannot_be_bypassed_by_omission(tmp_path):
    policy = limits(total_wall_ms=25000); today = datetime(2026, 10, 17, tzinfo=timezone.utc)
    budget(tmp_path, resource_policy=policy, clock=lambda: today).run('fit', {}, lambda: envelope('fit'))
    with pytest.raises(ValueError, match='resource allocation budget'):
        budget(tmp_path, resource_policy=policy, clock=lambda: today+timedelta(days=1)).run('fit', {'id': 2}, lambda: envelope('fit'))
    with pytest.raises(ValueError, match='resource policy changed'): budget(tmp_path).snapshot()


def test_concurrent_different_kinds_cannot_spend_last_wall_allocation_twice(tmp_path):
    policy = limits(total_wall_ms=35000); barrier = threading.Barrier(2); executed = []
    def attempt(kind):
        barrier.wait(timeout=5)
        try:
            def run(): executed.append(kind); return envelope(kind)
            budget(tmp_path, resource_policy=policy).run(kind, {}, run, questions=1 if kind == 'semantic_fixture' else 0)
            return 'completed'
        except ValueError as error:
            assert 'resource allocation budget' in str(error)
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, kind) for kind in ('fit', 'semantic_fixture')]
        assert sorted(f.result(timeout=5) for f in futures) == ['completed', 'rejected']
    assert len(executed) == 1


@pytest.mark.parametrize('resource', ['input_tokens', 'output_tokens', 'wall_ms'])
def test_overrun_blocks_fresh_work_and_allows_completed_cache(tmp_path, resource):
    ticks = iter([0, (65001 if resource == 'wall_ms' else 1)*1_000_000]); research = budget(tmp_path, timer=lambda: next(ticks))
    tokens = {'input_tokens': 32001 if resource == 'input_tokens' else 100, 'output_tokens': 2049 if resource == 'output_tokens' else 1}
    tokens['total_tokens'] = sum(tokens.values())
    call = research.run('proposal', {}, lambda: {**envelope('proposal', actual=True), 'tokens': tokens})
    assert research.snapshot()['resources']['overrun_actions'] == 1
    with pytest.raises(ValueError, match='overrun'): research.run('fit', {'new': True}, lambda: pytest.fail('must not run'))
    assert research.run('proposal', {}, lambda: pytest.fail('cached'))['operation_key'] == call['operation_key']


def test_legacy_migration_preserves_actions_and_charges_unknown_history(tmp_path):
    research = budget(tmp_path); research.run('proposal', {}, lambda: envelope('proposal', actual=True)); research.run('fit', {}, lambda: envelope('fit'))
    path = tmp_path/'common.sqlite'
    with sqlite3.connect(path) as db:
        actions = db.execute('SELECT * FROM coordinated_actions ORDER BY key').fetchall(); manifest = db.execute('SELECT * FROM coordinated_policy').fetchall()
        db.execute('DROP TABLE coordinated_resources'); db.execute('DROP TABLE coordinated_resource_policy')
    before = path.read_bytes(); snapshot = research.snapshot()
    assert snapshot['resources'] is None and snapshot['resource_accounting'] == 'legacy_unmeasured_not_initialized'
    assert path.read_bytes() == before
    cached = research.run('fit', {}, lambda: pytest.fail('cached'))
    assert cached['original_resources']['origin'] == 'legacy_unmeasured'
    snapshot = research.snapshot()['resources']
    assert snapshot['legacy_unmeasured_actions'] == snapshot['unmeasured_wall_actions'] == 2
    assert snapshot['unknown_token_actions_by_field'] == {name: 1 for name in ZERO_TOKENS}
    assert snapshot['reserved_allocations']['wall_ms'] == 90000
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM coordinated_actions ORDER BY key').fetchall() == actions
        assert db.execute('SELECT * FROM coordinated_policy').fetchall() == manifest


def test_legacy_usage_can_exhaust_policy_without_erasing_attempts(tmp_path):
    research = budget(tmp_path); research.run('fit', {}, lambda: envelope('fit'))
    with sqlite3.connect(tmp_path/'common.sqlite') as db:
        db.execute('DROP TABLE coordinated_resources'); db.execute('DROP TABLE coordinated_resource_policy')
    limited = budget(tmp_path, resource_policy=limits(total_wall_ms=1000))
    with pytest.raises(ValueError, match='resource allocation budget'): limited.run('fit', {'new': True}, lambda: pytest.fail('must not run'))
    assert limited.snapshot()['total_reserved_actions'] == 1
    assert limited.snapshot()['resources']['reserved_allocations']['wall_ms'] == 25000


@pytest.mark.parametrize('corruption', ["UPDATE coordinated_resources SET allocation='{}'", "UPDATE coordinated_resources SET measurement='{}'",
    'DELETE FROM coordinated_resources', 'UPDATE coordinated_resources SET measurement=NULL,measurement_sha=NULL', 'DROP TABLE coordinated_resource_policy'])
def test_corrupt_accounting_is_refused_without_repair_or_new_work(tmp_path, corruption):
    research = budget(tmp_path); research.run('fit', {}, lambda: envelope('fit'))
    with sqlite3.connect(tmp_path/'common.sqlite') as db: db.execute(corruption)
    with pytest.raises(ValueError): research.snapshot()
    with pytest.raises(ValueError): research.run('fit', {'new': True}, lambda: pytest.fail('must not run'))


@pytest.mark.parametrize('usage,expected', [({}, {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}),
    ({'prompt_tokens': True, 'completion_tokens': -1, 'total_tokens': '2'}, {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}),
    ({'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 99}, {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}),
    ({'prompt_tokens': 4, 'total_tokens': 3}, {'input_tokens': None, 'output_tokens': None, 'total_tokens': None}),
    ({'prompt_tokens': 4, 'completion_tokens': 2}, {'input_tokens': 4, 'output_tokens': 2, 'total_tokens': None})])
def test_normalization_never_guesses_missing_provider_fields(usage, expected):
    assert provider_tokens(usage) == expected


def test_snapshot_with_resources_is_read_only(tmp_path):
    research = budget(tmp_path); research.run('fit', {}, lambda: envelope('fit'))
    path = tmp_path/'common.sqlite'; before = path.read_bytes(); research.snapshot()
    assert path.read_bytes() == before and path.stat().st_mode & 0o777 == 0o600


def test_total_only_usage_overrun_blocks_fresh_work_without_guessing_components(tmp_path):
    research = budget(tmp_path)
    research.run('proposal', {}, lambda: {**envelope('proposal', actual=True),
        'tokens': {'input_tokens': None, 'output_tokens': None, 'total_tokens': 1000000}})
    snapshot = research.snapshot()['resources']
    assert snapshot['overrun_actions'] == 1
    assert snapshot['unknown_token_actions_by_field']['input_tokens'] == 1
    assert snapshot['provider_tokens_known_subtotal']['total_tokens'] == 1000000
    with pytest.raises(ValueError, match='overrun'):
        research.run('fit', {}, lambda: pytest.fail('must not run'))
