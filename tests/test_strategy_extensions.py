from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import pytest
from cryptoforge.strategy_extensions import extension_signal,ExtensionSpec
from test_trade_simulator import history


def signal(rows,family):return extension_signal(rows,31,ExtensionSpec(family),as_of=rows[31].open_time+timedelta(minutes=5))


def test_support_touch_and_recovery_requires_known_volume_confirmation():
    rows=history(count=40);rows[31]=replace(rows[31],low=D('98.9'),close=D('100.5'),volume=D(2000))
    result=signal(rows,'support_bounce');assert result['would_enter'] and not result['live_eligible']
    rows[31]=replace(rows[31],volume=D(100))
    assert not signal(rows,'support_bounce')['would_enter']


def test_compression_breakout_excludes_breakout_bar_from_atr_and_high_reference():
    rows=history(count=40)
    rows[:31]=[replace(row,high=D(105),low=D(95)) for row in rows[:31]]
    rows[26:31]=[replace(row,high=D('100.1'),low=D('99.9')) for row in rows[26:31]]
    rows[31]=replace(rows[31],close=D(106),high=D(107),volume=D(2000))
    assert signal(rows,'compression_breakout')['would_enter']
    rows[31]=replace(rows[31],close=D(104))
    assert not signal(rows,'compression_breakout')['would_enter']


def test_future_prices_do_not_change_extension_and_late_input_is_rejected():
    rows=history(count=40);before=signal(rows,'support_bounce')
    changed=rows[:32]+[replace(row,open=D(500),close=D(500),high=D(600),low=D(1)) for row in rows[32:]]
    assert signal(changed,'support_bounce')==before
    rows[3]=replace(rows[3],cache_observed_at=rows[32].open_time+timedelta(seconds=1))
    with pytest.raises(ValueError,match='unavailable'):signal(rows,'support_bounce')


def test_zero_volume_cannot_create_extension_entry():
    rows=[replace(row,volume=D(0)) for row in history(count=40)]
    assert not signal(rows,'support_bounce')['would_enter']
    assert not signal(rows,'compression_breakout')['would_enter']
