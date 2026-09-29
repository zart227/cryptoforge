from datetime import UTC, datetime, timedelta

from cryptoforge.research_selection import NightResearchSelector


class FakeSelector(NightResearchSelector):
    def __init__(self, report):  # type: ignore[no-untyped-def]
        self.report = report

    def _latest_report(self):  # type: ignore[no-untyped-def]
        return self.report


def test_selector_uses_fresh_tradeable_night_candidates() -> None:
    selector = FakeSelector(
        {
            "generated_at": "2026-09-27T15:00:00+00:00",
            "results": [
                {"pair": "ETH/USDT", "recommendation": "low_priority", "score": "1"},
                {"pair": "NEAR/USDT", "recommendation": "volatile_but_wait_for_volume", "score": "10"},
                {"pair": "ENA/USDT", "recommendation": "watch_for_intraday_levels", "score": "9"},
            ],
        }
    )

    selection = selector.select_pairs(
        fallback_pairs=["ETH/USDT"],
        now=datetime(2026, 9, 27, 16, tzinfo=UTC),
    )

    assert selection.source == "night_research"
    assert selection.pairs == ("NEAR/USDT", "ENA/USDT")


def test_selector_falls_back_when_report_is_stale() -> None:
    selector = FakeSelector({"generated_at": "2026-09-25T15:00:00+00:00", "results": []})

    selection = selector.select_pairs(
        fallback_pairs=["ETH/USDT"],
        now=datetime(2026, 9, 27, 16, tzinfo=UTC),
        max_age=timedelta(hours=24),
    )

    assert selection.source == "fallback"
    assert selection.pairs == ("ETH/USDT",)
    assert "stale" in selection.reasons[0]
