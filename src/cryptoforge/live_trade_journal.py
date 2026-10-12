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
    conversion_events: int = 0


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
        "exit_reason": (f"FIFO execution={closed['execId']} order={closed.get('orderId')} origin={'cryptoforge' if owned(closed) else 'external'} source={closed.get('journalSource', 'spot_execution')}" if closed else None),
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
        executions=sum(not identity.startswith("conversion:") for identity in seen),
        conversion_events=sum(identity.startswith("conversion:") for identity in seen), closed_segments=sum(r["status"] == "closed" for r in records),
        open_lots=sum(r["status"] == "open" for r in records), unmatched_sells=unmatched,
        incomplete_fees=sum(r["status"] == "closed" and r["realized_pnl"] is None for r in records),
    )


def trade_notice_events(fills: list[JsonObject], trades: list[JsonObject], pending: set[str], *, now: datetime) -> list[JsonObject]:
    groups: dict[tuple[str, str], list[JsonObject]] = defaultdict(list)
    for fill in fills:
        if str(fill["execId"]) in pending and fill.get("execType", "Trade") == "Trade" and str(fill.get("symbol")).endswith("USDT"):
            groups[(str(fill.get("orderId") or fill["execId"]), str(fill["side"]))].append(fill)
    events = []
    for (order_id, side), group in groups.items():
        ids = {str(f["execId"]) for f in group}
        segments = [r for r in trades if r["status"] == "closed" and r["idempotency_key"].rsplit(":", 1)[-1] in ids]
        if side == "Buy" and not any(owned(f) for f in group):
            continue
        if side == "Sell" and not segments and not any(owned(f) for f in group):
            continue
        qty = sum((decimal(f, "execQty") for f in group), ZERO)
        value = sum((decimal(f, "execQty") * decimal(f, "execPrice") for f in group), ZERO)
        payload = {"journal_notice": True, "mode": "live", "pair": bybit_symbol_to_pair(str(group[0]["symbol"])),
                   "amount": str(qty), "entry_price" if side == "Buy" else "exit_price": str(value / qty)}
        if side == "Sell":
            expected = sum((decimal(f, "execQty") + (decimal(f, "execFee") if f.get("feeCurrency") == str(f["symbol"])[:-4] else ZERO) for f in group), ZERO)
            matched = sum((Decimal(r["amount"]) for r in segments), ZERO)
            known = bool(segments) and abs(matched - expected) < Decimal("0.000000000001") and all(r["realized_pnl"] is not None for r in segments)
            cost = sum((Decimal(r["stake_amount"]) for r in segments), ZERO)
            pnl = sum((Decimal(r["realized_pnl"]) for r in segments), ZERO) if known else None
            fees = sum((Decimal(r["fee_amount"]) for r in segments), ZERO) if known else None
            payload.update(realized_pnl=str(pnl) if pnl is not None else None,
                           realized_pnl_pct=str(pnl / cost) if pnl is not None and cost > 0 else None,
                           fee_amount=str(fees) if fees is not None else None)
        digest = hashlib.sha256(",".join(sorted(ids)).encode()).hexdigest()[:24]
        events.append({"occurred_at": now.isoformat(), "source": "cryptoforge.live_trade_journal", "severity": "info",
                       "event_type": "trade.opened" if side == "Buy" else "trade.closed",
                       "idempotency_key": f"bybit:spot:notice:{order_id}:{digest}", "payload": payload})
    return events


def default_cache_path(bybit: BybitPrivateClient) -> Path:
    identity = hashlib.sha256(bybit.api_key.encode()).hexdigest()[:16]
    return Path(os.environ.get("CRYPTOFORGE_DATA_DIR", "data")) / f"live-journal-{identity}.sqlite"


def read_existing_journal_rows(client, fills):
    from urllib import parse,request
    buyers=[str(fill["execId"]) for fill in fills if fill.get("side")=="Buy" and owned(fill)]
    found={}
    for start in range(0,len(buyers),20):
        prefixes=buyers[start:start+20]
        if not prefixes:continue
        condition="("+",".join("idempotency_key.like.bybit:spot:fifo:"+identity+":*" for identity in prefixes)+")"
        for offset in range(0,10000,500):
            query=parse.urlencode({"mode":"eq.live","or":condition,"select":"*","limit":"500","offset":str(offset)})
            req=request.Request(client.supabase_url.rstrip("/")+"/rest/v1/trades?"+query,
                                headers={"apikey":client.service_role_key,"authorization":"Bearer "+client.service_role_key})
            with request.urlopen(req,timeout=client.timeout_seconds) as response:rows=json.loads(response.read())
            found.update((row["idempotency_key"],row) for row in rows)
            if len(rows)<500:break
        else:raise ValueError("existing journal namespace read exceeded limit")
    return found


