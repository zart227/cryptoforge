from dataclasses import replace
from datetime import UTC,datetime,timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.equity_blocks import daily_changes,block_interval
from cryptoforge.trade_simulator import SimulationResult


def test_midnight_closes_belong_to_previous_day_and_changes_reconcile():
    start=datetime(2026,1,1,tzinfo=UTC)
    outcome=SimulationResult((),(),((start+timedelta(days=1),D('101')),(start+timedelta(days=2),D('99'))),D('99'),D('.02'))
    report=daily_changes(outcome,initial_capital='100');changes=report['daily_changes_fraction_initial_capital']
    assert changes=={'2026-01-01':'0.01','2026-01-02':'-0.02'}
    assert sum(map(D,changes.values()))==D('-.01')
    with pytest.raises(ValueError,match='missing equity day'):
        daily_changes(replace(outcome,equity=(outcome.equity[0],(start+timedelta(days=3),D('99')))),initial_capital='100')


def test_sparse_calendar_data_has_no_confidence_claim():
    report=block_interval({'2026-01-01':'.1','2026-01-02':'.1'})
    assert report['status']=='insufficient_calendar_days' and report['interval_lower'] is None
    assert not report['live_promotion_allowed']


def test_fixed_block_resampling_is_deterministic_and_preserves_constant_returns():
    changes={f'2026-01-{day:02}':'-.001' for day in range(1,16)}
    a=block_interval(changes);b=block_interval(changes)
    assert a==b and a['interval_upper']<0 and a['interval_lower']<0


def test_bootstrap_rejects_missing_calendar_days_even_when_count_is_sufficient():
    changes={f'2026-01-{day:02}':'.001' for day in range(1,17) if day!=5}
    with pytest.raises(ValueError,match='calendar'):block_interval(changes)


def test_partial_boundary_days_are_not_counted_as_full_bootstrap_days():
    start=datetime(2026,1,1,12,tzinfo=UTC)
    marks=tuple((start+timedelta(hours=i+1),D(100)) for i in range(72))
    outcome=SimulationResult((),(),marks,D(100),D(0))
    report=daily_changes(outcome,initial_capital='100')
    assert report['partial_boundary_days']==['2026-01-01','2026-01-04']
    assert list(report['bootstrap_eligible_full_days'])==['2026-01-02','2026-01-03']


@pytest.mark.parametrize('seed',[True,1.5,float('nan'),'20261011'])
def test_noninteger_bootstrap_seeds_are_rejected_before_resampling(seed):
    with pytest.raises(ValueError,match='integer bootstrap seed'):
        block_interval({},seed=seed)
