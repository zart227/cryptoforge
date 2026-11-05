from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json

import pytest

import cryptoforge.paper_valuation_capture as capture
from cryptoforge.paper_lifecycle import CoverageTimeline, PaperLifecycle, mark_valid_until, resource_blocker
from cryptoforge.paper_valuation_capture import CapturedPaperWallet, audit_valuation_capture
from test_paper_wallet import Clock, START, config
from test_paper_valuation_capture import raw_market, rewrite_chain


def limits(**changes):
    base = PaperLifecycle(poll_seconds=5, maximum_operations_per_poll=4, estimated_bytes_per_operation=8192,
        maximum_mark_gap_seconds=5, maximum_endpoint_gap_seconds=1, minimum_known_time_fraction='0.99',
        closeout_seconds=5, finalization_grace_seconds=10, maximum_operation_wall_seconds=1,
        maximum_storage_bytes=16*1024*1024, minimum_free_disk_bytes=16*1024*1024,
        minimum_available_memory_bytes=1)
    return replace(base, **changes)


def setup(tmp_path, *, policy=None):
    clock = Clock()
    clock.now = START-timedelta(seconds=10)
    wallet = CapturedPaperWallet.create(tmp_path/'new-lifecycle', candidate_sha='a'*64, config=config(),
        start=START, end=START+timedelta(seconds=30), max_events=128, lifecycle=policy or limits(), clock=clock)
    clock.now = START
    return wallet, clock


def audit(wallet):
    return audit_valuation_capture(wallet.root, expected_protocol_sha256=wallet.protocol_sha256,
        clock=lambda: START+timedelta(seconds=40))


def populate_flat(wallet, clock):
    for value in (0, 5, 10, 15, 20, 25, 29):
        clock.now = START+timedelta(seconds=value)
        wallet.mark({})


@pytest.mark.parametrize('changes', [
    dict(poll_seconds=True), dict(maximum_operations_per_poll=0),
    dict(minimum_known_time_fraction='NaN'), dict(minimum_known_time_fraction='0'),
    dict(minimum_known_time_fraction='1.01'), dict(maximum_operation_wall_seconds=6),
    dict(maximum_storage_bytes=128), dict(minimum_free_disk_bytes=1),
    dict(estimated_bytes_per_operation=524289), dict(maximum_mark_gap_seconds=4),
])
def test_invalid_contract_never_becomes_a_protocol(changes):
    with pytest.raises(ValueError): limits(**changes)


def test_persistent_roundtrip_and_horizon_capacity_preflight(tmp_path):
    policy = limits()
    assert PaperLifecycle.from_payload(policy.payload()) == policy
    plan = policy.plan(START, START+timedelta(seconds=30), max_events=128)
    assert policy.capacity_requirements(START, START+timedelta(seconds=30)) == plan
    assert plan['required_events'] == 52
    assert plan['entry_cutoff'] == (START+timedelta(seconds=25)).isoformat()
    clock = Clock()
    with pytest.raises(ValueError, match='needs .* events'):
        CapturedPaperWallet.create(tmp_path/'impossible', candidate_sha='a'*64, config=config(),
            start=START+timedelta(seconds=10), end=START+timedelta(days=30),
            lifecycle=policy, clock=clock)
    assert not (tmp_path/'impossible').exists()


def test_storage_estimate_cannot_be_ignored():
    policy = limits(maximum_storage_bytes=65536)
    with pytest.raises(ValueError, match='storage'):
        policy.plan(START, START+timedelta(seconds=30), max_events=128)
    with pytest.raises(ValueError, match='closeout'):
        policy.plan(START, START+timedelta(seconds=5), max_events=128)


def test_full_time_coverage_and_terminal_are_not_economic_approval(tmp_path):
    wallet, clock = setup(tmp_path)
    populate_flat(wallet, clock)
    clock.now = START+timedelta(seconds=30)
    wallet.terminate('completed')
    report = audit(wallet)
    assert report['lifecycle']['coverage']['known_fraction'] == '1'
    assert report['lifecycle']['lifecycle_evidence_pass']
    assert not report['fill_source_evidence_pass']
    assert not report['economic_profitability_established']
    assert not report['live_admission_granted']


def test_same_timestamp_duplicates_cannot_cover_an_unobserved_interval():
    timeline = CoverageTimeline(START, START+timedelta(seconds=30), limits())
    for _ in range(100):
        timeline.invalidate(START)
        timeline.mark(START, START+timedelta(seconds=5), sources_known=True)
    report = timeline.finish()
    assert report['known_seconds'] == '5'
    assert report['maximum_unknown_gap_seconds'] == '25'
    assert not report['coverage_pass']


def test_fills_and_unknown_marks_interrupt_previous_coverage():
    timeline = CoverageTimeline(START, START+timedelta(seconds=30), limits())
    timeline.mark(START, START+timedelta(seconds=5), sources_known=True)
    timeline.invalidate(START+timedelta(seconds=2))
    timeline.mark(START+timedelta(seconds=10), START+timedelta(seconds=15), sources_known=False)
    assert timeline.finish()['known_seconds'] == '2'


