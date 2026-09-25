from pathlib import Path


def test_live_blockers_remain_explicit() -> None:
    text = Path("docs/LIVE_BLOCKERS.md").read_text(encoding="utf-8")

    required = [
        "dedicated limited Bybit sub-account",
        "withdrawal permission is confirmed absent",
        "small capital allocation is explicitly chosen",
        "separate live config",
        "backup/restore is verified immediately before live start",
        "live kill switch is tested",
        "real trading remains disabled",
    ]

    for phrase in required:
        assert phrase in text
