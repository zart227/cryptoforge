from dataclasses import replace
from datetime import UTC, datetime, timedelta
import pytest
from cryptoforge.model_training import TrainingExample
from cryptoforge.train_window import prepare_training_window

END = datetime(2026, 10, 11, tzinfo=UTC)


def rows():
    return [TrainingExample('BTC/USDT', END-timedelta(days=days), (0.,)*7,
                            1, 0, .01, END-timedelta(hours=1)) for days in (4, 2, 1)]


def test_window_boundary_and_recency_are_target_independent():
    result = prepare_training_window(rows(), train_end=END, window_days=2, half_life_days=1)
    assert len(result.rows) == 2
    assert result.weights[1] == pytest.approx(2 * result.weights[0])
    assert sum(result.weights) == pytest.approx(2)
    assert result.effective_sample_size == pytest.approx(1.8)
    changed = [replace(row, label=0, future_return=-.5) for row in rows()]
    assert prepare_training_window(changed, train_end=END, window_days=2,
                                   half_life_days=1).weights == result.weights
    assert not result.live_eligible


def test_uniform_and_input_order_invariance():
    result = prepare_training_window(rows(), train_end=END, window_days=4)
    assert result.weights == (1., 1., 1.)
    assert result.effective_sample_size == 3
    assert result == prepare_training_window(list(reversed(rows())), train_end=END, window_days=4)


@pytest.mark.parametrize('change', [dict(label_end_time=END+timedelta(seconds=1)),
                                  dict(open_time=END), dict(label_end_time=None)])
def test_future_and_missing_availability_fail_even_outside_window(change):
    data = rows(); data[0] = replace(data[0], **change)
    with pytest.raises(ValueError):
        prepare_training_window(data, train_end=END, window_days=2)


def test_duplicate_and_underflow_fail():
    with pytest.raises(ValueError, match='duplicate'):
        prepare_training_window(rows()+[rows()[0]], train_end=END, window_days=2)
    with pytest.raises(ValueError, match='underflow'):
        prepare_training_window(rows(), train_end=END, window_days=4, half_life_days=1e-10)
