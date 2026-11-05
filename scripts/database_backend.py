"""Manage the loopback PostgreSQL/PostgREST backend without printing secrets."""
from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib import request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cryptoforge.backend import resolve_backend

STATE = ROOT / ".local/database"


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for raw in path.read_text().splitlines():
            if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw:
                key, value = raw.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    return values


def compose(*args: str, **kwargs):
    return subprocess.run(["docker", "compose", "--env-file", str(STATE / "compose.env"),
                           "-f", str(ROOT / "docker/database.compose.yml"), *args],
                          check=True, **kwargs)


def init() -> None:
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (STATE / "compose.env").exists() or (STATE / "api-key").exists():
        raise ValueError("Local credentials already exist; refusing to rotate them implicitly")
    jwt_secret = secrets.token_hex(32)
    def b64(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    body = b64(b'{"alg":"HS256","typ":"JWT"}') + "." + b64(
        b'{"role":"service_role","aud":"cryptoforge-local"}')
    token = body + "." + b64(hmac.new(jwt_secret.encode(), body.encode(), hashlib.sha256).digest())
    config = {"POSTGRES_PASSWORD": secrets.token_hex(24),
              "POSTGREST_DB_PASSWORD": secrets.token_hex(24),
              "FREQTRADE_DB_PASSWORD": secrets.token_hex(24),
              "POSTGREST_JWT_SECRET": jwt_secret}
    for name, content in (("compose.env", "".join(f"{k}={v}\n" for k, v in config.items())),
                          ("api-key", token + "\n"),
                          ("freqtrade-url", "postgresql://freqtrade_worker:" + config["FREQTRADE_DB_PASSWORD"]
                           + "@127.0.0.1:55432/cryptoforge\n")):
        fd = os.open(STATE / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
    print("Local credentials created in .local/database (not in Git)")


def checked_backend(name: str):
    env = {**os.environ, **read_env(ROOT / ".env"), "CRYPTOFORGE_BACKEND": name,
           "CRYPTOFORGE_LOCAL_API_KEY_FILE": str(STATE / "api-key")}
    backend = resolve_backend(env)
    req = request.Request(backend.url + "/rest/v1/market_candles?select=id&limit=1",
                          headers={"apikey": backend.key, "Authorization": "Bearer " + backend.key})
    with request.urlopen(req, timeout=15) as response:
        rows = json.loads(response.read())
    if not isinstance(rows, list):
        raise ValueError("Backend did not return a row array")
    return backend


def switch(name: str) -> None:
    checked_backend(name)  # Never commit an unavailable target to the config.
    path = ROOT / ".env"
    original = path.read_text()
    backup = STATE / "env-before-first-switch"
    if not backup.exists():
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(original)
    lines = [line for line in original.splitlines()
             if line.split("=", 1)[0].strip() not in {
                 "CRYPTOFORGE_BACKEND", "CRYPTOFORGE_LOCAL_API_KEY_FILE"}]
    lines += [f"CRYPTOFORGE_BACKEND={name}",
              f"CRYPTOFORGE_LOCAL_API_KEY_FILE={STATE / 'api-key'}"]
    temp = path.with_name(".env.backend-switch")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write("\n".join(lines) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    print(f"Backend switched to {name}. Restart existing workers to apply; databases are NOT synchronized.")


def backup() -> None:
    directory = STATE / "backups"
    directory.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"cryptoforge-{stamp}.dump"
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        compose("exec", "-T", "db", "pg_dump", "-U", "postgres", "-d", "cryptoforge",
                "--format=custom", stdout=stream)
    if path.stat().st_size == 0:
        raise ValueError("Empty backup")
    print(path)


def main() -> int:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "start", "status", "backup"):
        sub.add_parser(name)
    restore = sub.add_parser("restore", help="Restore a local backup into an empty database")
    restore.add_argument("archive", type=Path)
    change = sub.add_parser("switch")
    change.add_argument("backend", choices=("local", "supabase"))
    args = parser.parse_args()
    if args.command == "init":
        init()
    elif args.command == "start":
        compose("up", "-d", "--wait")
    elif args.command == "switch":
        switch(args.backend)
    elif args.command == "backup":
        backup()
    elif args.command == "restore":
        # Existing tables make pg_restore fail; one transaction rolls everything back.
        with args.archive.open("rb") as stream:
            compose("exec", "-T", "db", "pg_restore", "-U", "postgres", "-d", "cryptoforge",
                    "--single-transaction", "--exit-on-error", stdin=stream)
        compose("exec", "-T", "db", "psql", "-X", "-U", "postgres", "-d", "cryptoforge",
                "-c", "NOTIFY pgrst, 'reload schema'")
    else:
        name = read_env(ROOT / ".env").get("CRYPTOFORGE_BACKEND", "supabase")
        backend = checked_backend(name)
        print(f"backend={backend.name} url={backend.url} read_check=ok")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # HTTP/DB exception messages may contain credentials or response payloads.
        print(f"Database operation failed ({type(exc).__name__}); configuration unchanged if probe failed.", file=sys.stderr)
        raise SystemExit(1)
