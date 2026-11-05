from __future__ import annotations

import os
from pathlib import Path
import sys

from sqlalchemy.engine import make_url


def build_runtime_url(source: str, *, backend: str = "supabase") -> str:
    """Scope Freqtrade's SQLAlchemy connection to its private Supabase schema."""
    url = make_url(source)
    if url.drivername == "postgres":
        url = url.set(drivername="postgresql")
    if url.get_backend_name() != "postgresql":
        raise ValueError("SUPABASE_DB_URL must be a PostgreSQL connection URL")
    if backend == "supabase":
        if not url.host or not url.host.endswith(".pooler.supabase.com"):
            raise ValueError("SUPABASE_DB_URL must use the Supabase session pooler")
        if url.port != 5432 or url.database != "postgres":
            raise ValueError("SUPABASE_DB_URL must use the session pooler on port 5432")
        if not url.username or "." not in url.username or not url.password:
            raise ValueError("SUPABASE_DB_URL is missing session-pooler credentials")
    elif backend == "local":
        if url.host not in {"localhost", "127.0.0.1", "::1"} or url.database != "cryptoforge":
            raise ValueError("Local database must be cryptoforge on loopback")
        if url.username != "freqtrade_worker" or not url.password:
            raise ValueError("Local Freqtrade must use its dedicated database role")
    else:
        raise ValueError("CRYPTOFORGE_BACKEND must be local or supabase")

    query = dict(url.query)
    options = str(query.get("options", "")).strip()
    if "search_path" in options.lower():
        raise ValueError("Do not set search_path in SUPABASE_DB_URL; CryptoForge sets it")
    query["options"] = f"{options} -c search_path=freqtrade".strip()
    query["sslmode"] = "require" if backend == "supabase" else "disable"
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
    try:
        backend = os.environ.get("CRYPTOFORGE_BACKEND", "supabase").strip().lower()
        if backend == "local":
            path = Path(os.environ.get("CRYPTOFORGE_LOCAL_DB_URL_FILE", ".local/database/freqtrade-url"))
            source = path.read_text().strip()
        else:
            source = os.environ.get("SUPABASE_DB_URL", "").strip()
        if not source:
            raise ValueError("Database URL required")
        print(build_runtime_url(source, backend=backend))
    except Exception as exc:  # Avoid logging a connection string or credentials.
        print(f"Invalid Supabase database configuration: {type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
