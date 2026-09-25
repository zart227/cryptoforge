from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_INCLUDE_PATHS = (
    "config",
    "user_data/strategies",
    "supabase/migrations",
    "deploy",
    "data/outbox.sqlite3",
)

DEFAULT_EXCLUDE_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "backtest_results",
    "cache",
    "candles",
    "data/bybit",
    "data/downloaded",
    "hyperopt_results",
    "logs",
    "market_history",
}


@dataclass(frozen=True)
class BackupManifest:
    created_at: str
    root_name: str
    included_paths: tuple[str, ...]
    file_count: int

    def as_json(self) -> str:
        return json.dumps(
            {
                "created_at": self.created_at,
                "root_name": self.root_name,
                "included_paths": list(self.included_paths),
                "file_count": self.file_count,
            },
            indent=2,
            sort_keys=True,
        )


@dataclass(frozen=True)
class BackupResult:
    archive_path: Path
    checksum_path: Path
    sha256: str
    manifest: BackupManifest


def create_backup(
    project_root: Path,
    output_dir: Path,
    *,
    timestamp: datetime | None = None,
    include_paths: tuple[str, ...] = DEFAULT_INCLUDE_PATHS,
) -> BackupResult:
    project_root = project_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = timestamp or datetime.now(UTC)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    stamp = created_at.strftime("%Y%m%dT%H%M%SZ")
    archive_path = output_dir / f"cryptoforge-backup-{stamp}.tar.gz"
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")

    files = collect_backup_files(project_root, include_paths=include_paths)
    manifest = BackupManifest(
        created_at=created_at.isoformat(),
        root_name=project_root.name,
        included_paths=include_paths,
        file_count=len(files),
    )

    with tarfile.open(archive_path, "w:gz") as archive:
        manifest_bytes = manifest.as_json().encode("utf-8")
        manifest_info = tarfile.TarInfo("BACKUP_MANIFEST.json")
        manifest_info.size = len(manifest_bytes)
        manifest_info.mtime = int(created_at.timestamp())
        archive.addfile(manifest_info, fileobj=_BytesReader(manifest_bytes))
        for path in files:
            archive.add(path, arcname=path.relative_to(project_root))

    sha256 = sha256_file(archive_path)
    checksum_path.write_text(f"{sha256}  {archive_path.name}\n", encoding="utf-8")
    verify_backup(archive_path, checksum_path)
    return BackupResult(archive_path, checksum_path, sha256, manifest)


def restore_backup(
    archive_path: Path,
    restore_dir: Path,
    *,
    checksum_path: Path | None = None,
) -> tuple[Path, ...]:
    if checksum_path is not None:
        verify_backup(archive_path, checksum_path)
    restore_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            target = safe_extract_target(restore_dir, member.name)
            archive.extract(member, path=restore_dir, filter="data")
            extracted.append(target)
    return tuple(extracted)


def verify_backup(archive_path: Path, checksum_path: Path) -> bool:
    expected = checksum_path.read_text(encoding="utf-8").split()[0]
    actual = sha256_file(archive_path)
    if actual != expected:
        raise ValueError("backup checksum mismatch")
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
        if "BACKUP_MANIFEST.json" not in names:
            raise ValueError("backup manifest missing")
    return True


def collect_backup_files(
    project_root: Path,
    *,
    include_paths: tuple[str, ...] = DEFAULT_INCLUDE_PATHS,
) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in include_paths:
        path = project_root / relative
        if not path.exists():
            continue
        if should_exclude(path, project_root):
            continue
        if path.is_file():
            files.append(path)
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file() and not should_exclude(child, project_root):
                files.append(child)
    return tuple(sorted(files))


def should_exclude(path: Path, project_root: Path) -> bool:
    relative = path.relative_to(project_root)
    if relative.name == ".env":
        return True
    relative_text = relative.as_posix()
    for part in DEFAULT_EXCLUDE_PARTS:
        if relative_text == part or relative_text.startswith(f"{part}/") or part in relative.parts:
            return True
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract_target(restore_dir: Path, member_name: str) -> Path:
    target = (restore_dir / member_name).resolve()
    root = restore_dir.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"unsafe archive path: {member_name}")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create, verify, or restore CryptoForge backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--project-root", type=Path, default=Path.cwd())
    create.add_argument("--output-dir", type=Path, default=Path("backups"))

    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    verify.add_argument("checksum", type=Path)

    restore = subparsers.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--checksum", type=Path)
    restore.add_argument("--restore-dir", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "create":
        result = create_backup(args.project_root, args.output_dir)
        print(result.archive_path)
        print(result.checksum_path)
        return 0
    if args.command == "verify":
        verify_backup(args.archive, args.checksum)
        print("ok")
        return 0
    if args.command == "restore":
        restore_backup(args.archive, args.restore_dir, checksum_path=args.checksum)
        print(args.restore_dir)
        return 0
    return 2


class _BytesReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.data) - self.offset
        chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


if __name__ == "__main__":
    raise SystemExit(main())
