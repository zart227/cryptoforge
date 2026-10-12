from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.validation_threshold import ValidationPortfolio, select_validation_threshold

START = datetime(2026, 10, 1, tzinfo=UTC)
END = START + timedelta(days=7)
SHA = 'a' * 64


def trial(threshold, net=2, stress=1):
    return ValidationPortfolio(D(threshold), 'validation', START, END, SHA,
                               'b'*64, D(100), D(net), D(stress), D('.02'), D('.03'), 20, 20)


def select(results, **changes):
    options=dict(declared_thresholds=['.5','.6'], validation_start=START,
                 validation_end=END, study_sha256=SHA, minimum_trades=10,
                 maximum_drawdown='.05')
    options.update(changes)
    return select_validation_threshold(results, **options)


def test_stress_return_ranks_before_optimistic_net_and_input_order():
    rows=[trial('.5', 8, 1), trial('.6', 3, 2)]
    result=select(rows)
    assert result['selected_threshold'] == '0.6'
    assert result == select(list(reversed(rows)))
    assert not result['live_promotion_allowed']


@pytest.mark.parametrize('change', [dict(role='test'), dict(end=END+timedelta(days=1)),
                                   dict(study_sha256='c'*64), dict(initial_cash=D(200))])
def test_test_scope_and_mismatched_trials_fail(change):
    with pytest.raises(ValueError):
        select([trial('.5'), replace(trial('.6'), **change)])


def test_missing_duplicate_and_equivalent_grid_values_fail():
    for rows in ([trial('.5')], [trial('.5'),trial('.5')]):
        with pytest.raises(ValueError):select(rows)
    with pytest.raises(ValueError):
        select([trial('.5')], declared_thresholds=['.5','0.50'])


def test_zero_trades_negative_stress_and_excessive_stress_drawdown_cannot_win():
    assert select([replace(trial('.5',100,100),trade_count=0),
                   trial('.6',10,-1)])['selected_threshold'] is None
    assert select([replace(trial('.5'),stress_max_drawdown=D('.06')),
                   trial('.6',-1,1)])['selected_threshold'] is None


def test_tie_is_deterministic_and_nonfinite_metric_refused():
    assert select([trial('.5'),trial('.6')])['selected_threshold'] == '0.6'
    with pytest.raises(ValueError,match='finite'):
        select([trial('.5'),replace(trial('.6'),net_pnl=D('NaN'))])


def test_tiny_stress_execution_sample_cannot_qualify_profitable_threshold():
    result=select([replace(trial('.5',100,100),stress_trade_count=1),trial('.6',-1,-1)])
    assert result['selected_threshold'] is None
