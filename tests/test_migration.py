from datetime import UTC, datetime
import tarfile

from cryptoforge.backup import verify_backup
from cryptoforge.migration import (
    DEFAULT_MIGRATION_CHECKLIST,
    create_migration_export,
    import_migration_export,
)
from tests.test_backup import make_project


def test_migration_export_is_compact_and_restorable(tmp_path) -> None:
    project = tmp_path / "project"
    packages = tmp_path / "packages"
    imported = tmp_path / "imported"
    project.mkdir()
    make_project(project)

    result = create_migration_export(
        project,
        packages,
        timestamp=datetime(2026, 9, 25, 13, 0, tzinfo=UTC),
    )

    assert result.archive_path.name == "cryptoforge-migration-20260925T130000Z.tar.gz"
    assert verify_backup(result.archive_path, result.checksum_path)
    import_migration_export(result.archive_path, imported, checksum_path=result.checksum_path)

    assert (imported / "config" / "risk.dry-run.json").exists()
    assert (imported / "supabase" / "migrations" / "001.sql").exists()
    assert (imported / "data" / "outbox.sqlite3").exists()
    assert not (imported / "data" / "candles").exists()
    assert not (imported / ".env").exists()


def test_migration_archive_does_not_depend_on_full_disk_copy(tmp_path) -> None:
    project = tmp_path / "project"
    packages = tmp_path / "packages"
    project.mkdir()
    make_project(project)

    result = create_migration_export(project, packages)

    with tarfile.open(result.archive_path, "r:gz") as archive:
        names = set(archive.getnames())

    assert "BACKUP_MANIFEST.json" in names
    assert "data/candles/BTC.feather" not in names
    assert ".git/config" not in names
    assert ".env" not in names


def test_migration_checklist_documents_old_and_new_vps_order() -> None:
    assert DEFAULT_MIGRATION_CHECKLIST.old_vps_steps[0] == "stop research jobs"
    assert "flush Supabase outbox" in DEFAULT_MIGRATION_CHECKLIST.old_vps_steps
    assert DEFAULT_MIGRATION_CHECKLIST.new_vps_steps[0] == "clone repository"
    assert "restore secrets securely outside git" in DEFAULT_MIGRATION_CHECKLIST.new_vps_steps
    assert DEFAULT_MIGRATION_CHECKLIST.new_vps_steps[-1] == "verify monitoring health"
