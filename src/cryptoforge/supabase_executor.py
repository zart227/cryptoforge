from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_DOWN
import json
from typing import TYPE_CHECKING, Any
from urllib import parse, request

from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.order_observer import instance_order_id
from cryptoforge.supabase_market import SupabaseRestClient

if TYPE_CHECKING:
    from cryptoforge.model_registry import ActiveModelRegistry


@dataclass(frozen=True)
class CandleRow:
    pair: str
    symbol: str
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class ExecutorDecision:
    decision: str
    pair: str
    reasons: tuple[str, ...]
    order: dict[str, Any] | None = None


class SupabaseMarketReader:
    def __init__(self, client: SupabaseRestClient) -> None:
        self.client = client

    def read_candles(self, pair: str, *, timeframe: str = "5m", limit: int = 120) -> list[CandleRow]:
        query = parse.urlencode(
            {
                "pair": f"eq.{pair}",
                "timeframe": f"eq.{timeframe}",
                "select": "pair,symbol,open_time,open,high,low,close,volume",
                "order": "open_time.desc",
                "limit": str(limit),
            }
        )
        rows = self._get(f"market_candles?{query}")
        candles = [
            CandleRow(
                pair=str(row["pair"]),
                symbol=str(row["symbol"]),
                open_time=datetime.fromisoformat(str(row["open_time"]).replace("Z", "+00:00")),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
            )
            for row in rows
        ]
        return sorted(candles, key=lambda candle: candle.open_time)

    def _get(self, path: str) -> list[dict[str, Any]]:
        url = f"{self.client.supabase_url.rstrip('/')}/rest/v1/{path}"
        headers = {
            "apikey": self.client.service_role_key,
            "authorization": f"Bearer {self.client.service_role_key}",
        }
        req = request.Request(url, headers=headers, method="GET")
        with request.urlopen(req, timeout=self.client.timeout_seconds) as response:
            return json.loads(response.read())


