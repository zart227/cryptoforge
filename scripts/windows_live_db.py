from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text


def read_status(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"open_trades": 0, "open_orders": 0}
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("PRAGMA busy_timeout=10000")
        trades = connection.execute(
            "SELECT COUNT(*) FROM trades WHERE is_open = 1"
        ).fetchone()[0]
        orders = connection.execute(
            "SELECT COUNT(*) FROM orders WHERE ft_is_open = 1"
        ).fetchone()[0]
        return {"open_trades": int(trades), "open_orders": int(orders)}
    finally:
        connection.close()


def read_postgres_status(db_url: str) -> dict[str, int]:
    engine = create_engine(
        db_url,
        connect_args={"connect_timeout": 10, "sslmode": "require"},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as connection:
            tables = connection.execute(
                text(
                    """select
                        to_regclass('trades') is not null as has_trades,
                        to_regclass('orders') is not null as has_orders"""
                )
            ).mappings().one()
            open_trades = 0
            open_orders = 0
            if tables["has_trades"]:
                open_trades = connection.execute(
                    text("select count(*) from trades where is_open = true")
                ).scalar_one()
            if tables["has_orders"]:
                open_orders = connection.execute(
                    text("select count(*) from orders where ft_is_open = true")
                ).scalar_one()
            return {"open_trades": int(open_trades), "open_orders": int(open_orders)}
    finally:
        engine.dispose()


def backup_database(source: Path, directory: Path) -> Path | None:
    if not source.exists():
        return None
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"tradesv3-pre-git-update-{stamp}.sqlite"
    src = sqlite3.connect(source, timeout=10)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "backup"))
    parser.add_argument("--database", type=Path)
    parser.add_argument("--live-supabase", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.command == "status":
        if args.live_supabase:
            db_url = os.environ.get("FREQTRADE__DB_URL", "")
            if not db_url.startswith("postgresql+psycopg://"):
                parser.error("FREQTRADE__DB_URL is not configured for Supabase Postgres")
            try:
                status = read_postgres_status(db_url)
            except Exception as exc:  # Do not leak a DSN into logs.
                print(json.dumps({"error": type(exc).__name__}))
                return 1
            print(json.dumps(status))
            return 0
        if args.database is None:
            parser.error("status requires --database or --live-supabase")
        print(json.dumps(read_status(args.database)))
        return 0
    if args.live_supabase:
        parser.error("Supabase backups are managed outside the local SQLite helper")
    if args.database is None or args.backup_dir is None:
        parser.error("backup requires --backup-dir")
    backup = backup_database(args.database, args.backup_dir)
    print(json.dumps({"backup": str(backup) if backup else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
