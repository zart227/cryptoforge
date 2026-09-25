import json
from decimal import Decimal

from cryptoforge.live_config import LiveConfigRequest, build_live_config, write_live_config
from cryptoforge.live_pilot import validate_live_freqtrade_config


def test_live_config_generator_creates_separate_spot_only_config_without_plain_secrets(tmp_path) -> None:
    request = LiveConfigRequest(
        stake_amount=Decimal("10"),
        max_open_trades=1,
        pair_whitelist=("BTC/USDT",),
    )

    config = build_live_config(request)

    assert config["dry_run"] is False
    assert config["initial_state"] == "stopped"
    assert config["trading_mode"] == "spot"
    assert config["margin_mode"] == ""
    assert config["max_open_trades"] == 1
    assert config["exchange"]["key"] == "${BYBIT_API_KEY}"
    assert config["exchange"]["secret"] == "${BYBIT_API_SECRET}"
    assert config["telegram"]["enabled"] is False
    assert "leverage" not in json.dumps(config).lower()

    target = write_live_config(tmp_path / "freqtrade.live.json", request)
    blockers = validate_live_freqtrade_config(target)

    assert blockers == ()


def test_live_config_generator_rejects_unbounded_inputs() -> None:
    for request in (
        LiveConfigRequest(stake_amount=Decimal("0")),
        LiveConfigRequest(max_open_trades=0),
        LiveConfigRequest(pair_whitelist=()),
    ):
        try:
            build_live_config(request)
        except ValueError:
            continue
        raise AssertionError("request should have been rejected")
