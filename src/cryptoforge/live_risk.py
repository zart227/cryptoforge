from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from typing import Any


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
    day = now.date().isoformat()
    state: dict[str, str] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            state = {}
    if state.get("date") != day:
        state = {"date": day, "start_equity": format(current_equity, "f")}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    start_equity = Decimal(state["start_equity"])
    loss = start_equity - current_equity
    if loss >= maximum_loss:
        return (f"daily equity loss limit reached: {loss:.8f} >= {maximum_loss:.8f} USDT",)
    return ()
