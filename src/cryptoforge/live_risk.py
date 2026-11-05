from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import fcntl
import json
from pathlib import Path
from typing import Any
from cryptoforge.atomic_reports import write_json_report


def count_open_spot_positions(coins: list[dict[str, Any]], *, minimum_usd: Decimal = Decimal("1")) -> int:
    return sum(
        1
        for coin in coins
        if str(coin.get("coin")) != "USDT"
        and Decimal(str(coin.get("usdValue") or "0")) >= minimum_usd
    )


def dynamic_entry_capacity(
    *,
    total_equity: Decimal,
    free_usdt: Decimal,
    stake_amount: Decimal,
    open_positions: int,
    hard_position_cap: int,
) -> tuple[int, int, int]:
    if stake_amount <= 0:
        raise ValueError("stake_amount must be positive")
    equity_capacity = int(total_equity // stake_amount)
    effective_max_positions = min(max(hard_position_cap, 0), equity_capacity)
    cash_entry_slots = int(free_usdt // stake_amount)
    available_entry_slots = min(
        max(effective_max_positions - max(open_positions, 0), 0),
        cash_entry_slots,
    )
    return equity_capacity, effective_max_positions, available_entry_slots


def daily_equity_blockers(
    *,
    current_equity: Decimal,
    maximum_loss: Decimal,
    state_path: Path,
    now: datetime,
) -> tuple[str, ...]:
    """Fail closed on missing/corrupt state; preserve the existing UTC baseline.

    Initial provisioning/recovery must supply an independently reviewed baseline.
    A valid previous-day state may roll forward under the same UTC policy.
    """
    if (not isinstance(current_equity, Decimal) or not isinstance(maximum_loss, Decimal)
            or now.tzinfo is None or now.utcoffset() is None
            or not current_equity.is_finite() or current_equity < 0
            or not maximum_loss.is_finite() or maximum_loss <= 0):
        return ('daily equity risk input invalid; new entries paused',)
    day = now.astimezone(UTC).date()
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # Lock a stable sidecar: atomic replacement changes the state inode.
        lock_path = state_path.with_name(state_path.name + '.lock')
        with lock_path.open('a') as lock:
            lock_path.chmod(0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if not isinstance(state, dict) or not isinstance(state.get('date'), str):
                raise ValueError('invalid state object')
            state_day = date.fromisoformat(state['date'])
            if state_day.isoformat() != state['date'] or state_day > day:
                raise ValueError('invalid state day')
            if not isinstance(state.get('start_equity'), str):
                raise ValueError('invalid baseline type')
            start_equity = Decimal(state['start_equity'])
            if not start_equity.is_finite() or start_equity < 0:
                raise ValueError('invalid baseline value')
            if state.get('timezone', 'UTC') != 'UTC':
                raise ValueError('incompatible baseline timezone')
            if state_day < day:
                start_equity = current_equity
                write_json_report(state_path, {'date': day.isoformat(),
                    'start_equity': format(start_equity, 'f'), 'timezone': 'UTC'})
            loss = start_equity - current_equity
            if loss >= maximum_loss:
                return (f'daily equity loss limit reached: {loss:.8f} >= {maximum_loss:.8f} USDT',)
            return ()
    except (OSError, ValueError, TypeError, InvalidOperation):
        return ('daily equity risk state unavailable or invalid; new entries paused pending baseline recovery',)
