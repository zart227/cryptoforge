from pathlib import Path


STRATEGY = Path("user_data/strategies/CryptoForgeLongShortResearchStrategy.py")
DOCS = Path("docs/LONG_SHORT_RESEARCH.md")


def test_long_short_research_strategy_is_not_spot_live_strategy() -> None:
    source = STRATEGY.read_text(encoding="utf-8")

    assert "can_short = True" in source
    assert "research_short_level_signal" in source
    assert "research_short_exit" in source
    assert "support_breakdown" in source
    assert "resistance_reject" in source


def test_long_short_research_docs_keep_derivatives_out_of_first_live_pilot() -> None:
    docs = DOCS.read_text(encoding="utf-8")

    assert "research-only" in docs
    assert "must not be wired into the first" in docs
    assert "Real derivatives, margin or leverage remain blocked" in docs
