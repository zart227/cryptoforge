from pathlib import Path

import pytest

from cryptoforge.backend import resolve_backend
from cryptoforge.supabase_market import SupabaseRestClient
from cryptoforge.telegram_relay import client_from_env


def test_cloud_is_default_and_preserves_secret_key_support():
    backend = resolve_backend({"SUPABASE_URL": "https://example.supabase.co/", "SUPABASE_SECRET_KEY": "cloud"})
    assert (backend.name, backend.url, backend.key) == ("supabase", "https://example.supabase.co", "cloud")


def test_local_never_uses_cloud_credentials(tmp_path, monkeypatch):
    key_file = tmp_path / "local-key"
    key_file.write_text("local-token\n")
    values = {"CRYPTOFORGE_BACKEND": "local", "CRYPTOFORGE_LOCAL_API_KEY_FILE": str(key_file),
              "SUPABASE_URL": "https://cloud.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "cloud-secret"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("CRYPTOFORGE_LOCAL_API_KEY", raising=False)
    backend = resolve_backend(values)
    client = SupabaseRestClient.from_env()
    relay = client_from_env(values)
    assert client.supabase_url == relay.supabase_url == backend.url == "http://127.0.0.1:54321"
    assert client.service_role_key == relay.service_role_key == "local-token"


def test_missing_local_credentials_do_not_fall_back_to_cloud(tmp_path):
    with pytest.raises(ValueError, match="Local API key missing"):
        resolve_backend({"CRYPTOFORGE_BACKEND": "local", "CRYPTOFORGE_LOCAL_API_KEY_FILE": str(tmp_path / "missing"),
                         "SUPABASE_URL": "https://cloud.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "secret"})


@pytest.mark.parametrize("url", ["https://evil.example", "http://192.168.1.1", "http://127.0.0.1.evil.example",
                                      "http://user:pass@localhost", "http://localhost?x=1"])
def test_local_credentials_cannot_be_sent_to_remote_host(url):
    with pytest.raises(ValueError):
        resolve_backend({"CRYPTOFORGE_BACKEND": "local", "CRYPTOFORGE_LOCAL_API_URL": url,
                         "CRYPTOFORGE_LOCAL_API_KEY": "local"})


def test_unknown_backend_rejected():
    with pytest.raises(ValueError, match="must be local or supabase"):
        resolve_backend({"CRYPTOFORGE_BACKEND": "locla"})
