from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import os
import socket
from typing import Any

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.supabase_market import SupabaseRestClient


@dataclass(frozen=True)
class ObservedOrder:
    order_id: str
    symbol: str
    side: str
    status: str
    order_link_id: str
    origin: str
    occurred_at: str


def executor_instance_id() -> str:
    configured = os.environ.get("CRYPTOFORGE_EXECUTOR_ID", "").strip()
    identity = configured or socket.gethostname()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]


def instance_order_id(pair: str, open_time: datetime, *, instance_id: str | None = None) -> str:
    owner = instance_id or executor_instance_id()
    digest = hashlib.sha256(f"{pair}:{open_time.isoformat()}".encode("utf-8")).hexdigest()[:20]
    return f"cf-{owner}-{digest}"


class BybitOrderObserver:
    def __init__(
        self,
        *,
        bybit: BybitPrivateClient,
        supabase: SupabaseRestClient,
        instance_id: str | None = None,
    ) -> None:
        self.bybit = bybit
        self.supabase = supabase
        self.instance_id = instance_id or executor_instance_id()

    def observe_filled_buys(self, *, limit: int = 50) -> list[ObservedOrder]:
        observed: list[ObservedOrder] = []
        records: list[dict[str, Any]] = []
        for row in self.bybit.get_order_history(limit=limit):
            if str(row.get("side")) != "Buy" or str(row.get("orderStatus")) != "Filled":
                continue
            order_id = str(row.get("orderId") or "").strip()
            if not order_id:
                continue
            order_link_id = str(row.get("orderLinkId") or "")
            origin = classify_origin(order_link_id, self.instance_id)
            occurred_at = bybit_timestamp(row.get("createdTime"))
            item = ObservedOrder(
                order_id=order_id,
                symbol=str(row.get("symbol") or ""),
                side="Buy",
                status="Filled",
                order_link_id=order_link_id,
                origin=origin,
                occurred_at=occurred_at,
            )
            observed.append(item)
            records.append(
                {
                    "occurred_at": occurred_at,
                    "source": "cryptoforge.order_observer",
                    "severity": "info" if origin == "this_instance" else "warning",
                    "event_type": "trade.buy_observed",
                    "idempotency_key": f"bybit:spot:buy:{order_id}",
                    "payload": {
                        "exchange": "bybit",
                        "market_type": "spot",
                        "executor_instance_id": self.instance_id,
                        "origin": origin,
                        "order_id": order_id,
                        "order_link_id": order_link_id,
                        "symbol": item.symbol,
                        "side": item.side,
                        "status": item.status,
                        "price": str(row.get("avgPrice") or row.get("price") or ""),
                        "quantity": str(row.get("cumExecQty") or row.get("qty") or ""),
                        "value": str(row.get("cumExecValue") or ""),
                    },
                }
            )
        self.supabase.upsert(
            "system_events",
            records,
            on_conflict="idempotency_key",
            resolution="ignore-duplicates",
        )
        return observed


def classify_origin(order_link_id: str, instance_id: str) -> str:
    if order_link_id.startswith(f"cf-{instance_id}-"):
        return "this_instance"
    if order_link_id.startswith("cf-"):
        return "other_or_legacy_cryptoforge"
    return "external"


def bybit_timestamp(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.now(UTC).isoformat()
