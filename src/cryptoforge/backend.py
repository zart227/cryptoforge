"""Explicit backend selection; never fall back between divergent databases."""
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Backend:
    name: str
    url: str
    key: str


def resolve_backend(env: Mapping[str, str]) -> Backend:
    name = env.get("CRYPTOFORGE_BACKEND", "supabase").strip().lower()
    if name == "supabase":
        url = env.get("SUPABASE_URL", "")
        key = env.get("SUPABASE_SERVICE_ROLE_KEY", "") or env.get("SUPABASE_SECRET_KEY", "")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SECRET_KEY are required")
    elif name == "local":
        url = env.get("CRYPTOFORGE_LOCAL_API_URL", "http://127.0.0.1:54321")
        key = env.get("CRYPTOFORGE_LOCAL_API_KEY", "")
        if not key:
            key_file = env.get("CRYPTOFORGE_LOCAL_API_KEY_FILE", ".local/database/api-key")
            try:
                key = Path(key_file).read_text().strip()
            except OSError:
                raise ValueError("Local API key missing; run scripts/database_backend.py init") from None
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Local backend API must use HTTP on a loopback address")
        if not key or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Invalid local backend configuration")
    else:
        raise ValueError("CRYPTOFORGE_BACKEND must be local or supabase")
    return Backend(name, url.rstrip("/"), key)
