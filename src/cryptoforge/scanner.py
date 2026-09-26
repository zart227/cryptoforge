from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import mean

from cryptoforge.market_data import (
    BybitPublicClient,
    Candle,
    Instrument,
    PRIMARY_TIMEFRAME,
    Ticker24h,
)


STABLE_BASE_COINS = {
    "USDC",
    "USDE",
    "DAI",
    "FDUSD",
    "TUSD",
    "USDD",
    "PYUSD",
    "EUR",
    "EURC",
}
LEVERAGED_SUFFIXES = ("3L", "3S", "5L", "5S", "UP", "DOWN", "BULL", "BEAR")


@dataclass(frozen=True)
class ScannerConfig:
    min_turnover_24h_usdt: Decimal = Decimal("500000")
    max_spread_pct: Decimal = Decimal("0.003")
    min_candle_count: int = 60
    max_intraday_range_pct: Decimal = Decimal("0.35")
    max_volume_anomaly_ratio: Decimal = Decimal("6")
    min_oscillation_score: Decimal = Decimal("1.2")
    cheap_shortlist_size: int = 30
    expensive_shortlist_size: int = 12
    output_limit: int = 8
    candle_limit: int = 120
    timeframe: str = PRIMARY_TIMEFRAME


@dataclass(frozen=True)
class RejectedCandidate:
    symbol: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CheapCandidate:
    instrument: Instrument
    ticker: Ticker24h
    spread_pct: Decimal | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScoredCandidate:
    symbol: str
    score: Decimal
    turnover_24h: Decimal
    spread_pct: Decimal | None
    atr_pct: Decimal
    realized_volatility_pct: Decimal
    intraday_range_pct: Decimal
    momentum_pct: Decimal
    oscillation_score: Decimal
    volume_anomaly_ratio: Decimal
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScannerResult:
    selected: tuple[ScoredCandidate, ...]
    rejected: tuple[RejectedCandidate, ...]
    cheap_candidates: tuple[CheapCandidate, ...]


class MarketScanner:
    def __init__(
        self,
        client: BybitPublicClient,
        config: ScannerConfig | None = None,
    ) -> None:
        self.client = client
        self.config = config or ScannerConfig()

    def scan(self) -> ScannerResult:
        instruments = self.client.get_usdt_spot_instruments()
        tickers = {ticker.symbol: ticker for ticker in self.client.get_tickers()}
        cheap_candidates, rejected = cheap_filter(instruments, tickers, self.config)

        scored: list[ScoredCandidate] = []
        for candidate in cheap_candidates[: self.config.expensive_shortlist_size]:
            candles = self.client.get_klines(
                candidate.instrument.symbol,
                interval=self.config.timeframe,
                limit=self.config.candle_limit,
            )
            scored_candidate = score_candidate(candidate, candles, self.config)
            if scored_candidate is None:
                rejected.append(
                    RejectedCandidate(
                        candidate.instrument.symbol,
                        ("insufficient candle history",),
                    )
                )
                continue
            if scored_candidate.intraday_range_pct > self.config.max_intraday_range_pct:
                rejected.append(
                    RejectedCandidate(
                        scored_candidate.symbol,
                        ("intraday range too extreme",),
                    )
                )
                continue
            if scored_candidate.volume_anomaly_ratio > self.config.max_volume_anomaly_ratio:
                rejected.append(
                    RejectedCandidate(
                        scored_candidate.symbol,
                        ("volume anomaly too extreme",),
                    )
                )
                continue
            if scored_candidate.oscillation_score < self.config.min_oscillation_score:
                rejected.append(
                    RejectedCandidate(
                        scored_candidate.symbol,
                        ("insufficient intraday back-and-forth movement",),
                    )
                )
                continue
            scored.append(scored_candidate)

        selected = tuple(
            sorted(scored, key=lambda item: item.score, reverse=True)[
                : self.config.output_limit
            ]
        )
        return ScannerResult(
            selected=selected,
            rejected=tuple(rejected),
            cheap_candidates=tuple(cheap_candidates),
        )


def cheap_filter(
    instruments: list[Instrument],
    tickers: dict[str, Ticker24h],
    config: ScannerConfig,
) -> tuple[list[CheapCandidate], list[RejectedCandidate]]:
    candidates: list[CheapCandidate] = []
    rejected: list[RejectedCandidate] = []

    for instrument in instruments:
        reasons = cheap_rejection_reasons(instrument, tickers.get(instrument.symbol), config)
        if reasons:
            rejected.append(RejectedCandidate(instrument.symbol, tuple(reasons)))
            continue

        ticker = tickers[instrument.symbol]
        candidates.append(
            CheapCandidate(
                instrument=instrument,
                ticker=ticker,
                spread_pct=spread_pct(ticker),
                reasons=("liquid USDT spot pair",),
            )
        )

    candidates.sort(
        key=lambda item: item.ticker.turnover_24h or Decimal("0"),
        reverse=True,
    )
    return candidates[: config.cheap_shortlist_size], rejected


