from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from cryptoforge import telegram_daily_summary as daily


def test_moscow_period_groups_fifo_segments_and_counts_outcomes():
    paths = []
    class Client:
        def _get_rows(self, path):
            paths.append(path)
            if path.startswith('bot_health'):
                return [{'status': 'ok', 'observed_at': '2026-10-09T21:02:00Z'}]
            return [
                {'exit_reason': 'FIFO order=a origin=cryptoforge', 'realized_pnl': '2', 'fee_amount': '.1'},
                {'exit_reason': 'FIFO order=a origin=cryptoforge', 'realized_pnl': '-1', 'fee_amount': '.1'},
                {'exit_reason': 'FIFO order=b origin=cryptoforge', 'realized_pnl': '-.5', 'fee_amount': '.2'},
            ]
    exchange = SimpleNamespace(get_unified_usdt_balance=lambda: SimpleNamespace(total_equity_usd=Decimal('20'), usdt_wallet_balance=Decimal('10')))
    text = daily.render_daily_summary(Client(), date(2026, 10, 9), bybit=exchange, now=datetime(2026, 10, 9, 21, 5, tzinfo=UTC))
    assert 'продаж): 2' in text
    assert 'Прибыльных: 1 · Убыточных: 1' in text
    assert '+0.500000 USDT' in text
    assert '0.400000 USDT' in text
    assert '20.0000 USD' in text
    from urllib.parse import unquote
    assert '2026-10-08T21:00:00+00:00' in unquote(paths[-1])
    assert '2026-10-09T21:00:00+00:00' in unquote(paths[-1])


def test_daily_schedule_retry_and_no_duplicate_after_restart(monkeypatch, tmp_path):
    path = tmp_path / 'state.json'
    sent = []
    notifier = SimpleNamespace(notify=lambda message: (sent.append(message) or SimpleNamespace(sent=True)))
    monkeypatch.setattr(daily, 'render_daily_summary', lambda client, day, **kw: str(day))
    run = lambda now: daily.daily_summary_once(client=None, notifier=notifier, state_path=path, now=now)
    assert run(datetime(2026, 10, 9, 12, tzinfo=UTC)) == 0
    assert run(datetime(2026, 10, 9, 21, 4, tzinfo=UTC)) == 0
    notifier.notify = lambda message: SimpleNamespace(sent=False)
    assert run(datetime(2026, 10, 9, 21, 5, tzinfo=UTC)) == 0
    notifier.notify = lambda message: (sent.append(message) or SimpleNamespace(sent=True))
    assert run(datetime(2026, 10, 9, 21, 6, tzinfo=UTC)) == 1
    assert run(datetime(2026, 10, 9, 21, 7, tzinfo=UTC)) == 0
    assert len(sent) == 1
