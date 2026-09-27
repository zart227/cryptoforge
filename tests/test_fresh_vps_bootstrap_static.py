from pathlib import Path


BOOTSTRAP = Path("deploy/bootstrap_fresh_vps.sh")
DOCS = Path("docs/FRESH_VPS_BOOTSTRAP.md")


def test_fresh_vps_bootstrap_installs_core_runtime_without_secrets() -> None:
    script = BOOTSTRAP.read_text(encoding="utf-8")

    assert "apt-get install" in script
    assert "git clone" in script
    assert "python3-venv" in script
    assert "pip\" install freqtrade" in script
    assert "cryptoforge-live-pilot.service" in script
    assert "cryptoforge-git-sync.timer" in script
    assert "BYBIT_API_KEY=" not in script
    assert "BYBIT_API_SECRET=" not in script


def test_live_pilot_service_uses_secret_export_wrapper() -> None:
    unit = Path("deploy/systemd/cryptoforge-live-pilot.service").read_text(encoding="utf-8")
    wrapper = Path("deploy/run_live_pilot.sh").read_text(encoding="utf-8")
    update = Path("deploy/update_vps.sh").read_text(encoding="utf-8")

    assert "EnvironmentFile=/opt/cryptoforge/app/.env" in unit
    assert "ExecStart=/opt/cryptoforge/app/cryptoforge_repo/deploy/run_live_pilot.sh" in unit
    assert "FREQTRADE__EXCHANGE__KEY" in wrapper
    assert "FREQTRADE__EXCHANGE__SECRET" in wrapper
    assert "cryptoforge-live-pilot.service" in update


def test_fresh_vps_bootstrap_docs_keep_live_start_manual() -> None:
    docs = DOCS.read_text(encoding="utf-8")

    assert "Do not start live trading until the smoke check is green" in docs
    assert "Start only after final approval" in docs
