from scripts.select_live_universe import bybit_symbol_to_freqtrade_pair


def test_bybit_symbol_to_freqtrade_pair_supports_usdt_spot() -> None:
    assert bybit_symbol_to_freqtrade_pair("SOLUSDT") == "SOL/USDT"


def test_bybit_symbol_to_freqtrade_pair_rejects_non_usdt() -> None:
    try:
        bybit_symbol_to_freqtrade_pair("BTCEUR")
    except ValueError:
        return
    raise AssertionError("non-USDT symbol should be rejected")
