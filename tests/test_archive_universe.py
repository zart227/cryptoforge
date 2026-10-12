from decimal import Decimal
from dataclasses import replace
from cryptoforge.market_data import Candle
from cryptoforge.archive_universe import daily_membership,DAY_MS


def candles():
    return [Candle('BTCUSDT','60',i*3600000,Decimal(100),Decimal(101),Decimal(99),Decimal(100),
                   Decimal(1),Decimal(100000)) for i in range(48)]


def test_membership_uses_completed_previous_day_without_future_volume():
    rows=candles();history=daily_membership(rows)
    assert history[0]['effective_at_ms']==DAY_MS and history[0]['included']
    rows[24:]=[replace(c,turnover=Decimal(0)) for c in rows[24:]]
    changed=daily_membership(rows)
    assert changed[0]==history[0]
    assert changed[1]['included'] is False
    assert daily_membership(rows[1:])[0]['included'] is False