class SupabaseLiveExecutor:
    def __init__(
        self,
        *,
        reader: SupabaseMarketReader,
        supabase: SupabaseRestClient,
        bybit: BybitPrivateClient,
        stake_amount: Decimal = Decimal("10"),
        min_candles: int = 60,
        max_candle_age: timedelta = timedelta(minutes=12),
        allow_intraday_reversion: bool = False,
        allow_emerging_momentum: bool = False,
        active_model_registry: ActiveModelRegistry | None = None,
        ml_mode: str = "off",
        ml_threshold: float = 0.55,
        ml_max_age: timedelta = timedelta(hours=36),
        entry_blockers: tuple[str, ...] = (),
        entry_slots: int | None = None,
        stop_loss_percent: Decimal = Decimal("0.04"),
        max_dust_fraction: Decimal = Decimal("0.01"),
    ) -> None:
        if ml_mode not in {"off", "shadow", "gate"}:
            raise ValueError("ml_mode must be one of: off, shadow, gate")
        if not Decimal("0") <= stop_loss_percent < Decimal("1"):
            raise ValueError("stop_loss_percent must be between zero and one")
        self.reader = reader
        self.supabase = supabase
        self.bybit = bybit
        self.stake_amount = stake_amount
        self.min_candles = min_candles
        self.max_candle_age = max_candle_age
        self.allow_intraday_reversion = allow_intraday_reversion
        self.allow_emerging_momentum = allow_emerging_momentum
        self.active_model_registry = active_model_registry
        self.ml_mode = ml_mode
        self.ml_threshold = ml_threshold
        self.ml_max_age = ml_max_age
        self.entry_blockers = entry_blockers
        self.entry_slots = entry_slots
        self.stop_loss_percent = stop_loss_percent
        self.max_dust_fraction = max_dust_fraction

    def run_once(self, pair: str, *, live: bool = False, now: datetime | None = None) -> ExecutorDecision:
        now = now or datetime.now(UTC)
        candles = self.reader.read_candles(pair, limit=120)
        reasons: list[str] = []
        if len(candles) < self.min_candles:
            reasons.append("not enough candles")
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        latest = candles[-1]
        if now - latest.open_time > self.max_candle_age:
            reasons.append("latest candle is stale")
            return self._record(pair, "reject_entry", reasons, candles, live=live)

        symbol = latest.symbol
        base_coin = pair.split("/", 1)[0]
        if self.bybit.get_open_orders(symbol=symbol):
            reasons.append("open order already exists")
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        base_balance = self.bybit.get_unified_coin_wallet_balance(base_coin)
        instrument = self.bybit.get_spot_instrument(symbol)
        sellable_quantity = quantize_down(base_balance, instrument.quantity_step)
        has_material_position = (
            sellable_quantity >= instrument.minimum_quantity
            and base_balance * latest.close >= Decimal("1")
        )
        if base_balance > 0 and not has_material_position:
            reasons.append(
                f"ignored_dust={base_balance}; sellable_value={sellable_quantity * latest.close}"
            )
        if has_material_position:
            should_exit, exit_reasons = exit_signal(candles)
            reasons.extend(exit_reasons)
            buy_orders = self.bybit.get_order_history(symbol=symbol, limit=20)
            latest_buy = next(
                (
                    row
                    for row in buy_orders
                    if row.get("side") == "Buy"
                    and row.get("orderStatus") == "Filled"
                    and Decimal(str(row.get("avgPrice") or "0")) > 0
                ),
                None,
            )
            if latest_buy is not None:
                entry_price = Decimal(str(latest_buy["avgPrice"]))
                stop_price = entry_price * (Decimal("1") - self.stop_loss_percent)
                stop_loss = latest.close <= stop_price
                reasons.extend(
                    [
                        f"entry_price={entry_price}",
                        f"stop_price={stop_price}",
                        f"stop_loss={stop_loss}",
                    ]
                )
                should_exit = should_exit or stop_loss
            if not should_exit:
                return self._record(pair, "hold", reasons, candles, live=live)
            qty = sellable_quantity
            if qty < instrument.minimum_quantity or qty * latest.close < instrument.minimum_order_amount:
                reasons.append(
                    "exit_blocked_by_exchange_minimum: "
                    f"sellable_quantity={qty}; value={qty * latest.close}; "
                    f"minimum_quantity={instrument.minimum_quantity}; "
                    f"minimum_notional={instrument.minimum_order_amount}; "
                    "position remains open; no automatic top-up"
                )
                return self._record(pair, "hold", reasons, candles, live=live)
            order_link_id = order_id(f"{pair}:exit", latest.open_time)
            if not live:
                reasons.append("shadow mode; exit order not submitted")
                return self._record(pair, "approve_exit", reasons, candles, live=live)
            order = self.bybit.create_spot_market_order(
                symbol=symbol,
                side="Sell",
                qty=qty,
                order_link_id=order_link_id,
            )
            return self._record(pair, "approve_exit", reasons, candles, live=live, order=order)

        signal, signal_reasons = entry_signal(
            candles,
            allow_intraday_reversion=self.allow_intraday_reversion,
            allow_emerging_momentum=self.allow_emerging_momentum,
        )
        reasons.extend(signal_reasons)
        short_shadow, short_reasons = short_shadow_signal(candles)
        reasons.extend(short_reasons)
        if short_shadow:
            reasons.extend(self._ml_shadow_research_reasons(candles))
        if not signal:
            return self._record(pair, "hold", reasons, candles, live=live)
        if self.entry_blockers:
            reasons.extend(self.entry_blockers)
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        if self.entry_slots is not None and self.entry_slots <= 0:
            reasons.append("no entry slots remaining in this cycle")
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        # Buying at the exchange minimum can leave an unsellable position
        # after fees or a stop loss. Keep the operator's stake cap unchanged.
        # Reserve 0.2% for acquisition fees and 1% adverse price movement on
        # each side; this is a bounded estimate, not a guarantee across gaps.
        estimated_quantity = quantize_down(
            self.stake_amount * Decimal("0.998") / (latest.close * Decimal("1.01")),
            instrument.quantity_step,
        )
        estimated_exit_value = (
            estimated_quantity * latest.close
            * (Decimal("1") - self.stop_loss_percent) * Decimal("0.99")
        )
        if (
            estimated_quantity < instrument.minimum_quantity
            or estimated_exit_value < instrument.minimum_order_amount
        ):
            reasons.append(
                "entry rejected: exit would be below exchange minimum at stop: "
                f"estimated_exit_value={estimated_exit_value}; "
                f"minimum_notional={instrument.minimum_order_amount}; "
                f"estimated_quantity={estimated_quantity}; "
                f"minimum_quantity={instrument.minimum_quantity}"
            )
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        maximum_residual_value = instrument.quantity_step * latest.close
        maximum_allowed_residual = self.stake_amount * self.max_dust_fraction
        if maximum_residual_value > maximum_allowed_residual:
            reasons.append(
                "dust risk too high: "
                f"step_value={maximum_residual_value} > allowed={maximum_allowed_residual}"
            )
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        ml_allows_entry, ml_reasons = self._ml_entry_allows(candles)
        reasons.extend(ml_reasons)
        if not ml_allows_entry:
            return self._record(pair, "reject_entry", reasons, candles, live=live)
        balance = self.bybit.get_unified_usdt_balance()
        if balance.usdt_wallet_balance < self.stake_amount:
            reasons.append("insufficient USDT balance")
            return self._record(pair, "reject_entry", reasons, candles, live=live)

        if self.stake_amount < instrument.minimum_order_amount:
            reasons.append("order below minimum notional")
            return self._record(pair, "reject_entry", reasons, candles, live=live)

        order_link_id = order_id(pair, latest.open_time)
        if not live:
            reasons.append("shadow mode; order not submitted")
            return self._record(pair, "approve_entry", reasons, candles, live=live)

        order = self.bybit.create_spot_market_order(
            symbol=symbol,
            side="Buy",
            qty=self.stake_amount,
            order_link_id=order_link_id,
        )
        if self.entry_slots is not None:
            self.entry_slots -= 1
        decision = self._record(pair, "approve_entry", reasons, candles, live=live, order=order)
        return decision

    def _ml_entry_allows(self, candles: list[CandleRow]) -> tuple[bool, list[str]]:
        # Local import avoids the model-training module's CandleRow dependency
        # forming a runtime import cycle.
        from cryptoforge.model_training import FEATURE_VERSION, extract_features

        if self.ml_mode == "off" or self.active_model_registry is None:
            return True, ["ml_mode=off"]
        try:
            model = self.active_model_registry.latest(max_age=self.ml_max_age)
        except Exception as exc:
            allowed = self.ml_mode != "gate"
            return allowed, [f"ml_fallback=registry_error:{type(exc).__name__}"]
        if model is None:
            return self.ml_mode != "gate", ["ml_fallback=no_fresh_model"]
        if model.feature_version != FEATURE_VERSION:
            return self.ml_mode != "gate", [f"ml_fallback=unsupported_feature_version:{model.feature_version}"]
        try:
            features = extract_features(candles, [candle.volume for candle in candles])
            probability = model.predict_probability(features)
            short_predictor = getattr(model, "predict_short_probability", None)
            short_probability = short_predictor(features) if short_predictor is not None else None
        except Exception as exc:
            return self.ml_mode != "gate", [f"ml_fallback=prediction_error:{type(exc).__name__}"]
        reasons = [
            f"ml_mode={self.ml_mode}",
            f"ml_model={model.model_version}",
            f"ml_probability={probability:.6f}",
            "ml_short_probability=unavailable"
            if short_probability is None
            else f"ml_short_probability={short_probability:.6f}",
            f"ml_threshold={self.ml_threshold:.6f}",
        ]
        if self.ml_mode == "gate" and probability < self.ml_threshold:
            reasons.append("ml_gate=reject")
            return False, reasons
        reasons.append("ml_gate=pass" if self.ml_mode == "gate" else "ml_shadow=observed")
        return True, reasons

    def _ml_shadow_research_reasons(self, candles: list[CandleRow]) -> list[str]:
        from cryptoforge.model_training import FEATURE_VERSION, extract_features

        if self.active_model_registry is None:
            return ["short_ml_shadow=unavailable:no_registry"]
        try:
            model = self.active_model_registry.latest(max_age=self.ml_max_age)
        except Exception as exc:
            return [f"short_ml_shadow=registry_error:{type(exc).__name__}"]
        if model is None:
            return ["short_ml_shadow=unavailable:no_fresh_model"]
        if model.feature_version != FEATURE_VERSION:
            return [f"short_ml_shadow=unsupported_feature_version:{model.feature_version}"]
        try:
            features = extract_features(candles, [candle.volume for candle in candles])
            probability = model.predict_short_probability(features)
        except Exception as exc:
            return [f"short_ml_shadow=prediction_error:{type(exc).__name__}"]
        if probability is None:
            return ["short_ml_shadow=unavailable:legacy_model"]
        return [f"short_ml_shadow=observed", f"ml_short_probability={probability:.6f}"]

    def _record(
        self,
        pair: str,
        decision: str,
        reasons: list[str],
        candles: list[CandleRow],
        *,
        live: bool,
        order: dict[str, Any] | None = None,
    ) -> ExecutorDecision:
        latest = candles[-1] if candles else None
        record = {
            "decided_at": datetime.now(UTC).isoformat(),
            "mode": "live" if live else "shadow",
            "pair": pair,
            "timeframe": "5m",
            "strategy_name": "SupabaseLiveExecutor",
            "strategy_version": "v0.1.0",
            "decision": decision,
            "stake_amount": format(self.stake_amount, "f"),
            "reference_price": format(latest.close, "f") if latest else None,
            "features": {"order": order or {}, "latest_open_time": latest.open_time.isoformat() if latest else None},
            "reasons": reasons,
            "idempotency_key": order_id(pair, latest.open_time if latest else datetime.now(UTC)),
        }
        self.supabase.upsert("trade_decisions", [record], on_conflict="idempotency_key")
        return ExecutorDecision(decision, pair, tuple(reasons), order)


