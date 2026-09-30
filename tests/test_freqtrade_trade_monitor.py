from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from cryptoforge.freqtrade_trade_monitor import monitor_once
from cryptoforge.notifications import Notification


@dataclass
class RecordingNotifier:
    notifications: list[Notification] = field(default_factory=list)

    def notify(self, notification: Notification):  # type: ignore[no-untyped-def]
        self.notifications.append(notification)

        class Result:
            sent = True

        return Result()


def create_db(path):  # type: ignore[no-untyped-def]
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            create table trades (
                id integer primary key,
                pair text not null,
                is_open integer not null,
                open_date text,
                close_date text,
                open_rate real,
                close_rate real,
                amount real,
                stake_amount real,
                close_profit_abs real,
                close_profit real,
                exit_reason text
            )
            """
        )


def insert_trade(path, **values):  # type: ignore[no-untyped-def]
    defaults = {
        "id": 1,
        "pair": "XRP/USDT",
        "is_open": 1,
        "open_date": "2026-09-30 10:00:00",
        "close_date": None,
        "open_rate": 2.5,
        "close_rate": None,
        "amount": 2.0,
        "stake_amount": 5.0,
        "close_profit_abs": None,
        "close_profit": None,
        "exit_reason": None,
    }
    defaults.update(values)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            insert into trades (
                id, pair, is_open, open_date, close_date, open_rate,
                close_rate, amount, stake_amount, close_profit_abs,
                close_profit, exit_reason
            ) values (
                :id, :pair, :is_open, :open_date, :close_date, :open_rate,
                :close_rate, :amount, :stake_amount, :close_profit_abs,
                :close_profit, :exit_reason
            )
            """,
            defaults,
        )


def test_monitor_sends_open_position_once(tmp_path) -> None:
    db_path = tmp_path / "trades.sqlite"
    state_path = tmp_path / "state.json"
    create_db(db_path)
    insert_trade(db_path)
    notifier = RecordingNotifier()

    result = monitor_once(db_path=db_path, state_path=state_path, notifier=notifier)
    second = monitor_once(db_path=db_path, state_path=state_path, notifier=notifier)

    assert result.opened_sent == 1
    assert second.opened_sent == 0
    assert len(notifier.notifications) == 1
    rendered = notifier.notifications[0].render()
    assert "position opened" in rendered
    assert "XRP/USDT" in rendered
    assert "stake_amount: 5.0" in rendered


def test_monitor_sends_closed_position_with_profit_and_loss(tmp_path) -> None:
    db_path = tmp_path / "trades.sqlite"
    state_path = tmp_path / "state.json"
    create_db(db_path)
    insert_trade(
        db_path,
        is_open=0,
        close_date="2026-09-30 10:30:00",
        close_rate=2.55,
        close_profit_abs=0.1,
        close_profit=0.02,
        exit_reason="roi",
    )
    insert_trade(
        db_path,
        id=2,
        pair="BTC/USDT",
        is_open=0,
        close_date="2026-09-30 11:30:00",
        close_rate=99,
        close_profit_abs=-0.05,
        close_profit=-0.01,
        exit_reason="stop_loss",
    )
    notifier = RecordingNotifier()

    result = monitor_once(db_path=db_path, state_path=state_path, notifier=notifier)

    assert result.opened_sent == 2
    assert result.closed_sent == 2
    messages = [notification.render() for notification in notifier.notifications]
    assert any("profit +0.1" in message for message in messages)
    assert any("loss -0.05" in message for message in messages)
    assert any("realized_pnl_pct: 2.0000%" in message for message in messages)
    assert any("realized_pnl_pct: -1.0000%" in message for message in messages)
