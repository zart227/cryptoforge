import gzip

from cryptoforge.disk_policy import (
    CleanupTarget,
    DataClass,
    DiskStatus,
    cleanup_safe_targets,
    classify_disk_usage,
    rotate_log_file,
)


def test_disk_thresholds_match_plan() -> None:
    normal = classify_disk_usage(69.9)
    warning = classify_disk_usage(70.0)
    cleanup = classify_disk_usage(80.0)
    critical = classify_disk_usage(90.0)

    assert normal.status == DiskStatus.NORMAL
    assert normal.allow_research
    assert warning.status == DiskStatus.WARNING
    assert warning.allow_research
    assert cleanup.status == DiskStatus.CLEANUP
    assert not cleanup.allow_research
    assert cleanup.should_cleanup_safe_data
    assert critical.status == DiskStatus.CRITICAL
    assert not critical.allow_research
    assert critical.should_emit_critical


def test_cleanup_removes_only_temporary_and_reproducible_data(tmp_path) -> None:
    critical = tmp_path / "outbox.sqlite3"
    reproducible = tmp_path / "candles"
    temporary = tmp_path / "debug"
    critical.write_text("must stay", encoding="utf-8")
    reproducible.mkdir()
    (reproducible / "BTC.feather").write_bytes(b"candle-cache")
    temporary.mkdir()
    (temporary / "failed.log").write_text("temporary", encoding="utf-8")

    result = cleanup_safe_targets(
        [
            CleanupTarget(critical, DataClass.CRITICAL),
            CleanupTarget(reproducible, DataClass.REPRODUCIBLE),
            CleanupTarget(temporary, DataClass.TEMPORARY),
        ]
    )

    assert critical.exists()
    assert not reproducible.exists()
    assert not temporary.exists()
    assert result.skipped_critical_paths == (critical,)
    assert set(result.removed_paths) == {reproducible, temporary}
    assert result.freed_bytes > 0


def test_log_rotation_compresses_and_keeps_bounded_history(tmp_path) -> None:
    log = tmp_path / "freqtrade-service.log"
    log.write_text("a" * 128, encoding="utf-8")

    assert rotate_log_file(log, max_bytes=64, keep=2, compress=True)
    log.write_text("b" * 128, encoding="utf-8")
    assert rotate_log_file(log, max_bytes=64, keep=2, compress=True)
    log.write_text("c" * 128, encoding="utf-8")
    assert rotate_log_file(log, max_bytes=64, keep=2, compress=True)

    assert log.exists()
    assert (tmp_path / "freqtrade-service.log.1.gz").exists()
    assert (tmp_path / "freqtrade-service.log.2.gz").exists()
    assert not (tmp_path / "freqtrade-service.log.3.gz").exists()

    with gzip.open(tmp_path / "freqtrade-service.log.1.gz", "rt", encoding="utf-8") as handle:
        assert handle.read() == "c" * 128


def test_small_log_is_not_rotated(tmp_path) -> None:
    log = tmp_path / "freqtrade-service.log"
    log.write_text("small", encoding="utf-8")

    assert not rotate_log_file(log, max_bytes=64, keep=2)
    assert log.read_text(encoding="utf-8") == "small"