def entry_signal(
    candles: list[CandleRow],
    *,
    allow_intraday_reversion: bool = False,
    allow_emerging_momentum: bool = False,
) -> tuple[bool, list[str]]:
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    ema_fast = ema(closes, 12)
    ema_slow = ema(closes, 36)
    rsi_value = rsi(closes, 14)
    volume_mean = sum(volumes[-20:]) / Decimal("20")
    volume_ratio = volumes[-1] / volume_mean if volume_mean > 0 else Decimal("0")
    short_volume_mean = sum(volumes[-7:-1]) / Decimal("6")
    short_volume_ratio = volumes[-1] / short_volume_mean if short_volume_mean > 0 else Decimal("0")
    resistance = max(c.high for c in candles[-31:-1])
    support = min(c.low for c in candles[-31:-1])
    last = candles[-1]
    previous = candles[-2]
    trend = ema_fast > ema_slow and rsi_value >= Decimal("50")
    breakout = last.close > resistance and previous.close <= resistance and volume_ratio >= Decimal("1.15")
    bounce = last.close > last.open and last.close > previous.close and last.low <= support * Decimal("1.003")
    pullback = trend and previous.close <= ema_fast and last.close > ema_fast and rsi_value <= Decimal("72")
    recent_momentum = (last.close - candles[-13].close) / candles[-13].close if candles[-13].close > 0 else Decimal("0")
    prior_momentum = (candles[-13].close - candles[-25].close) / candles[-25].close if candles[-25].close > 0 else Decimal("0")
    emerging_momentum = (
        allow_emerging_momentum
        and recent_momentum >= Decimal("0.008")
        and recent_momentum > prior_momentum
        and volume_ratio >= Decimal("0.55")
        and short_volume_ratio >= Decimal("0.80")
        and Decimal("40") <= rsi_value <= Decimal("99")
        and last.close >= ema_fast
    )
    intraday_reversion = (
        allow_intraday_reversion
        and bounce
        and Decimal("30") <= rsi_value <= Decimal("55")
        and volume_ratio >= Decimal("0.35")
        and last.close < resistance * Decimal("0.999")
    )
    reasons = [
        f"rsi={rsi_value:.2f}",
        f"volume_ratio={volume_ratio:.3f}",
        f"trend={trend}",
        f"breakout={breakout}",
        f"bounce={bounce}",
        f"pullback={pullback}",
        f"recent_momentum={recent_momentum:.4f}",
        f"short_volume_ratio={short_volume_ratio:.3f}",
        f"emerging_momentum={emerging_momentum}",
        f"intraday_reversion={intraday_reversion}",
    ]
    trend_entry = trend and (breakout or bounce or pullback) and volume_ratio >= Decimal("0.65")
    return bool(trend_entry or intraday_reversion or emerging_momentum), reasons


