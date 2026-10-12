"""Daily Telegram results for Moscow calendar days, delivered after reconciliation."""
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.notifications import Notification, NotificationKind

MOSCOW = ZoneInfo('Europe/Moscow')


def closed_order_key(row):
    match = re.search(r'\border=([^\s]+)', str(row.get('exit_reason') or ''))
    return match.group(1) if match else str(row.get('external_trade_id') or row.get('id'))


def render_daily_summary(client, day: date, *, bybit=None, now=None):
    now = now or datetime.now(UTC)
    start = datetime.combine(day, time(), MOSCOW).astimezone(UTC)
    end = start + timedelta(days=1)
    health = client._get_rows('bot_health?' + urlencode({'component': 'eq.live_trade_journal', 'select': 'status,observed_at', 'limit': '1'}))
    if not health or health[0]['status'] != 'ok' or datetime.fromisoformat(health[0]['observed_at'].replace('Z', '+00:00')) < end:
        raise RuntimeError('daily journal not reconciled yet')
    rows = []
    while True:
        query = urlencode({'select': '*', 'mode': 'eq.live', 'status': 'eq.closed',
            'and': f'(closed_at.gte.{start.isoformat()},closed_at.lt.{end.isoformat()})',
            'order': 'closed_at.asc,id.asc', 'limit': '500', 'offset': str(len(rows))})
        batch = client._get_rows('trades?' + query)
        rows.extend(batch)
        if len(batch) < 500:
            break
    groups = {}
    for row in rows:
        groups.setdefault(closed_order_key(row), []).append(row)
    wins = losses = neutral = unknown = 0
    pnl = Decimal(0)
    fees = Decimal(0)
    missing_fees = False
    for group in groups.values():
        if any(r.get('realized_pnl') is None for r in group):
            unknown += 1
        else:
            result = sum((Decimal(str(r['realized_pnl'])) for r in group), Decimal(0))
            pnl += result
            wins += result > 0
            losses += result < 0
            neutral += result == 0
        missing_fees |= any(r.get('fee_amount') is None for r in group)
        fees += sum((Decimal(str(r['fee_amount'])) for r in group if r.get('fee_amount') is not None), Decimal(0))
    exchange = bybit or BybitPrivateClient.from_env()
    if bybit is None:
        exchange.synchronize_time()
    balance = exchange.get_unified_usdt_balance()
    lines = [f'Итоги CryptoForge за {day:%d.%m.%Y} (Москва)',
             f'Закрытий сделок (исполненных продаж): {len(groups)}',
             f'Прибыльных: {wins} · Убыточных: {losses} · Без результата: {neutral}',
             f'Прибыль/убыток после комиссий: {pnl:+.6f} USDT' + (' (по полным записям)' if unknown else ''),
             f'Комиссии: {fees:.6f} USDT' + (' (данные неполные)' if missing_fees else ''),
             f'Текущая стоимость аккаунта: {balance.total_equity_usd:.4f} USD',
             f'Баланс USDT: {balance.usdt_wallet_balance:.4f}',
             f'Баланс на {now.astimezone(MOSCOW):%d.%m.%Y %H:%M} МСК; это не изменение баланса за день.']
    if unknown:
        lines.append(f'Закрытий с неполными данными PnL: {unknown}')
    return '\n'.join(lines)


def daily_summary_once(*, client, notifier, state_path, now=None):
    now = now or datetime.now(UTC)
    local = now.astimezone(MOSCOW)
    path = Path(state_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'last_day': (local.date() - timedelta(days=1)).isoformat()}), encoding='utf-8')
        return 0
    state = json.loads(path.read_text(encoding='utf-8'))
    day = date.fromisoformat(state['last_day']) + timedelta(days=1)
    if day >= local.date() or local.time() < time(0, 5):
        return 0
    try:
        text = render_daily_summary(client, day, now=now)
        result = notifier.notify(Notification(NotificationKind.DAILY_SUMMARY, '', text))
        if not result.sent:
            return 0
    except Exception as exc:
        print(f'daily_summary=pending error_type={type(exc).__name__}', flush=True)
        return 0
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'last_day': day.isoformat()}), encoding='utf-8')
    temporary.replace(path)
    return 1
