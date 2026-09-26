from pathlib import Path


def test_live_pilot_smoke_script_exists_and_avoids_orders() -> None:
    script = Path("scripts/live_pilot_smoke.py")
    text = script.read_text(encoding="utf-8")

    assert "create_order" not in text
    assert "place_order" not in text
    assert "BybitPrivateClient" in text
    assert "validate_live_freqtrade_config" in text
    assert "create_backup" in text
