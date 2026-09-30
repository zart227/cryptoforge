from datetime import datetime
from types import SimpleNamespace

from cryptoforge.order_observer import BybitOrderObserver, classify_origin, instance_order_id


class FakeSupabase:
    def __init__(self) -> None:
        self.calls = []

    def upsert(self, table, records, *, on_conflict, resolution="merge-duplicates") -> None:
        self.calls.append((table, records, on_conflict, resolution))


def test_observer_publishes_filled_buys_once_by_order_id() -> None:
    bybit = SimpleNamespace(
        get_order_history=lambda **kwargs: [
            {
                "orderId": "buy-1",
                "orderLinkId": "cf-other123-abcdef",
                "symbol": "CELOUSDT",
                "side": "Buy",
                "orderStatus": "Filled",
                "createdTime": "1790724861644",
                "avgPrice": "0.1",
                "cumExecQty": "55",
                "cumExecValue": "5.5",
            },
            {"orderId": "sell-1", "side": "Sell", "orderStatus": "Filled"},
        ]
    )
    supabase = FakeSupabase()

    observed = BybitOrderObserver(
        bybit=bybit, supabase=supabase, instance_id="local123"  # type: ignore[arg-type]
    ).observe_filled_buys()

    assert len(observed) == 1
    assert observed[0].origin == "other_or_legacy_cryptoforge"
    table, records, conflict, resolution = supabase.calls[0]
    assert table == "system_events"
    assert conflict == "idempotency_key"
    assert resolution == "ignore-duplicates"
    assert records[0]["idempotency_key"] == "bybit:spot:buy:buy-1"
    assert records[0]["severity"] == "warning"


def test_order_origin_and_link_id_are_instance_aware() -> None:
    assert classify_origin("cf-abcd1234-deadbeef", "abcd1234") == "this_instance"
    assert classify_origin("cf-legacy", "abcd1234") == "other_or_legacy_cryptoforge"
    assert classify_origin("manual-order", "abcd1234") == "external"
    link_id = instance_order_id("ETH/USDT", datetime(2026, 1, 1), instance_id="abcd1234")
    assert link_id.startswith("cf-abcd1234-")
    assert len(link_id) <= 36
