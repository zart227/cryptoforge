import pytest
from sqlalchemy.engine import make_url

from scripts.freqtrade_supabase_url import build_runtime_url


def test_freqtrade_url_uses_private_schema_and_ssl() -> None:
    source = (
        "postgres://postgres.project-ref:encoded%40password@"
        "aws-region.pooler.supabase.com:5432/postgres"
    )

    result = make_url(build_runtime_url(source))

    assert result.drivername == "postgresql+psycopg"
    assert result.password == "encoded@password"
    assert result.query["sslmode"] == "require"
    assert result.query["options"] == "-c search_path=freqtrade"
    assert result.query["connect_timeout"] == "10"
    assert result.query["keepalives_idle"] == "30"


@pytest.mark.parametrize(
    "source",
    [
        "sqlite:///trades.sqlite",
        "postgresql://postgres:secret@localhost:5432/postgres",
        "postgresql://postgres.project-ref:secret@"
        "aws-region.pooler.supabase.com:6543/postgres",
    ],
)
def test_freqtrade_url_rejects_non_session_supabase_connections(source: str) -> None:
    with pytest.raises(ValueError):
        build_runtime_url(source)


def test_freqtrade_url_rejects_caller_defined_search_path() -> None:
    source = (
        "postgres://postgres.project-ref:secret@"
        "aws-region.pooler.supabase.com:5432/postgres?options=-c+search_path%3Dpublic"
    )

    with pytest.raises(ValueError, match="Do not set search_path"):
        build_runtime_url(source)


def test_local_freqtrade_uses_loopback_and_private_schema():
    result = make_url(build_runtime_url(
        "postgresql://freqtrade_worker:secret@127.0.0.1:55432/cryptoforge", backend="local"))
    assert result.query["options"] == "-c search_path=freqtrade"
    assert result.query["sslmode"] == "disable"
    assert result.username == "freqtrade_worker"


@pytest.mark.parametrize("source", [
    "postgresql://freqtrade_worker:secret@external.example:55432/cryptoforge",
    "postgresql://postgres:secret@127.0.0.1:55432/cryptoforge",
])
def test_local_freqtrade_rejects_remote_and_admin_connections(source):
    with pytest.raises(ValueError):
        build_runtime_url(source, backend="local")
