from datetime import UTC, datetime
import tarfile

import pytest

from cryptoforge.backup import (
    collect_backup_files,
    create_backup,
    restore_backup,
    verify_backup,
)


def make_project(root):  # type: ignore[no-untyped-def]
    (root / "config").mkdir()
    (root / "config" / "risk.dry-run.json").write_text("{}", encoding="utf-8")
    (root / "user_data" / "strategies").mkdir(parents=True)
    (root / "user_data" / "strategies" / "Strategy.py").write_text("class S:\n    value = 1\n", encoding="utf-8")
    (root / "supabase" / "migrations").mkdir(parents=True)
    (root / "supabase" / "migrations" / "001.sql").write_text("select 1;", encoding="utf-8")
    (root / "deploy" / "systemd").mkdir(parents=True)
    (root / "deploy" / "systemd" / "svc.service").write_text("[Service]", encoding="utf-8")
    (root / "data").mkdir()
    (root / "data" / "outbox.sqlite3").write_bytes(b"outbox")
    (root / "data" / "candles").mkdir()
    (root / "data" / "candles" / "BTC.feather").write_bytes(b"large-cache")
    (root / ".env").write_text("LOCAL_SECRET_PLACEHOLDER=excluded\n", encoding="utf-8")


def test_backup_collects_critical_files_without_env_or_candle_cache(tmp_path) -> None:
    make_project(tmp_path)

    files = {path.relative_to(tmp_path).as_posix() for path in collect_backup_files(tmp_path)}

    assert "config/risk.dry-run.json" in files
    assert "user_data/strategies/Strategy.py" in files
    assert "supabase/migrations/001.sql" in files
    assert "deploy/systemd/svc.service" in files
    assert "data/outbox.sqlite3" in files
    assert ".env" not in files
    assert "data/candles/BTC.feather" not in files


def test_create_verify_and_restore_backup(tmp_path) -> None:
    project = tmp_path / "project"
    output = tmp_path / "backups"
    restore = tmp_path / "restore"
    project.mkdir()
    make_project(project)

    result = create_backup(
        project,
        output,
        timestamp=datetime(2026, 9, 25, 12, 0, tzinfo=UTC),
    )

    assert result.archive_path.name == "cryptoforge-backup-20260925T120000Z.tar.gz"
    assert result.checksum_path.exists()
    assert verify_backup(result.archive_path, result.checksum_path)

    restore_backup(result.archive_path, restore, checksum_path=result.checksum_path)

    assert (restore / "BACKUP_MANIFEST.json").exists()
    assert (restore / "config" / "risk.dry-run.json").exists()
    assert (restore / "user_data" / "strategies" / "Strategy.py").exists()
    assert (restore / "data" / "outbox.sqlite3").read_bytes() == b"outbox"
    assert not (restore / ".env").exists()
    assert not (restore / "data" / "candles").exists()


def test_verify_rejects_checksum_mismatch(tmp_path) -> None:
    project = tmp_path / "project"
    output = tmp_path / "backups"
    project.mkdir()
    make_project(project)
    result = create_backup(project, output)
    result.checksum_path.write_text("0" * 64 + f"  {result.archive_path.name}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_backup(result.archive_path, result.checksum_path)


def test_restore_rejects_path_traversal(tmp_path) -> None:
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 0
        handle.addfile(info)

    with pytest.raises(ValueError, match="unsafe archive path"):
        restore_backup(archive, tmp_path / "restore")


def test_live_decision_journals_restore_committed_wal_and_original_reasons(tmp_path):
    import sqlite3
    from cryptoforge.order_submission_journal import OrderSubmissionJournal
    from cryptoforge.decision_outbox import DecisionOutbox
    from test_order_submission_journal import INTENT, ACK
    from test_order_decision_recovery import original
    project=tmp_path/'project';project.mkdir();state=project/'.local/state'
    journal=OrderSubmissionJournal(state/'live-order-submissions.sqlite')
    box=DecisionOutbox(state/'live-decision-outbox.sqlite')
    # Keep WAL open: a raw main-file copy would not include the new context.
    keeper=sqlite3.connect(journal.path);keeper.execute('PRAGMA journal_mode=WAL')
    try:
        journal.capture_decision_context(INTENT,original())
        journal.prepare(**INTENT);journal.finish(INTENT['order_link_id'],'acknowledged',ACK)
        result=create_backup(project,tmp_path/'backups')
    finally:
        keeper.close()
    assert result.archive_path.stat().st_mode & 0o777 == 0o600
    restore=tmp_path/'restore';restore_backup(result.archive_path,restore,checksum_path=result.checksum_path)
    recovered=OrderSubmissionJournal(restore/'.local/state/live-order-submissions.sqlite')
    restored_box=DecisionOutbox(restore/'.local/state/live-decision-outbox.sqlite')
    assert recovered.recover_decisions(restored_box)==1
    rows=[];from types import SimpleNamespace
    restored_box.flush(SimpleNamespace(upsert=lambda table,batch,**kw:rows.extend(batch)))
    assert rows[0]['reasons']==['stop_loss=True']


def test_queue_snapshot_follows_order_journal_during_concurrent_recovery(tmp_path,monkeypatch):
    import sqlite3
    from cryptoforge.order_submission_journal import OrderSubmissionJournal
    from cryptoforge.decision_outbox import DecisionOutbox
    from test_order_submission_journal import INTENT, ACK
    from test_order_decision_recovery import original
    project=tmp_path/'project';project.mkdir();state=project/'.local/state'
    journal=OrderSubmissionJournal(state/'live-order-submissions.sqlite')
    box=DecisionOutbox(state/'live-decision-outbox.sqlite')
    journal.capture_decision_context(INTENT,original());journal.prepare(**INTENT)
    journal.finish(INTENT['order_link_id'],'acknowledged',ACK)
    original_add=tarfile.TarFile.add;seen=[]
    def add(archive,name,arcname=None,*args,**kwargs):
        original_add(archive,name,arcname,*args,**kwargs)
        if str(arcname).endswith('live-order-submissions.sqlite'):
            seen.append('journal');journal.recover_decisions(box)
        elif str(arcname).endswith('live-decision-outbox.sqlite'):seen.append('outbox')
    monkeypatch.setattr(tarfile.TarFile,'add',add)
    result=create_backup(project,tmp_path/'backups')
    assert seen==['journal','outbox']
    restore=tmp_path/'restore';restore_backup(result.archive_path,restore)
    restored_box=DecisionOutbox(restore/'.local/state/live-decision-outbox.sqlite')
    assert restored_box.pending()==1
