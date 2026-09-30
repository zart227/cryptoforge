from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptoforge.notifications import (
    Notification,
    NotificationKind,
    telegram_notifier_from_env,
)


@dataclass(frozen=True)
class FreqtradeTrade:
    id: int
    pair: str
    is_open: bool
    open_date: str | None
    close_date: str | None
    open_rate: object
    close_rate: object
    amount: object
    stake_amount: object
    close_profit_abs: object
    close_profit: object
    exit_reason: str | None


@dataclass(frozen=True)
class MonitorState:
    opened_trade_ids: tuple[int, ...] = ()
    closed_trade_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class MonitorResult:
    scanned: int
    opened_sent: int
    closed_sent: int
    failed: int


def monitor_once(*, db_path: str | Path, state_path: str | Path, notifier: Any) -> MonitorResult:
    trades = read_trades(Path(db_path))
    state_file = Path(state_path)
    state = load_state(state_file)
    opened_ids = set(state.opened_trade_ids)
    closed_ids = set(state.closed_trade_ids)
    opened_sent = 0
    closed_sent = 0
    failed = 0

    for trade in trades:
        if trade.id not in opened_ids:
            result = notifier.notify(open_notification(trade))
            if not result.sent:
                failed += 1
                break
            opened_ids.add(trade.id)
            opened_sent += 1

        if not trade.is_open and trade.id not in closed_ids:
            result = notifier.notify(close_notification(trade))
            if not result.sent:
                failed += 1
                break
            closed_ids.add(trade.id)
            closed_sent += 1

    save_state(
        state_file,
        MonitorState(
            opened_trade_ids=tuple(sorted(opened_ids)[-1000:]),
            closed_trade_ids=tuple(sorted(closed_ids)[-1000:]),
        ),
    )
    return MonitorResult(
        scanned=len(trades),
        opened_sent=opened_sent,
        closed_sent=closed_sent,
        failed=failed,
    )


def read_trades(db_path: Path) -> list[FreqtradeTrade]:
    if not db_path.exists():
        return []
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table_names = {
            str(row["name"])
            for row in conn.execute("select name from sqlite_master where type = 'table'")
        }
        if "trades" not in table_names:
            return []
        columns = {
            str(row["name"])
            for row in conn.execute("pragma table_info(trades)")
        }
        selected = [
            "id",
            "pair",
            "is_open",
            "open_date",
            "close_date",
            "open_rate",
            "close_rate",
            "amount",
            "stake_amount",
            "close_profit_abs",
            "close_profit",
            "exit_reason",
        ]
        expressions = [
            column if column in columns else f"null as {column}"
            for column in selected
        ]
        rows = conn.execute(
            f"select {', '.join(expressions)} from trades order by id asc"
        ).fetchall()

    return [
        FreqtradeTrade(
            id=int(row["id"]),
            pair=str(row["pair"]),
            is_open=bool(row["is_open"]),
            open_date=none_or_str(row["open_date"]),
            close_date=none_or_str(row["close_date"]),
            open_rate=row["open_rate"],
            close_rate=row["close_rate"],
            amount=row["amount"],
            stake_amount=row["stake_amount"],
            close_profit_abs=row["close_profit_abs"],
            close_profit=row["close_profit"],
            exit_reason=none_or_str(row["exit_reason"]),
        )
        for row in rows
    ]


def open_notification(trade: FreqtradeTrade) -> Notification:
    return Notification(
        kind=NotificationKind.TRADE_OPENED,
        title="CryptoForge: position opened",
        body=trade.pair,
        fields={
            "trade_id": trade.id,
            "opened_at": trade.open_date,
            "entry_price": trade.open_rate,
            "amount": trade.amount,
            "stake_amount": trade.stake_amount,
        },
    )


def close_notification(trade: FreqtradeTrade) -> Notification:
    pnl = number_or_zero(trade.close_profit_abs)
    return Notification(
        kind=NotificationKind.TRADE_CLOSED,
        title="CryptoForge: position closed",
        body=f"{trade.pair} {profit_label(pnl)}",
        fields={
            "trade_id": trade.id,
            "closed_at": trade.close_date,
            "exit_reason": trade.exit_reason,
            "entry_price": trade.open_rate,
            "exit_price": trade.close_rate,
            "realized_pnl": trade.close_profit_abs,
            "realized_pnl_pct": percent_value(trade.close_profit),
        },
    )


def load_state(path: Path) -> MonitorState:
    if not path.exists():
        return MonitorState()
    data = json.loads(path.read_text(encoding="utf-8"))
    return MonitorState(
        opened_trade_ids=tuple(int(value) for value in data.get("opened_trade_ids", [])),
        closed_trade_ids=tuple(int(value) for value in data.get("closed_trade_ids", [])),
    )


def save_state(path: Path, state: MonitorState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "opened_trade_ids": list(state.opened_trade_ids),
                "closed_trade_ids": list(state.closed_trade_ids),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def default_db_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get("CRYPTOFORGE_FREQTRADE_DB")
    if explicit:
        return sqlite_db_path(explicit)
    return Path("./data/live-pilot/tradesv3.paper.sqlite")


def default_state_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get("CRYPTOFORGE_TRADE_MONITOR_STATE")
    if explicit:
        return Path(explicit)
    data_dir = Path(env.get("CRYPTOFORGE_DATA_DIR", "./data"))
    return data_dir / "freqtrade-trade-monitor-state.json"


def sqlite_db_path(value: str) -> Path:
    if value.startswith("sqlite:///"):
        return Path(value.removeprefix("sqlite:///"))
    return Path(value)


def none_or_str(value: object) -> str | None:
    return None if value is None else str(value)


def number_or_zero(value: object) -> float:
    if value is None:
        return 0.0
    return float(value)


def percent_value(value: object) -> str | None:
    if value is None:
        return None
    return f"{float(value) * 100:.4f}%"


def profit_label(pnl: float) -> str:
    if pnl > 0:
        return f"profit +{pnl:.8g}"
    if pnl < 0:
        return f"loss {pnl:.8g}"
    return "breakeven"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send Telegram notifications for Freqtrade open/closed positions.")
    parser.add_argument("--db-path", default=str(default_db_path()))
    parser.add_argument("--state-path", default=str(default_state_path()))
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)

    notifier = telegram_notifier_from_env()
    while True:
        result = monitor_once(
            db_path=args.db_path,
            state_path=args.state_path,
            notifier=notifier,
        )
        print(
            "trade monitor: "
            f"scanned={result.scanned} opened_sent={result.opened_sent} "
            f"closed_sent={result.closed_sent} failed={result.failed}",
            flush=True,
        )
        if not args.watch:
            return 1 if result.failed else 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
