from pathlib import Path


def test_derivatives_policy_keeps_live_trading_separate() -> None:
    text = Path("docs/DERIVATIVES_RESEARCH_POLICY.md").read_text(encoding="utf-8")

    required = [
        "paper",
        "shadow",
        "backtest mode",
        "enable live Futures trading",
        "enable leverage",
        "applied to live trading",
        "automatically",
        "Current Phase 31 remains Spot-only",
    ]

    for phrase in required:
        assert phrase in text
