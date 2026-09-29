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