def test_quote_freshness_uses_original_receipt_not_repeated_mark_time():
    clock = Clock()
    q, r = raw_market(clock)
    before = dict(lots=[dict(pair='AAA/USDT', qty='1')])
    policy = limits(maximum_mark_gap_seconds=30)
    at = START+timedelta(seconds=9)
    assert mark_valid_until(policy, at, before, {'AAA/USDT': q}, {'AAA/USDT': r}, config()) == START+timedelta(seconds=10)


def test_known_time_requires_completion_not_backdated_producer_mark(tmp_path):
    wallet, clock = setup(tmp_path)
    times = iter([START, START+timedelta(seconds=2)])
    wallet.clock = lambda: next(times)
    wallet.mark({})
    wallet.clock = clock
    result = audit(wallet)['lifecycle']['coverage']
    assert result['known_seconds'] == '3'
    assert result['leading_unknown_seconds'] == '2'


def test_microseconds_use_exact_decimal_coverage_at_threshold():
    policy = limits(minimum_known_time_fraction='0.999999')
    timeline = CoverageTimeline(START, START+timedelta(seconds=1), policy)
    timeline.mark(START+timedelta(microseconds=1), START+timedelta(seconds=1), sources_known=True)
    assert timeline.finish()['known_fraction'] == '0.999999'


def test_completed_cannot_be_declared_early_or_after_grace(tmp_path):
    wallet, clock = setup(tmp_path)
    with pytest.raises(ValueError, match='termination outside'): wallet.terminate('completed')
    clock.now = START+timedelta(seconds=41)
    with pytest.raises(ValueError, match='termination outside'): wallet.terminate('completed')


def test_missing_terminal_never_passes_even_with_complete_marks(tmp_path):
    wallet, clock = setup(tmp_path)
    populate_flat(wallet, clock)
    report = audit(wallet)['lifecycle']
    assert report['coverage']['coverage_pass']
    assert report['terminal_reason'] == 'missing'
    assert not report['lifecycle_evidence_pass']


