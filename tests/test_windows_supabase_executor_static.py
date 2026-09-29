from pathlib import Path


def test_windows_executor_uses_research_emerging_and_ml_shadow() -> None:
    text = Path("deploy/install_windows_supabase_executor.ps1").read_text(encoding="utf-8")
    for required in (
        "--use-night-research",
        "--night-research-limit 8",
        "--allow-intraday-reversion",
        "--allow-emerging-momentum",
        "--ml-mode shadow",
        "--ml-threshold 0.55",
        "--ml-max-age-hours 36",
        "--live",
    ):
        assert required in text
    assert "New-TimeSpan -Minutes 2" in text
    assert "MultipleInstances IgnoreNew" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