def exit_signal(candles: list[CandleRow]) -> tuple[bool, list[str]]:
    closes = [c.close for c in candles]
    ema_fast = ema(closes, 12)
    ema_slow = ema(closes, 36)
    rsi_value = rsi(closes, 14)
    support = min(c.low for c in candles[-31:-1])
    last = candles[-1]
    previous = candles[-2]
    trend_down = ema_fast < ema_slow
    overbought = rsi_value >= Decimal("72")
    support_breakdown = last.close < support and previous.close >= support
    reasons = [
        f"exit_rsi={rsi_value:.2f}",
        f"exit_trend_down={trend_down}",
        f"exit_overbought={overbought}",
        f"exit_support_breakdown={support_breakdown}",
    ]
    return bool(trend_down or overbought or support_breakdown), reasons


def short_shadow_signal(candles: list[CandleRow]) -> tuple[bool, list[str]]:
    closes = [c.close for c in candles]
    volumes = [c.volume for c in candles]
    ema_fast = ema(closes, 12)
    ema_slow = ema(closes, 36)
    rsi_value = rsi(closes, 14)
    volume_mean = sum(volumes[-20:]) / Decimal("20")
    volume_ratio = volumes[-1] / volume_mean if volume_mean > 0 else Decimal("0")
    resistance = max(c.high for c in candles[-31:-1])
    support = min(c.low for c in candles[-31:-1])
    last = candles[-1]
    previous = candles[-2]
    resistance_reject = (
        last.high >= resistance * Decimal("0.997")
        and last.close < last.open
        and last.close < previous.close
    )
    support_breakdown = (
        last.close < support
        and previous.close >= support
        and volume_ratio >= Decimal("0.85")
    )
    trend_down = ema_fast < ema_slow and rsi_value <= Decimal("52")
    short_shadow = trend_down and (resistance_reject or support_breakdown)
    reasons = [
        f"short_shadow_signal={short_shadow}",
        f"short_trend_down={trend_down}",
        f"short_resistance_reject={resistance_reject}",
        f"short_support_breakdown={support_breakdown}",
    ]
    return bool(short_shadow), reasons


def ema(values: list[Decimal], period: int) -> Decimal:
    alpha = Decimal("2") / Decimal(period + 1)
    current = values[0]
    for value in values[1:]:
        current = value * alpha + current * (Decimal("1") - alpha)
    return current


def rsi(values: list[Decimal], period: int) -> Decimal:
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for left, right in zip(values[-period - 1 : -1], values[-period:]):
        delta = right - left
        gains.append(max(delta, Decimal("0")))
        losses.append(max(-delta, Decimal("0")))
    avg_gain = sum(gains) / Decimal(period)
    avg_loss = sum(losses) / Decimal(period)
    if avg_loss == 0:
        return Decimal("100")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def quantity_step(symbol: str) -> Decimal:
    if symbol in {"BTCUSDT", "ETHUSDT"}:
        return Decimal("0.00001")
    if symbol == "ENAUSDT":
        return Decimal("1")
    if symbol == "HYPEUSDT":
        return Decimal("0.001")
    return Decimal("0.01")


def order_id(pair: str, open_time: datetime) -> str:
    return instance_order_id(pair, open_time)
