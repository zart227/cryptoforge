from pathlib import Path


SCRIPT = Path("deploy/post_bootstrap_restore.sh")


def test_post_bootstrap_restore_runs_smoke_without_starting_live_service() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "scripts/select_live_universe.py" in text
    assert "scripts/live_pilot_smoke.py" in text
    assert "install_github_runner.sh" in text
    assert "systemctl start cryptoforge-live-pilot.service" not in text
