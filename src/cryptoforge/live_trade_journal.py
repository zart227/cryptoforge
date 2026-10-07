"""Reconcile Bybit Spot fills to fee-aware FIFO lots in the canonical journal.

SQLite retains immutable executions and an overlapping fetch cursor across restarts.
Only inventory bought or sold through a CryptoForge order is published as a trade.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.supabase_market import SupabaseRestClient, bybit_symbol_to_pair

ZERO = Decimal(0)
DAY_MS = 86_400_000
JsonObject = dict[str, Any]


@dataclass
class Lot:
    fill: JsonObject
    quantity: Decimal
    remaining: Decimal
    cost: Decimal
    fee: Decimal | None
    owned: bool


@dataclass(frozen=True)
class JournalResult:
    executions: int
    closed_segments: int
    open_lots: int
    unmatched_sells: int
    incomplete_fees: int


def decimal(row: JsonObject, key: str) -> Decimal:
    return Decimal(str(row.get(key) or "0"))


def fee_quote(fill: JsonObject) -> Decimal | None:
    """Do not guess fee currency or third-token exchange rates."""
    if fill.get("execFee") in {None, ""} or fill.get("extraFees"):
        return None
    fee = decimal(fill, "execFee")
    if fee == 0:
        return ZERO
    currency = fill.get("feeCurrency")
    base = str(fill["symbol"])[:-4]
    if currency == "USDT":
        return fee
    if currency == base:
        return fee * decimal(fill, "execPrice")
    return None


def owned(fill: JsonObject) -> bool:
    return str(fill.get("orderLinkId") or "").startswith("cf-")


def timestamp(fill: JsonObject) -> str:
    return datetime.fromtimestamp(int(fill["execTime"]) / 1000, UTC).isoformat()


def record(lot: Lot, *, suffix: str, quantity: Decimal, cost: Decimal,
           closed: JsonObject | None = None, pnl: Decimal | None = None,
           fees: Decimal | None = None) -> JsonObject:
    fill = lot.fill
    key = f"bybit:spot:fifo:{fill['execId']}:{suffix}"
    return {
        "external_trade_id": key, "idempotency_key": key,
        "exchange": "bybit", "market_type": "spot", "mode": "live",
        "pair": bybit_symbol_to_pair(str(fill["symbol"])), "timeframe": "5m", "side": "long",
        "status": "closed" if closed else ("open" if quantity > 0 else "cancelled"),
        "opened_at": timestamp(fill), "closed_at": timestamp(closed) if closed else None,
        "entry_price": str(decimal(fill, "execPrice")),
        "exit_price": str(decimal(closed, "execPrice")) if closed else None,
        "amount": str(quantity), "stake_amount": str(cost),
        "fee_amount": str(fees) if fees is not None else None,
        "realized_pnl": str(pnl) if pnl is not None else None,
        "realized_pnl_pct": str(pnl / cost) if pnl is not None and cost > 0 else None,
        "entry_reason": f"FIFO execution={fill['execId']} order={fill.get('orderId')} origin={'cryptoforge' if lot.owned else 'external'}",
        "exit_reason": (f"FIFO execution={closed['execId']} order={closed.get('orderId')} origin={'cryptoforge' if owned(closed) else 'external'}" if closed else None),
    }


def reconstruct_trades(fills: list[JsonObject]) -> tuple[list[JsonObject], JournalResult]:
    inventory: dict[str, deque[Lot]] = defaultdict(deque)
    lots: list[Lot] = []
    records: list[JsonObject] = []
    unmatched = 0
    seen: set[str] = set()
    for fill in sorted(fills, key=lambda r: (int(r["execTime"]), str(r["execId"]), str(r.get("orderId")), str(r.get("leavesQty")))):
        exec_id = str(fill["execId"])
        if exec_id in seen:
            continue
        seen.add(exec_id)
        symbol = str(fill["symbol"])
        if not symbol.endswith("USDT") or fill.get("execType", "Trade") != "Trade":
            continue
        qty, price = decimal(fill, "execQty"), decimal(fill, "execPrice")
        if qty <= 0 or price <= 0:
            raise ValueError("nonpositive execution quantity or price")
        value = decimal(fill, "execValue") if fill.get("execValue") not in {None, ""} else qty * price
        fee = fee_quote(fill)
        raw_fee = decimal(fill, "execFee")
        base_fee = raw_fee if fill.get("feeCurrency") == symbol[:-4] else ZERO
        quote_fee = raw_fee if fill.get("feeCurrency") == "USDT" else ZERO
        if fill.get("side") == "Buy":
            received = qty - base_fee
            if received <= 0:
                raise ValueError("buy fee consumes entire fill")
            lot = Lot(fill, received, received, value + quote_fee, fee, owned(fill))
            inventory[symbol].append(lot)
            lots.append(lot)
        elif fill.get("side") == "Sell":
            consumed = qty + base_fee
            if consumed <= 0:
                raise ValueError("invalid sell fee")
            remaining = consumed
            while remaining > 0 and inventory[symbol]:
                lot = inventory[symbol][0]
                matched = min(remaining, lot.remaining)
                cost = lot.cost * matched / lot.quantity
                proceeds = (value - quote_fee) * matched / consumed
                known = fee is not None and lot.fee is not None
                fees = (lot.fee * matched / lot.quantity + fee * matched / consumed) if known else None
                if lot.owned or owned(fill):
                    records.append(record(lot, suffix=exec_id, quantity=matched, cost=cost,
                                          closed=fill, pnl=proceeds - cost if known else None, fees=fees))
                lot.remaining -= matched
                remaining -= matched
                if lot.remaining == 0:
                    inventory[symbol].popleft()
            if remaining > 0:
                # Without an acquisition cost, publishing a profit would be fabricated.
                unmatched += 1
    for lot in lots:
        if lot.owned:
            fraction = lot.remaining / lot.quantity
            records.append(record(lot, suffix="remaining", quantity=lot.remaining,
                                  cost=lot.cost * fraction,
                                  fees=lot.fee * fraction if lot.fee is not None else None))
    return records, JournalResult(
        executions=len(seen), closed_segments=sum(r["status"] == "closed" for r in records),
        open_lots=sum(r["status"] == "open" for r in records), unmatched_sells=unmatched,
        incomplete_fees=sum(r["status"] == "closed" and r["realized_pnl"] is None for r in records),
    )


def default_cache_path(bybit: BybitPrivateClient) -> Path:
    identity = hashlib.sha256(bybit.api_key.encode()).hexdigest()[:16]
    return Path(os.environ.get("CRYPTOFORGE_DATA_DIR", "data")) / f"live-journal-{identity}.sqlite"


def sync_live_journal(*, bybit: BybitPrivateClient, supabase: SupabaseRestClient,
                      cache_path: Path | None = None, now: datetime | None = None,
                      since: datetime | None = None) -> JournalResult:
    now = now or datetime.now(UTC)
    end_ms = int(now.timestamp() * 1000)
    path = cache_path or default_cache_path(bybit)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=30) as db:
        db.execute("create table if not exists executions (exec_id text primary key, payload text not null)")
        db.execute("create table if not exists journal_state (id integer primary key check (id=1), start_ms integer not null, cursor_ms integer not null)")
        db.commit()
        # Serialize standalone reconciliation and executor reconciliation on this cache.
        db.execute("begin immediate")
        state = db.execute("select start_ms, cursor_ms from journal_state where id=1").fetchone()
        initial_ms = int((since or now - timedelta(days=30)).timestamp() * 1000)
        if state and since is not None and initial_ms != state[0]:
            raise ValueError("the journal history start cannot be changed after initialization")
        start_ms = max(state[0], state[1] - DAY_MS) if state else initial_ms
        if start_ms > end_ms:
            raise ValueError("journal history start is in the future")
        while start_ms <= end_ms:
            window_end = min(start_ms + 7 * DAY_MS - 1, end_ms)
            fills = bybit.get_spot_executions(start_ms=start_ms, end_ms=window_end)
            for fill in fills:
                if not fill.get("execId") or not fill.get("execTime"):
                    raise ValueError("execution identity/time missing")
                db.execute("insert into executions values (?, ?) on conflict(exec_id) do update set payload=excluded.payload",
                           (str(fill["execId"]), json.dumps(fill, sort_keys=True)))
            start_ms = window_end + 1
        fills = [json.loads(row[0]) for row in db.execute("select payload from executions")]
        trades, result = reconstruct_trades(fills)
        # One transaction at the REST endpoint prevents partially published lot balances.
        supabase.upsert("trades", trades, on_conflict="idempotency_key")
        health = {
            "component": "live_trade_journal", "status": "warning" if result.unmatched_sells or result.incomplete_fees else "ok",
            "observed_at": now.isoformat(), "message": "Bybit Spot FIFO journal reconciled",
            "payload": {**result.__dict__, "history_start": datetime.fromtimestamp((state[0] if state else initial_ms) / 1000, UTC).isoformat()},
        }
        supabase.upsert("bot_health", [health], on_conflict="component")
        db.execute("insert into journal_state values (1, ?, ?) on conflict(id) do update set cursor_ms=excluded.cursor_ms",
                   (state[0] if state else initial_ms, end_ms))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile actual Bybit Spot executions; never submits orders.")
    parser.add_argument("--since", help="Initial history boundary, ISO timestamp; default: 30 days ago")
    parser.add_argument("--cache-path", type=Path)
    args = parser.parse_args()
    bybit = BybitPrivateClient.from_env()
    bybit.synchronize_time()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None
    if since is not None:
        since = since.replace(tzinfo=UTC) if since.tzinfo is None else since.astimezone(UTC)
    result = sync_live_journal(bybit=bybit, supabase=SupabaseRestClient.from_env(), cache_path=args.cache_path,
                               since=since)
    print(json.dumps(result.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