def sync_live_journal(*, bybit: BybitPrivateClient, supabase: SupabaseRestClient,
                      cache_path: Path | None = None, now: datetime | None = None,
                      since: datetime | None = None) -> JournalResult:
    now = now or datetime.now(UTC)
    end_ms = int(now.timestamp() * 1000)
    path = cache_path or default_cache_path(bybit)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():path.chmod(0o600)
    with sqlite3.connect(path, timeout=30) as db:
        path.chmod(0o600)
        db.execute("create table if not exists executions (exec_id text primary key, payload text not null)")
        db.execute("create table if not exists journal_state (id integer primary key check (id=1), start_ms integer not null, cursor_ms integer not null)")
        db.execute("create table if not exists notification_executions (exec_id text primary key)")
        db.execute("create table if not exists notification_state (id integer primary key check(id=1))")
        db.execute("create table if not exists conversion_records (quote_id text primary key, payload text not null)")
        db.execute("create table if not exists account_transactions (id text primary key, payload text not null)")
        db.execute("create table if not exists accounting_version (id integer primary key, version integer not null)")
        db.execute("create table if not exists published_trade_rows (idempotency_key text primary key, payload text not null)")
        db.execute("create table if not exists superseded_trade_rows (idempotency_key text primary key, previous_payload text not null)")
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
        if hasattr(bybit, "get_small_conversion_history") and hasattr(bybit, "get_unified_transactions"):
            conversion_version = db.execute("select version from accounting_version where id=1").fetchone()
            flow_start = (max(state[0], state[1]-DAY_MS) if state and conversion_version else
                          state[0] if state else initial_ms)
            conversions = bybit.get_small_conversion_history(start_ms=flow_start, end_ms=end_ms)
            for conversion in conversions:
                db.execute("insert into conversion_records values (?,?) on conflict(quote_id) do update set payload=excluded.payload",
                           (str(conversion["exchangeTxId"]), json.dumps(conversion, sort_keys=True)))
            cursor = flow_start
            while cursor <= end_ms:
                until = min(cursor+7*DAY_MS-1,end_ms)
                for transaction in bybit.get_unified_transactions(start_ms=cursor,end_ms=until):
                    db.execute("insert into account_transactions values (?,?) on conflict(id) do update set payload=excluded.payload",
                               (str(transaction["id"]), json.dumps(transaction, sort_keys=True)))
                cursor = until+1
            from cryptoforge.conversion_journal import conversion_fills
            transactions=[json.loads(row[0]) for row in db.execute("select payload from account_transactions")]
            conversion_events = conversion_fills(
                [json.loads(row[0]) for row in db.execute("select payload from conversion_records")], transactions)
            raw_fills=[json.loads(row[0]) for row in db.execute("select payload from executions")]
            tracked_coins={str(fill["symbol"])[:-4] for fill in raw_fills if owned(fill)}
            covered_debits={event["sourceDebitId"] for event in conversion_events}
            unknown_movements=[t for t in transactions if t.get("currency") in tracked_coins
                and t.get("type")!="TRADE" and decimal(t,"change")!=0 and t.get("id") not in covered_debits]
            if unknown_movements:
                raise ValueError("unmodeled non-trade balance movements invalidate FIFO cost basis")
            for event in conversion_events:
                db.execute("insert into executions values (?,?) on conflict(exec_id) do update set payload=excluded.payload",
                           (event["execId"],json.dumps(event,sort_keys=True)))
            db.execute("insert into accounting_version values (1,2) on conflict(id) do update set version=2")
        fills = [json.loads(row[0]) for row in db.execute("select payload from executions")]

        trades, result = reconstruct_trades(fills)
        inventory_verified = False
        if hasattr(bybit,"get_unified_wallet_coins") and hasattr(bybit,"get_unified_transactions"):
            from cryptoforge.inventory_audit import verify_inventory
            audit=verify_inventory(fills,
                [json.loads(row[0]) for row in db.execute("select payload from account_transactions")],
                bybit.get_unified_wallet_coins())
            inventory_verified=audit["consistent"]
            if not inventory_verified:
                raise ValueError("wallet inventory or opening balance does not reconcile with the journal")
        # Corrections can move a sale to a different lot after a conversion.
        # Cancel stale derived segments, retain their previous payload locally.
        previous = {row[0]:json.loads(row[1]) for row in db.execute("select idempotency_key,payload from published_trade_rows")}
        if not previous and result.conversion_events and hasattr(supabase,"supabase_url"):
            previous = read_existing_journal_rows(supabase, fills)
        current_keys = {row["idempotency_key"] for row in trades}
        superseded=[]
        for key,row in previous.items():
            if key in current_keys:continue
            db.execute("insert into superseded_trade_rows values (?,?) on conflict(idempotency_key) do nothing",
                       (key,json.dumps(row,sort_keys=True)))
            keys=set(trades[0]) if trades else set(row)
            patch={name:row.get(name) for name in keys}
            patch.update(status="cancelled",amount="0",stake_amount="0",realized_pnl=None,
                         realized_pnl_pct=None,fee_amount=None,closed_at=None,
                         exit_reason="superseded FIFO segment after verified balance conversion")
            superseded.append(patch)
        # Uniform columns permit one REST transaction for all corrections and lots.
        supabase.upsert("trades", trades+superseded, on_conflict="idempotency_key")
        db.execute("delete from published_trade_rows")
        db.executemany("insert into published_trade_rows values (?,?)",
                       [(row["idempotency_key"],json.dumps(row,sort_keys=True)) for row in trades])
        seeded = db.execute("select id from notification_state where id=1").fetchone()
        notified = {row[0] for row in db.execute("select exec_id from notification_executions")}
        pending = {str(f["execId"]) for f in fills} - notified
        # The first run enables notices from now onward, without replaying historical trades.
        events = trade_notice_events(fills, trades, pending, now=now) if seeded else []
        supabase.upsert("system_events", events, on_conflict="idempotency_key", resolution="ignore-duplicates")
        db.executemany("insert or ignore into notification_executions values (?)", [(identity,) for identity in pending])
        db.execute("insert or ignore into notification_state values (1)")
        health = {
            "component": "live_trade_journal", "status": "warning" if result.unmatched_sells or result.incomplete_fees else "ok",
            "observed_at": now.isoformat(), "message": "Bybit Spot FIFO journal reconciled",
            "payload": {**result.__dict__, "accounting_version": (db.execute("select version from accounting_version where id=1").fetchone() or (1,))[0], "inventory_verified": inventory_verified, "history_start": datetime.fromtimestamp((state[0] if state else initial_ms) / 1000, UTC).isoformat()},
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
