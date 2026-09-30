from pathlib import Path


def test_windows_executor_uses_research_emerging_and_ml_gate() -> None:
    text = Path("deploy/install_windows_supabase_executor.ps1").read_text(encoding="utf-8")
    for required in (
        "--use-night-research",
        "--night-research-limit 12",
        "--allow-intraday-reversion",
        "--allow-emerging-momentum",
        "--stake-amount 5",
        "--max-open-positions 3",
        "--max-daily-loss 2",
        "--stop-loss-percent 0.04",
        "--ml-mode gate",
        "--ml-threshold 0.50",
        "--ml-max-age-hours 36",
        "--live",
    ):
        assert required in text
    assert "New-TimeSpan -Minutes 2" in text
    assert "MultipleInstances IgnoreNew" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "pythonw.exe" in text
    assert "windows_background_runner.py" in text
    assert "powershell.exe" not in text