def cheap_rejection_reasons(
    instrument: Instrument,
    ticker: Ticker24h | None,
    config: ScannerConfig,
) -> list[str]:
    reasons: list[str] = []
    if not instrument.is_trading_usdt_spot:
        reasons.append("not active Bybit Spot USDT")
    if instrument.base_coin in STABLE_BASE_COINS:
        reasons.append("stablecoin-like base asset")
    if any(instrument.base_coin.endswith(suffix) for suffix in LEVERAGED_SUFFIXES):
        reasons.append("leveraged/special token")
    if instrument.min_order_qty is None or instrument.min_order_qty <= 0:
        reasons.append("missing or invalid minimum order quantity")
    if ticker is None:
        reasons.append("missing ticker")
        return reasons
    if ticker.turnover_24h is None or ticker.turnover_24h < config.min_turnover_24h_usdt:
        reasons.append("24h turnover below threshold")

    spread = spread_pct(ticker)
    if spread is not None and spread > config.max_spread_pct:
        reasons.append("spread above threshold")
    return reasons


def score_candidate(
    candidate: CheapCandidate,
    candles: list[Candle],
    config: ScannerConfig,
) -> ScoredCandidate | None:
    if len(candles) < config.min_candle_count:
        return None

    atr = average_true_range_pct(candles)
    realized_vol = realized_volatility_pct(candles)
    intraday_range = intraday_range_pct(candidate.ticker)
    momentum = momentum_pct(candles)
    oscillation = oscillation_score(candles)
    anomaly = volume_anomaly_ratio(candles)
    turnover = candidate.ticker.turnover_24h or Decimal("0")

    liquidity_score = min_decimal(turnover / config.min_turnover_24h_usdt, Decimal("6"))
    spread_penalty = Decimal("0")
    if candidate.spread_pct is not None:
        spread_penalty = min_decimal(
            candidate.spread_pct / config.max_spread_pct,
            Decimal("4"),
        )
    anomaly_penalty = max(Decimal("0"), anomaly - Decimal("2"))
    momentum_component = min_decimal(abs(momentum) * Decimal("20"), Decimal("3"))
    volatility_component = min_decimal(realized_vol * Decimal("40"), Decimal("3"))
    atr_component = min_decimal(atr * Decimal("50"), Decimal("3"))
    oscillation_component = min_decimal(oscillation, Decimal("3"))

    score = (
        liquidity_score
        + momentum_component
        + volatility_component
        + atr_component
        + oscillation_component
        - spread_penalty
        - anomaly_penalty
    )

    return ScoredCandidate(
        symbol=candidate.instrument.symbol,
        score=score,
        turnover_24h=turnover,
        spread_pct=candidate.spread_pct,
        atr_pct=atr,
        realized_volatility_pct=realized_vol,
        intraday_range_pct=intraday_range,
        momentum_pct=momentum,
        oscillation_score=oscillation,
        volume_anomaly_ratio=anomaly,
        reasons=(
            "passed liquidity/spread filters",
            "score balances liquidity, volatility, momentum and oscillation",
        ),
    )


def spread_pct(ticker: Ticker24h) -> Decimal | None:
    if ticker.bid1_price is None or ticker.ask1_price is None:
        return None
    if ticker.bid1_price <= 0 or ticker.ask1_price <= 0:
        return None
    midpoint = (ticker.bid1_price + ticker.ask1_price) / Decimal("2")
    if midpoint <= 0:
        return None
    return (ticker.ask1_price - ticker.bid1_price) / midpoint


def intraday_range_pct(ticker: Ticker24h) -> Decimal:
    if (
        ticker.high_price_24h is None
        or ticker.low_price_24h is None
        or ticker.last_price <= 0
    ):
        return Decimal("0")
    return (ticker.high_price_24h - ticker.low_price_24h) / ticker.last_price


def average_true_range_pct(candles: list[Candle]) -> Decimal:
    ranges = [
        (candle.high - candle.low) / candle.close
        for candle in candles
        if candle.close > 0
    ]
    if not ranges:
        return Decimal("0")
    return mean_decimal(ranges)


def realized_volatility_pct(candles: list[Candle]) -> Decimal:
    returns: list[Decimal] = []
    for previous, current in zip(candles, candles[1:], strict=False):
        if previous.close > 0:
            returns.append((current.close - previous.close) / previous.close)
    if not returns:
        return Decimal("0")

    avg = mean_decimal(returns)
    variance = mean((float(value - avg) ** 2 for value in returns))
    return Decimal(str(variance ** 0.5))


def momentum_pct(candles: list[Candle]) -> Decimal:
    first = candles[0].close
    last = candles[-1].close
    if first <= 0:
        return Decimal("0")
    return (last - first) / first


def oscillation_score(candles: list[Candle]) -> Decimal:
    if len(candles) < 3:
        return Decimal("0")

    path = Decimal("0")
    for previous, current in zip(candles, candles[1:], strict=False):
        if previous.close > 0:
            path += abs((current.close - previous.close) / previous.close)

    displacement = abs(momentum_pct(candles))
    if displacement == 0:
        return path * Decimal("100")
    return path / displacement


def volume_anomaly_ratio(candles: list[Candle], lookback: int = 20) -> Decimal:
    if len(candles) < lookback + 1:
        return Decimal("1")
    recent = candles[-1].volume
    baseline = mean_decimal([candle.volume for candle in candles[-lookback - 1 : -1]])
    if baseline <= 0:
        return Decimal("1")
    return recent / baseline


def mean_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def min_decimal(left: Decimal, right: Decimal) -> Decimal:
    return left if left <= right else right
