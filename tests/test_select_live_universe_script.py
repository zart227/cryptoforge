from scripts.select_live_universe import (
    bybit_symbol_to_freqtrade_pair,
    harden_bybit_ccxt_config,
    normalize_stake_amount,
)
from scripts.sync_supabase_market_data import load_pairs


def test_bybit_symbol_to_freqtrade_pair_supports_usdt_spot() -> None:
    assert bybit_symbol_to_freqtrade_pair("SOLUSDT") == "SOL/USDT"


def test_bybit_symbol_to_freqtrade_pair_rejects_non_usdt() -> None:
    try:
        bybit_symbol_to_freqtrade_pair("BTCEUR")
    except ValueError:
        return
    raise AssertionError("non-USDT symbol should be rejected")


def test_harden_bybit_ccxt_config_migrates_existing_live_config() -> None:
    config = {
        "exchange": {
            "ccxt_config": {"enableRateLimit": False},
            "ccxt_async_config": {"enableRateLimit": True},
        }
    }

    harden_bybit_ccxt_config(config)

    for key in ("ccxt_config", "ccxt_async_config"):
        assert config["exchange"][key]["enableRateLimit"] is True
        assert config["exchange"][key]["has"]["fetchCurrencies"] is False
        assert config["exchange"][key]["options"]["fetchCurrencies"] is False


def test_normalize_stake_amount_converts_numeric_string() -> None:
    config = {"stake_amount": "10"}

    normalize_stake_amount(config)

    assert config["stake_amount"] == 10.0


def test_market_sync_loads_pairs_from_universe_file(tmp_path) -> None:
    universe = tmp_path / "live-universe.json"
    universe.write_text('{"pairs": ["SOL/USDT", "LINK/USDT"]}', encoding="utf-8")

    args = type("Args", (), {"pair": None, "live_config": universe})()

    assert load_pairs(args) == ["SOL/USDT", "LINK/USDT"]
