from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from urllib import error, parse, request

from cryptoforge.notifications import (
    Notification,
    NotificationKind,
    TelegramNotificationSink,
    telegram_notifier_from_env,
)


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class RelayEvent:
    id: str
    occurred_at: str
    event_type: str
    severity: str
    payload: JsonObject


@dataclass(frozen=True)
class RelayState:
    last_occurred_at: str
    delivered_event_ids: tuple[str, ...] = ()
    telegram_update_offset: int | None = None
    active_alert_keys: tuple[str, ...] = ()

    @staticmethod
    def initial() -> "RelayState":
        return RelayState(last_occurred_at="1970-01-01T00:00:00+00:00")


@dataclass(frozen=True)
class RelayResult:
    scanned: int
    sent: int
    skipped: int
    failed: int
    last_occurred_at: str


class RelayClient(Protocol):
    def fetch_events(self, *, since_occurred_at: str, limit: int) -> list[RelayEvent]:
        """Fetch events newer than the local relay cursor."""


class SupabaseRelayClient:
    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        timeout_seconds: float = 10.0,
        include_hold_decisions: bool = False,
    ) -> None:
        if not supabase_url:
            raise ValueError("supabase_url is required")
        if not service_role_key:
            raise ValueError("service_role_key is required")
        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.timeout_seconds = timeout_seconds
        self.include_hold_decisions = include_hold_decisions

    def fetch_events(self, *, since_occurred_at: str, limit: int) -> list[RelayEvent]:
        events: list[RelayEvent] = []
        events.extend(self._fetch_system_events(since_occurred_at=since_occurred_at, limit=limit))
        remaining = max(limit - len(events), 0)
        if remaining:
            events.extend(self._fetch_trade_decisions(since_occurred_at=since_occurred_at, limit=remaining))
        remaining = max(limit - len(events), 0)
        if remaining:
            events.extend(self._fetch_bot_health(since_occurred_at=since_occurred_at, limit=remaining))
        return sorted(events, key=lambda event: (parse_iso(event.occurred_at), event.id))[:limit]

    def _fetch_system_events(self, *, since_occurred_at: str, limit: int) -> list[RelayEvent]:
        query = parse.urlencode(
            {
                "select": "id,occurred_at,event_type,severity,payload",
                "occurred_at": f"gte.{since_occurred_at}",
                "event_type": "in.(trade.opened,trade.closed,trade.buy_observed,performance.daily_summary,research.nightly_summary)",
                "order": "occurred_at.asc,id.asc",
                "limit": str(limit),
            }
        )
        req = request.Request(
            f"{self.supabase_url}/rest/v1/system_events?{query}",
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    raise RuntimeError(f"Supabase returned unexpected status {response.status}")
                rows = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase HTTP {exc.code}: {body[:300]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Supabase request failed: {exc}") from exc

        return [
            RelayEvent(
                id=str(row["id"]),
                occurred_at=str(row["occurred_at"]),
                event_type=str(row["event_type"]),
                severity=str(row["severity"]),
                payload=dict(row.get("payload") or {}),
            )
            for row in rows
        ]

    def _fetch_trade_decisions(self, *, since_occurred_at: str, limit: int) -> list[RelayEvent]:
        decisions = ["approve_entry", "approve_exit", "reject_entry", "reject_exit", "no_new_trades"]
        if self.include_hold_decisions:
            decisions.append("hold")
        query = parse.urlencode(
            {
                "select": "id,decided_at,mode,pair,timeframe,decision,risk_decision,stake_amount,reference_price,reasons",
                "decided_at": f"gte.{since_occurred_at}",
                "decision": f"in.({','.join(decisions)})",
                "order": "decided_at.asc,id.asc",
                "limit": str(limit),
            }
        )
        rows = self._get_rows(f"trade_decisions?{query}")
        return [
            RelayEvent(
                id=f"trade_decision:{row['id']}",
                occurred_at=str(row["decided_at"]),
                event_type="trade.decision",
                severity="info" if str(row.get("decision")).startswith("approve") else "warning",
                payload=dict(row),
            )
            for row in rows
        ]

    def _fetch_bot_health(self, *, since_occurred_at: str, limit: int) -> list[RelayEvent]:
        query = parse.urlencode(
            {
                "select": "id,observed_at,component,status,message,payload",
                "observed_at": f"gte.{since_occurred_at}",
                "status": "in.(warning,error,critical)",
                "order": "observed_at.asc,id.asc",
                "limit": str(limit),
            }
        )
        rows = self._get_rows(f"bot_health?{query}")
        return [
            RelayEvent(
                id=f"bot_health:{row['id']}",
                occurred_at=str(row["observed_at"]),
                event_type="system.health",
                severity=str(row["status"]),
                payload=dict(row),
            )
            for row in rows
        ]

    def _get_rows(self, path: str) -> list[JsonObject]:
        req = request.Request(
            f"{self.supabase_url}/rest/v1/{path}",
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    raise RuntimeError(f"Supabase returned unexpected status {response.status}")
                return list(json.loads(response.read().decode("utf-8")))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase HTTP {exc.code}: {body[:300]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Supabase request failed: {exc}") from exc


@dataclass(frozen=True)
class StatusSnapshot:
    generated_at: datetime
    last_decision_at: datetime | None
    last_decision: JsonObject | None
    market_sync: JsonObject | None
    latest_candle_ingested_at: datetime | None
    latest_candle_open_time: datetime | None

    def alert_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        if self.last_decision_at is None:
            keys.append("executor:no_decisions")
        elif self.generated_at - self.last_decision_at > timedelta(minutes=6):
            keys.append("executor:stale")

        if not self.market_sync:
            keys.append("feeder:no_health")
        elif self.market_sync.get("status") != "ok":
            keys.append(f"feeder:{self.market_sync.get('status')}")

        observed = parse_optional_iso(str(self.market_sync.get("observed_at"))) if self.market_sync else None
        if observed is None or self.generated_at - observed > timedelta(minutes=6):
            keys.append("feeder:stale")

        if self.latest_candle_ingested_at is None:
            keys.append("candles:none")
        elif self.generated_at - self.latest_candle_ingested_at > timedelta(minutes=8):
            keys.append("candles:stale")

        return tuple(keys)

    def render(self) -> str:
        lines = ["CryptoForge status", f"now_utc: {self.generated_at.isoformat(timespec='seconds')}"]
        if self.last_decision:
            lines.extend(
                [
                    f"executor: {self.last_decision.get('mode')} {self.last_decision.get('decision')}",
                    f"pair: {self.last_decision.get('pair')}",
                    f"decision_at: {self.last_decision.get('decided_at')}",
                    f"price: {self.last_decision.get('reference_price')}",
                    "reasons: " + ", ".join(str(item) for item in self.last_decision.get("reasons", [])),
                ]
            )
        else:
            lines.append("executor: no decisions")

        if self.market_sync:
            lines.extend(
                [
                    f"market_sync: {self.market_sync.get('status')} {self.market_sync.get('message')}",
                    f"market_sync_at: {self.market_sync.get('observed_at')}",
                ]
            )
        else:
            lines.append("market_sync: missing")

        lines.append(
            "latest_candle: "
            + (
                self.latest_candle_open_time.isoformat(timespec="seconds")
                if self.latest_candle_open_time
                else "missing"
            )
        )
        alerts = self.alert_keys()
        lines.append("alerts: " + (", ".join(alerts) if alerts else "none"))
        return "\n".join(lines)


def fetch_status(client: SupabaseRelayClient) -> StatusSnapshot:
    decisions = client._get_rows(
        "trade_decisions?"
        + parse.urlencode(
            {
                "select": "decided_at,mode,pair,decision,reasons,reference_price",
                "order": "decided_at.desc",
                "limit": "1",
            }
        )
    )
    health = client._get_rows(
        "bot_health?"
        + parse.urlencode(
            {
                "select": "observed_at,component,status,message,payload",
                "component": "eq.supabase_market_sync",
                "order": "observed_at.desc",
                "limit": "1",
            }
        )
    )
    candles = client._get_rows(
        "market_candles?"
        + parse.urlencode(
            {
                "select": "open_time,ingested_at,pair",
                "order": "ingested_at.desc",
                "limit": "1",
            }
        )
    )
    decision = decisions[0] if decisions else None
    candle = candles[0] if candles else None
    return StatusSnapshot(
        generated_at=datetime.now(UTC),
        last_decision_at=parse_optional_iso(str(decision.get("decided_at"))) if decision else None,
        last_decision=decision,
        market_sync=health[0] if health else None,
        latest_candle_ingested_at=parse_optional_iso(str(candle.get("ingested_at"))) if candle else None,
        latest_candle_open_time=parse_optional_iso(str(candle.get("open_time"))) if candle else None,
    )


def relay_once(
    *,
    client: RelayClient,
    notifier: Any,
    state_path: str | Path,
    limit: int = 100,
) -> RelayResult:
    state_file = Path(state_path)
    state = load_state(state_file)
    events = client.fetch_events(since_occurred_at=state.last_occurred_at, limit=limit)

    sent = 0
    skipped = 0
    failed = 0
    delivered_ids = set(state.delivered_event_ids)
    last_occurred_at = state.last_occurred_at

    for event in events:
        if event.id in delivered_ids:
            skipped += 1
            last_occurred_at = max_iso_timestamp(last_occurred_at, event.occurred_at)
            continue

        notification = notification_from_event(event)
        if notification is None:
            skipped += 1
            last_occurred_at = max_iso_timestamp(last_occurred_at, event.occurred_at)
            continue

        result = notifier.notify(notification)
        if result.sent:
            sent += 1
            delivered_ids.add(event.id)
            last_occurred_at = max_iso_timestamp(last_occurred_at, event.occurred_at)
        else:
            failed += 1
            break

    # Only IDs at the cursor timestamp are needed for the inclusive next fetch.
    # Sorting UUIDs and keeping 500 could evict the current event and replay it forever.
    cursor_ids = {event.id for event in events if event.id in delivered_ids and parse_iso(event.occurred_at) == parse_iso(last_occurred_at)}
    if parse_iso(last_occurred_at) == parse_iso(state.last_occurred_at):
        cursor_ids.update(state.delivered_event_ids)
    save_state(
        state_file,
        RelayState(
            last_occurred_at=last_occurred_at,
            delivered_event_ids=tuple(sorted(cursor_ids)),
            telegram_update_offset=state.telegram_update_offset,
            active_alert_keys=state.active_alert_keys,
        ),
    )
    return RelayResult(
        scanned=len(events),
        sent=sent,
        skipped=skipped,
        failed=failed,
        last_occurred_at=last_occurred_at,
    )


def notification_from_event(event: RelayEvent) -> Notification | None:
    payload = event.payload
    if event.event_type == "trade.opened":
        return Notification(
            kind=NotificationKind.TRADE_OPENED,
            title="CryptoForge: trade opened",
            body=str(payload.get("pair", "unknown pair")),
            fields=compact_fields(
                payload,
                "mode",
                "side",
                "entry_price",
                "amount",
                "stake_amount",
                "stop_loss",
                "take_profit",
                "regime",
            ),
        )

    if event.event_type == "trade.closed":
        return Notification(
            kind=NotificationKind.TRADE_CLOSED,
            title="CryptoForge: trade closed",
            body=str(payload.get("pair", "unknown pair")),
            fields=compact_fields(
                payload,
                "mode",
                "exit_reason",
                "entry_price",
                "exit_price",
                "realized_pnl",
                "realized_pnl_pct",
                "fee_amount",
            ),
        )

    if event.event_type == "performance.daily_summary":
        return Notification(
            kind=NotificationKind.DAILY_SUMMARY,
            title="CryptoForge: daily summary",
            body=str(payload.get("date", event.occurred_at[:10])),
            fields=compact_fields(
                payload,
                "mode",
                "trade_count",
                "net_pnl",
                "gross_profit",
                "gross_loss",
                "fees",
                "win_rate",
                "profit_factor",
                "open_positions",
            ),
        )

    if event.event_type == "research.nightly_summary":
        return Notification(
            kind=NotificationKind.STARTED,
            title="CryptoForge: night research",
            body=", ".join(str(pair) for pair in payload.get("top_pairs", [])[:5]) or "no candidates",
            fields=compact_fields(
                payload,
                "timeframe",
                "lookback_candles",
                "top_pairs",
                "failures",
            ),
        )

    if event.event_type == "trade.decision":
        return Notification(
            kind=NotificationKind.STARTED,
            title="CryptoForge: trade decision",
            body=str(payload.get("pair", "unknown pair")),
            fields=compact_fields(
                payload,
                "mode",
                "decision",
                "risk_decision",
                "timeframe",
                "stake_amount",
                "reference_price",
                "reasons",
            ),
        )

    if event.event_type == "system.health":
        return Notification(
            kind=NotificationKind.CRITICAL_ERROR,
            title="CryptoForge: health alert",
            body=str(payload.get("component", "unknown component")),
            fields=compact_fields(
                payload,
                "status",
                "message",
                "payload",
            ),
        )

    return None


def compact_fields(payload: JsonObject, *keys: str) -> dict[str, object]:
    return {key: payload[key] for key in keys if payload.get(key) is not None}


def load_state(path: Path) -> RelayState:
    if not path.exists():
        return RelayState.initial()
    data = json.loads(path.read_text(encoding="utf-8"))
    return RelayState(
        last_occurred_at=str(data.get("last_occurred_at") or RelayState.initial().last_occurred_at),
        delivered_event_ids=tuple(str(event_id) for event_id in data.get("delivered_event_ids", [])),
        telegram_update_offset=(
            int(data["telegram_update_offset"])
            if data.get("telegram_update_offset") is not None
            else None
        ),
        active_alert_keys=tuple(str(key) for key in data.get("active_alert_keys", [])),
    )


def save_state(path: Path, state: RelayState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "last_occurred_at": state.last_occurred_at,
                "delivered_event_ids": list(state.delivered_event_ids),
                "telegram_update_offset": state.telegram_update_offset,
                "active_alert_keys": list(state.active_alert_keys),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def max_iso_timestamp(left: str, right: str) -> str:
    return right if parse_iso(right) >= parse_iso(left) else left


def parse_iso(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_optional_iso(value: str) -> datetime | None:
    if not value or value == "None":
        return None
    return parse_iso(value)


COMMAND_HELP = """CryptoForge — команды:
/status — состояние исполнителя и данных
/open — открытые ордера и Spot-балансы Bybit
/closed — последние закрытые сделки
/pnl — PnL и комиссии из журнала сделок
/summary — торговая сводка за сегодня (UTC)
/risk — последние решения и причины блокировок
/help — список команд"""


def report_rows(client: SupabaseRelayClient, table: str, **filters: str) -> list[JsonObject]:
    return client._get_rows(table + "?" + parse.urlencode({"select": "*", **filters}))


def render_command(client: SupabaseRelayClient, command: str) -> str:
    if command in {"/help", "/start"}:
        return COMMAND_HELP
    if command in {"/status", "/статус"}:
        return fetch_status(client).render()
    if command == "/open":
        from cryptoforge.bybit_private import BybitPrivateClient

        bybit = BybitPrivateClient.from_env()
        coins = bybit.get_unified_wallet_coins()
        # Spot realtime supports a request without a symbol, including unfilled buys.
        orders = bybit.get_open_orders(symbol="")
        lines = ["Bybit Spot: открытые ордера и балансы (весь аккаунт)"]
        lines += [f"{r.get('symbol')} {r.get('side')} qty={r.get('qty')} price={r.get('price')} status={r.get('orderStatus')}" for r in orders]
        if not orders:
            lines.append("Открытых ордеров нет.")
        lines.append("Балансы активов; это не журнал позиций CryptoForge:")
        lines += [f"{r.get('coin')}: {r.get('walletBalance')} (~{r.get('usdValue')} USD)" for r in coins if Decimal(str(r.get('walletBalance') or 0)) > 0]
        return "\n".join(lines)
    if command == "/closed":
        rows = report_rows(client, "trades", status="eq.closed", order="closed_at.desc", limit="10")
        if rows:
            return "Последние закрытые сделки:\n" + "\n".join(
                f"{r.get('closed_at')} {r.get('mode')} {r.get('pair')}: PnL={r.get('realized_pnl')} fee={r.get('fee_amount')}" for r in rows
            )
        from cryptoforge.bybit_private import BybitPrivateClient

        orders = BybitPrivateClient.from_env().get_order_history(limit=50)
        sells = [r for r in orders if r.get("side") == "Sell" and r.get("orderStatus") == "Filled"][:10]
        return "В журнале закрытых сделок нет. Последние исполненные продажи Bybit (весь аккаунт, без расчёта PnL):\n" + (
            "\n".join(f"{bybit_order_time(r)} {r.get('symbol')} qty={r.get('cumExecQty')} price={r.get('avgPrice')}" for r in sells)
            or "В последних 50 ордерах продаж нет."
        )
    if command in {"/pnl", "/summary"}:
        day = datetime.now(UTC).date().isoformat()
        filters = {"status": "eq.closed", "order": "closed_at.asc,id.asc", "limit": "500", "offset": "0"}
        if command == "/summary":
            filters["closed_at"] = f"gte.{day}T00:00:00+00:00"
        rows: list[JsonObject] = []
        while True:
            batch = report_rows(client, "trades", **filters)
            rows.extend(batch)
            if len(batch) < 500:
                break
            filters["offset"] = str(len(rows))
        title = f"Сводка за {day} (UTC)" if command == "/summary" else "PnL за всё время"
        if not rows:
            return title + "\nВ журнале нет закрытых сделок за этот период. PnL и комиссии недоступны; это не означает нулевую прибыль."
        lines = [title, "Источник: журнал CryptoForge. Live PnL после комиссий; комиссии отдельно, повторно не вычитаются. FIFO-записи могут быть частями сделки."]
        for mode in sorted({str(r.get("mode")) for r in rows}):
            group = [r for r in rows if str(r.get("mode")) == mode]
            pnl = sum((Decimal(str(r["realized_pnl"])) for r in group if r.get("realized_pnl") is not None), Decimal(0))
            fees = sum((Decimal(str(r["fee_amount"])) for r in group if r.get("fee_amount") is not None), Decimal(0))
            missing = sum(r.get("realized_pnl") is None or r.get("fee_amount") is None for r in group)
            lines.append(f"{mode}: сделок={len(group)}, PnL={pnl:.8f}, комиссии={fees:.8f}, неполных записей={missing}")
        return "\n".join(lines)
    if command == "/risk":
        rows = report_rows(client, "trade_decisions", mode="eq.live", order="decided_at.desc", limit="10")
        snapshot_path = Path(".local/state/live-risk-snapshot.json")
        limits = "Текущие лимиты исполнителя ещё не опубликованы.\n"
        if snapshot_path.exists():
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            limits = "Последний снимок лимитов исполнителя:\n" + "\n".join(f"{key}: {value}" for key, value in snapshot.items()) + "\n"
        return limits + "Последние live-решения и причины:\n" + (
            "\n".join(f"{r.get('decided_at')} {r.get('pair')} {r.get('decision')} risk={r.get('risk_decision')} stake={r.get('stake_amount')}: " + "; ".join(str(x) for x in (r.get('reasons') or [])) for r in rows)
            or "Live-решений пока нет."
        )
    return "Неизвестная команда. Доступные команды: /help"


def bybit_order_time(row: JsonObject) -> str:
    return datetime.fromtimestamp(int(row.get("updatedTime") or row.get("createdTime") or 0) / 1000, UTC).isoformat()


def send_command_reply(sink: TelegramNotificationSink, message: str) -> None:
    # Leave room below Telegram's 4096-character limit, including Unicode pairs.
    for start in range(0, len(message), 1800):
        sink.send(message[start:start + 1800])


def process_telegram_commands(
    *,
    client: SupabaseRelayClient,
    state_path: str | Path,
    bot_token: str,
    chat_id: str,
    proxy_url: str = "",
    timeout_seconds: float,
) -> int:
    if not bot_token or not chat_id:
        return 0
    state_file = Path(state_path)
    state = load_state(state_file)
    params = {"timeout": "0", "limit": "20"}
    if state.telegram_update_offset is not None:
        params["offset"] = str(state.telegram_update_offset)
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates?{parse.urlencode(params)}"
    try:
        payload = telegram_get_json(url, timeout_seconds=timeout_seconds, proxy_url=proxy_url)
    except (error.HTTPError, error.URLError, TimeoutError):
        return 0

    if not payload.get("ok"):
        return 0

    sink = TelegramNotificationSink(
        bot_token=bot_token,
        chat_id=chat_id,
        proxy_url=proxy_url,
        timeout_seconds=timeout_seconds,
    )
    handled = 0
    update_offset = state.telegram_update_offset
    for update in payload.get("result", []):
        update_id = int(update.get("update_id", 0))
        update_offset = max(update_offset or 0, update_id + 1)
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        if str(chat.get("id")) != str(chat_id):
            continue
        text = str(message.get("text") or "").strip()
        command = text.split()[0].split("@")[0].lower() if text else ""
        if not command.startswith("/"):
            continue
        try:
            reply = render_command(client, command)
        except Exception:  # A backend failure must not terminate polling or expose credentials.
            reply = f"Не удалось получить данные для {command}. Попробуйте позже."
        try:
            send_command_reply(sink, reply)
        except Exception:
            # Keep the failed update pending for the next poll.
            update_offset = update_id
            break
        handled += 1

    save_state(
        state_file,
        RelayState(
            last_occurred_at=state.last_occurred_at,
            delivered_event_ids=state.delivered_event_ids,
            telegram_update_offset=update_offset,
            active_alert_keys=state.active_alert_keys,
        ),
    )
    return handled


def telegram_get_json(url: str, *, timeout_seconds: float, proxy_url: str = "") -> JsonObject:
    req = request.Request(url, method="GET")
    if not proxy_url:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return dict(json.loads(response.read().decode("utf-8")))

    opener = request.build_opener(request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    try:
        with opener.open(req, timeout=timeout_seconds) as response:
            return dict(json.loads(response.read().decode("utf-8")))
    except (error.HTTPError, error.URLError, TimeoutError):
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return dict(json.loads(response.read().decode("utf-8")))


def watcher_once(
    *,
    client: SupabaseRelayClient,
    notifier: Any,
    state_path: str | Path,
) -> int:
    state_file = Path(state_path)
    state = load_state(state_file)
    status = fetch_status(client)
    alert_keys = status.alert_keys()
    previous = set(state.active_alert_keys)
    new_alerts = [key for key in alert_keys if key not in previous]
    sent = 0
    if new_alerts:
        result = notifier.notify(
            Notification(
                kind=NotificationKind.CRITICAL_ERROR,
                title="CryptoForge: watcher alert",
                body=", ".join(new_alerts),
                fields={"status": status.render()},
            )
        )
        sent = 1 if result.sent else 0
    save_state(
        state_file,
        RelayState(
            last_occurred_at=state.last_occurred_at,
            delivered_event_ids=state.delivered_event_ids,
            telegram_update_offset=state.telegram_update_offset,
            active_alert_keys=alert_keys,
        ),
    )
    return sent


def client_from_env(environ: dict[str, str] | None = None) -> SupabaseRelayClient:
    env = os.environ if environ is None else environ
    return SupabaseRelayClient(
        supabase_url=env.get("SUPABASE_URL", ""),
        service_role_key=env.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        timeout_seconds=float(env.get("CRYPTOFORGE_RELAY_TIMEOUT_SECONDS", "10")),
        include_hold_decisions=env.get("CRYPTOFORGE_TELEGRAM_INCLUDE_HOLD", "").lower()
        in {"1", "true", "yes"},
    )


def default_state_path(environ: dict[str, str] | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = env.get("CRYPTOFORGE_TELEGRAM_RELAY_STATE")
    if explicit:
        return Path(explicit)
    data_dir = Path(env.get("CRYPTOFORGE_DATA_DIR", "./data"))
    return data_dir / "telegram-relay-state.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relay CryptoForge Supabase events to Telegram.")
    parser.add_argument("--watch", action="store_true", help="run continuously")
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--state-path", default=str(default_state_path()))
    args = parser.parse_args(argv)

    client = client_from_env()
    notifier = telegram_notifier_from_env()
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    proxy_url = os.environ.get("TELEGRAM_PROXY_URL", "")
    timeout_seconds = float(os.environ.get("CRYPTOFORGE_RELAY_TIMEOUT_SECONDS", "10"))

    while True:
        commands = process_telegram_commands(
            client=client,
            state_path=args.state_path,
            bot_token=bot_token,
            chat_id=chat_id,
            proxy_url=proxy_url,
            timeout_seconds=timeout_seconds,
        )
        result = relay_once(client=client, notifier=notifier, state_path=args.state_path, limit=args.limit)
        alerts = watcher_once(client=client, notifier=notifier, state_path=args.state_path)
        print(
            "telegram relay: "
            f"scanned={result.scanned} sent={result.sent} skipped={result.skipped} "
            f"failed={result.failed} commands={commands} alerts={alerts} "
            f"cursor={result.last_occurred_at}",
            flush=True,
        )
        if not args.watch:
            return 1 if result.failed else 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
