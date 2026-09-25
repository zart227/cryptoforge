from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cryptoforge.backup import (
    BackupResult,
    create_backup,
    restore_backup,
    verify_backup,
)


MIGRATION_INCLUDE_PATHS = (
    "config",
    "user_data/strategies",
    "supabase/migrations",
    "deploy",
    "data/outbox.sqlite3",
)


@dataclass(frozen=True)
class MigrationChecklist:
    old_vps_steps: tuple[str, ...]
    new_vps_steps: tuple[str, ...]


DEFAULT_MIGRATION_CHECKLIST = MigrationChecklist(
    old_vps_steps=(
        "stop research jobs",
        "gracefully stop trader",
        "flush Supabase outbox",
        "create compact migration export",
        "verify checksum",
    ),
    new_vps_steps=(
        "clone repository",
        "restore secrets securely outside git",
        "install runtime",
        "import critical state",
        "reconnect Supabase",
        "re-download reproducible market data",
        "start dry-run",
        "verify monitoring health",
    ),
)


def create_migration_export(
    project_root: Path,
    output_dir: Path,
    *,
    timestamp: datetime | None = None,
) -> BackupResult:
    return create_backup(
        project_root,
        output_dir,
        timestamp=timestamp,
        include_paths=MIGRATION_INCLUDE_PATHS,
        archive_prefix="cryptoforge-migration",
    )


def import_migration_export(
    archive_path: Path,
    restore_dir: Path,
    *,
    checksum_path: Path | None = None,
) -> tuple[Path, ...]:
    return restore_backup(archive_path, restore_dir, checksum_path=checksum_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create, verify, or import CryptoForge migration packages.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--project-root", type=Path, default=Path.cwd())
    export.add_argument("--output-dir", type=Path, default=Path("migration-packages"))

    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("checksum", type=Path)

    import_cmd = subparsers.add_parser("import")
    import_cmd.add_argument("archive", type=Path)
    import_cmd.add_argument("--checksum", type=Path)
    import_cmd.add_argument("--restore-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "export":
        result = create_migration_export(args.project_root, args.output_dir)
        print(result.archive_path)
        print(result.checksum_path)
        return 0
    if args.command == "verify":
        verify_backup(args.archive, args.checksum)
        print("ok")
        return 0
    if args.command == "import":
        import_migration_export(args.archive, args.restore_dir, checksum_path=args.checksum)
        print(args.restore_dir)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
