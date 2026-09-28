from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


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
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(read_status(args.database)))
        return 0
    if args.backup_dir is None:
        parser.error("backup requires --backup-dir")
    backup = backup_database(args.database, args.backup_dir)
    print(json.dumps({"backup": str(backup) if backup else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
