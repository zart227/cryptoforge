from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LiveConfigRequest:
    api_key_env: str = "BYBIT_API_KEY"
    api_secret_env: str = "BYBIT_API_SECRET"
    stake_amount: Decimal = Decimal("10")
    max_open_trades: int = 1
    pair_whitelist: tuple[str, ...] = ("BTC/USDT",)
    db_url: str = "sqlite:////opt/cryptoforge/data/tradesv3.live.sqlite"
    strategy: str = "CryptoForgeBaselineStrategy"


def build_live_config(request: LiveConfigRequest) -> dict[str, Any]:
    if request.stake_amount <= 0:
        raise ValueError("stake_amount must be positive")
    if request.max_open_trades < 1:
        raise ValueError("max_open_trades must be at least 1")
    if not request.pair_whitelist:
        raise ValueError("pair_whitelist must not be empty")

    return {
        "$schema": "https://schema.freqtrade.io/schema.json",
        "bot_name": "cryptoforge-live-pilot",
        "initial_state": "stopped",
        "trading_mode": "spot",
        "margin_mode": "",
        "dry_run": False,
        "cancel_open_orders_on_exit": True,
        "max_open_trades": request.max_open_trades,
        "stake_currency": "USDT",
        "stake_amount": str(request.stake_amount),
        "tradable_balance_ratio": 0.99,
        "fiat_display_currency": "USD",
        "timeframe": "5m",
        "db_url": request.db_url,
        "strategy": request.strategy,
        "exchange": {
            "name": "bybit",
            "key": f"${{{request.api_key_env}}}",
            "secret": f"${{{request.api_secret_env}}}",
            "enable_ws": False,
            "ccxt_config": {"enableRateLimit": True},
            "ccxt_async_config": {"enableRateLimit": True},
            "pair_whitelist": list(request.pair_whitelist),
            "pair_blacklist": [],
        },
        "pairlists": [{"method": "StaticPairList"}],
        "entry_pricing": {
            "price_side": "same",
            "use_order_book": True,
            "order_book_top": 1,
            "price_last_balance": 0.0,
            "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": 1},
        },
        "exit_pricing": {
            "price_side": "same",
            "use_order_book": True,
            "order_book_top": 1,
        },
        "order_types": {
            "entry": "limit",
            "exit": "limit",
            "emergency_exit": "market",
            "force_entry": "limit",
            "force_exit": "market",
            "stoploss": "market",
            "stoploss_on_exchange": False,
        },
        "order_time_in_force": {"entry": "GTC", "exit": "GTC"},
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "internals": {"process_throttle_secs": 5},
    }


def write_live_config(path: str | Path, request: LiveConfigRequest) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    config = build_live_config(request)
    target.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
