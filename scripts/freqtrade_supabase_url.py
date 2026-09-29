from __future__ import annotations

import os
import sys

from sqlalchemy.engine import make_url


def build_runtime_url(source: str) -> str:
    """Scope Freqtrade's SQLAlchemy connection to its private Supabase schema."""
    url = make_url(source)
    if url.drivername == "postgres":
        url = url.set(drivername="postgresql")
    if url.get_backend_name() != "postgresql":
        raise ValueError("SUPABASE_DB_URL must be a PostgreSQL connection URL")
    if not url.host or "pooler.supabase.com" not in url.host:
        raise ValueError("SUPABASE_DB_URL must use the Supabase session pooler")
    if url.port != 5432 or url.database != "postgres":
        raise ValueError("SUPABASE_DB_URL must use the session pooler on port 5432")
    if not url.username or "." not in url.username or not url.password:
        raise ValueError("SUPABASE_DB_URL is missing session-pooler credentials")

    query = dict(url.query)
    options = str(query.get("options", "")).strip()
    if "search_path" in options.lower():
        raise ValueError("Do not set search_path in SUPABASE_DB_URL; CryptoForge sets it")
    query["options"] = f"{options} -c search_path=freqtrade".strip()
    query["sslmode"] = "require"
    # Bound connection establishment and detect dead TCP sessions promptly.
    # This does not replay a failed transaction; the worker must restart on failure.
    for name, value in {
        "connect_timeout": "10",
        "keepalives": "1",
        "keepalives_idle": "30",
        "keepalives_interval": "10",
        "keepalives_count": "3",
    }.items():
        query.setdefault(name, value)

    return url.set(drivername="postgresql+psycopg", query=query).render_as_string(
        hide_password=False
    )


def main() -> int:
    source = os.environ.get("SUPABASE_DB_URL", "").strip()
    if not source:
        print("SUPABASE_DB_URL is required", file=sys.stderr)
        return 2
    try:
        print(build_runtime_url(source))
    except Exception as exc:  # Avoid logging a connection string or credentials.
        print(f"Invalid Supabase database configuration: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
