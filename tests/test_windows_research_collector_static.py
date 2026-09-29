from pathlib import Path


def test_research_collector_runs_dynamic_scan_every_two_minutes() -> None:
    text = Path("deploy/install_windows_research_collector.ps1").read_text(encoding="utf-8")
    assert "-scan-universe" in text.lower()
    assert "New-TimeSpan -Minutes 2" in text
    assert "MultipleInstances IgnoreNew" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" not in text
