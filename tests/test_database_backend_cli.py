import json
import stat

import pytest

from scripts import database_backend as cli


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "STATE", tmp_path / ".local/database")
    cli.init()
    (tmp_path / ".env").write_text("# keep\nSUPABASE_URL=https://example.supabase.co\nSUPABASE_SERVICE_ROLE_KEY=cloud\n")
    return tmp_path


def test_failed_probe_leaves_selection_and_secrets_unchanged(workspace, monkeypatch):
    original = (workspace / ".env").read_bytes()
    def unavailable(name):
        raise ConnectionError("target unavailable")
    monkeypatch.setattr(cli, "checked_backend", unavailable)
    with pytest.raises(ConnectionError):
        cli.switch("local")
    assert (workspace / ".env").read_bytes() == original
    assert not (cli.STATE / "env-before-first-switch").exists()


def test_switch_preserves_cloud_configuration_and_original_backup(workspace, monkeypatch):
    original = (workspace / ".env").read_bytes()
    monkeypatch.setattr(cli, "checked_backend", lambda name: None)
    cli.switch("local")
    cli.switch("supabase")
    contents = (workspace / ".env").read_text()
    assert contents.count("CRYPTOFORGE_BACKEND=") == 1
    assert "CRYPTOFORGE_BACKEND=supabase" in contents
    assert "SUPABASE_SERVICE_ROLE_KEY=cloud" in contents
    assert (cli.STATE / "env-before-first-switch").read_bytes() == original
    assert stat.S_IMODE((workspace / ".env").stat().st_mode) == 0o600
    assert stat.S_IMODE((cli.STATE / "api-key").stat().st_mode) == 0o600


def test_init_does_not_rotate_existing_database_credentials(workspace):
    original = (cli.STATE / "compose.env").read_bytes()
    with pytest.raises(ValueError, match="already exist"):
        cli.init()
    assert (cli.STATE / "compose.env").read_bytes() == original