def test_abort_is_durable_and_does_not_unseal_outcomes(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.mark({})
    clock.advance()
    wallet.terminate('operator_abort')
    restored = CapturedPaperWallet.resume(wallet.root, expected_protocol_sha256=wallet.protocol_sha256, clock=clock)
    with pytest.raises(ValueError, match='terminated'): restored.mark({})
    with pytest.raises(ValueError, match='closed'):
        restored.enqueue('buy', 'AAA/USDT', 'Buy', created_at=clock.now)
    early = audit_valuation_capture(wallet.root, expected_protocol_sha256=wallet.protocol_sha256, clock=clock)
    assert early['status'] == 'sealed_until_capture_end'
    assert not audit(wallet)['lifecycle']['lifecycle_evidence_pass']


def test_resources_are_checked_before_namespace_creation_and_operation(tmp_path, monkeypatch):
    measured = dict(available_memory_bytes=None, free_disk_bytes=10**9, storage_bytes=0)
    monkeypatch.setattr(capture, 'measure_resources', lambda _: measured)
    with pytest.raises(ValueError, match='resources'): setup(tmp_path)
    assert not (tmp_path/'new-lifecycle').exists()
    measured['available_memory_bytes'] = 10**9
    wallet, clock = setup(tmp_path)
    measured['available_memory_bytes'] = 0
    with pytest.raises(ValueError, match='budget terminated'): wallet.mark({})
    assert wallet.snapshot()['fills'] == []
    assert audit(wallet)['lifecycle']['terminal_reason'] == 'resource_budget'


def test_operation_rate_and_wall_overrun_stop_future_calls(tmp_path, monkeypatch):
    wallet, clock = setup(tmp_path, policy=limits(maximum_operations_per_poll=1))
    wallet.mark({})
    with pytest.raises(ValueError, match='budget terminated'): wallet.mark({})
    assert audit(wallet)['lifecycle']['terminal_reason'] == 'operation_rate_budget'
    other, other_clock = setup(tmp_path/'other')
    times = iter([0, 2000000000])
    monkeypatch.setattr(capture, 'monotonic_ns', lambda: next(times))
    with pytest.raises(ValueError, match='wall budget exceeded'): other.mark({})
    report = audit(other)['lifecycle']
    assert report['terminal_reason'] == 'operation_wall_budget'
    assert not report['operation_wall_budget_pass']


def test_cutoff_blocks_pending_and_bypassed_buy_but_permits_paper_sell(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.enqueue('buy', 'AAA/USDT', 'Buy', created_at=clock.now)
    clock.advance()
    assert wallet.execute('buy', *raw_market(clock))['status'] == 'filled'
    q, r = raw_market(clock)
    wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    clock.now = START+timedelta(seconds=26)
    with pytest.raises(ValueError, match='closed'):
        wallet.enqueue('late-buy', 'BBB/USDT', 'Buy', created_at=clock.now)
    wallet._wallet.enqueue('bypassed-buy', 'BBB/USDT', 'Buy', created_at=clock.now)
    wallet.enqueue('sell', 'AAA/USDT', 'Sell', created_at=clock.now)
    clock.advance()
    with pytest.raises(ValueError, match='cutoff'):
        wallet.execute('bypassed-buy', *raw_market(clock, 'BBB/USDT'))
    assert wallet.execute('sell', *raw_market(clock))['status'] == 'filled'
    assert len(wallet.snapshot()['fills']) == 2


def test_material_inventory_remains_failed_despite_known_marks(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.mark({})
    wallet.enqueue('buy', 'AAA/USDT', 'Buy', created_at=clock.now)
    clock.advance()
    wallet.execute('buy', *raw_market(clock))
    for value in (2, 5, 10, 15, 20, 25, 29):
        clock.now = START+timedelta(seconds=value)
        q, r = raw_market(clock)
        wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    clock.now = START+timedelta(seconds=30)
    wallet.terminate('completed')
    report = audit(wallet)
    assert report['lifecycle']['coverage']['coverage_pass']
    assert report['mark_source_evidence_pass']
    assert not report['lifecycle']['terminal_inventory_closed']
    assert not report['lifecycle']['lifecycle_evidence_pass']


def test_full_closeout_with_fees_and_recorded_dust_is_not_a_profit_claim(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.mark({})
    wallet.enqueue('buy', 'AAA/USDT', 'Buy', created_at=clock.now)
    clock.advance()
    wallet.execute('buy', *raw_market(clock))
    for value in (2, 5, 10, 15, 20, 25):
        clock.now = START+timedelta(seconds=value)
        q, r = raw_market(clock)
        wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    wallet.enqueue('sell', 'AAA/USDT', 'Sell', created_at=clock.now)
    clock.advance(1)
    assert wallet.execute('sell', *raw_market(clock))['status'] == 'filled'
    for value in (26, 29):
        clock.now = START+timedelta(seconds=value)
        q, r = raw_market(clock)
        wallet.mark({'AAA/USDT': q}, {'AAA/USDT': r})
    clock.now = START+timedelta(seconds=30)
    wallet.terminate('completed')
    report = audit(wallet)
    assert report['lifecycle']['lifecycle_evidence_pass']
    assert report['lifecycle']['terminal_inventory_closed']
    assert Decimal(wallet.snapshot()['cash']) < 100
    assert not report['economic_profitability_established']


def test_late_start_and_truncated_tail_fail_endpoint_checks():
    timeline = CoverageTimeline(START, START+timedelta(seconds=30), limits(minimum_known_time_fraction='.5'))
    for offset in (5, 10, 15, 20):
        at = START+timedelta(seconds=offset)
        timeline.invalidate(at)
        timeline.mark(at, at+timedelta(seconds=5), sources_known=True)
    report = timeline.finish()
    assert report['checks']['known_time_fraction']
    assert not report['checks']['leading_endpoint']
    assert not report['checks']['trailing_endpoint']
    assert not report['coverage_pass']


def test_legacy_protocol_does_not_inherit_new_lifecycle_approval(tmp_path):
    from test_paper_valuation_capture import setup as legacy_setup
    wallet, clock = legacy_setup(tmp_path)
    wallet.mark({})
    report = audit_valuation_capture(wallet.root, expected_protocol_sha256=wallet.protocol_sha256,
        clock=lambda: START+timedelta(hours=1))
    assert report['lifecycle']['status'] == 'not_preregistered'
    assert not report['lifecycle']['lifecycle_evidence_pass']


def test_in_memory_frozen_contract_cannot_be_changed_to_bypass_cutoff(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.protocol['lifecycle_plan']['entry_cutoff'] = wallet.protocol['end']
    with pytest.raises(ValueError, match='in-memory'): wallet.mark({})


def test_rehashed_early_termination_cannot_pass_audit(tmp_path):
    wallet, clock = setup(tmp_path)
    wallet.mark({})
    wallet.terminate('operator_abort')
    def rewrite(seq, kind, payload):
        if kind == 'terminated': payload['reason'] = 'completed'
    rewrite_chain(wallet, rewrite)
    with pytest.raises(ValueError, match='termination'): audit(wallet)


@pytest.mark.parametrize('key,value', [('available_memory_bytes', None), ('free_disk_bytes', 0), ('storage_bytes', 10**9)])
def test_unknown_or_insufficient_resources_have_explicit_reason(key, value):
    measured = dict(available_memory_bytes=10**9, free_disk_bytes=10**9, storage_bytes=0)
    measured[key] = value
    assert resource_blocker(limits(), measured) is not None
