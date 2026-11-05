import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from cryptoforge.forecast_memory_snapshot import create_forecast_snapshot


def database(path, *, outcomes=True):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.executemany('INSERT INTO primary_forecasts VALUES (?,?)', [('a', '{"value":1}'), ('b', '{"value":2}')])
        if outcomes:
            db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
            db.execute('CREATE INDEX primary_forecast_outcome_lookup ON primary_forecast_outcomes(forecast,id)')
            db.executemany('INSERT INTO primary_forecast_outcomes VALUES (?,?,?,?,?)', [
                (1, 'a', 'one', '2026-10-01', '{"label":1}'),
                (2, 'a', 'two', '2026-10-02', '{"label":0}'),
                (3, 'missing', 'three', '2026-10-03', '{}')])


def test_snapshot_keeps_all_rows_and_versions_without_changing_original(tmp_path):
    source = tmp_path / 'memory.sqlite'; database(source)
    before = source.read_bytes(); result = create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    target = Path(result['snapshot'])
    assert source.read_bytes() == before and target.stat().st_mode & 0o777 == 0o600
    assert result['snapshot_sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert result['integrity_check'] == 'ok' and result['snapshot_counts_match_source_transaction']
    assert result['source_transaction_counts'] == {'forecasts': 2, 'outcomes': 3}
    assert result['forecast_rows']['rows'] == 2 and result['outcome_rows']['rows'] == 3
    assert result['orphan_outcomes'] == 1 and not result['writers_redirected']
    assert json.loads((target.parent / 'manifest.json').read_text()) == result
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT id,forecast,payload FROM primary_forecast_outcomes ORDER BY id').fetchall() == [
            (1, 'a', '{"label":1}'), (2, 'a', '{"label":0}'), (3, 'missing', '{}')]


def test_existing_forecast_reader_can_read_restored_independent_copy(tmp_path):
    from datetime import datetime, UTC
    import shutil
    from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
    source = tmp_path / 'memory.sqlite';database(source)
    result = create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    restored = tmp_path / 'restored.sqlite';shutil.copyfile(result['snapshot'], restored)
    memory = PrimaryForecastMemory(restored)
    assert [row['forecast_id'] for row in memory.iter_rows()] == ['a', 'b']
    assert memory.available_outcome('a', as_of=datetime(2026, 10, 2, tzinfo=UTC)) == {'label': 0}


def test_forecast_only_database_is_valid(tmp_path):
    source = tmp_path / 'memory.sqlite'; database(source, outcomes=False)
    result = create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    assert result['outcome_rows']['rows'] == 0 and result['orphan_outcomes'] == 0


def test_repeat_and_source_alias_are_rejected_without_replacing_snapshot(tmp_path):
    source = tmp_path / 'memory.sqlite'; database(source)
    output = tmp_path / 'snapshot'; create_forecast_snapshot(source, output, minimum_free_bytes=0)
    before = (output / 'manifest.json').read_bytes()
    with pytest.raises(ValueError):create_forecast_snapshot(source, output, minimum_free_bytes=0)
    alias = tmp_path / 'alias.sqlite'; alias.symlink_to(source)
    with pytest.raises(ValueError):create_forecast_snapshot(alias, tmp_path / 'other', minimum_free_bytes=0)
    assert (output / 'manifest.json').read_bytes() == before and not (tmp_path / 'other').exists()


def test_disk_and_byte_limits_stop_before_creating_output(tmp_path):
    source = tmp_path / 'memory.sqlite'; database(source)
    with pytest.raises(ValueError, match='disk reserve'):
        create_forecast_snapshot(source, tmp_path / 'space', minimum_free_bytes=10**18)
    with pytest.raises(ValueError, match='byte limit'):
        create_forecast_snapshot(source, tmp_path / 'size', maximum_source_bytes=1)
    assert not (tmp_path / 'space').exists() and not (tmp_path / 'size').exists()


def test_unexpected_schema_fails_without_touching_original(tmp_path):
    source = tmp_path / 'memory.sqlite'; database(source)
    with sqlite3.connect(source) as db:db.execute('CREATE TABLE other(secret TEXT)')
    before = source.read_bytes()
    with pytest.raises(ValueError, match='isolated forecast tables'):
        create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    assert source.read_bytes() == before and not (tmp_path / 'snapshot/manifest.json').exists()


def test_wal_uncheckpointed_records_are_present_in_consistent_snapshot(tmp_path):
    source = tmp_path / 'memory.sqlite'; database(source)
    with sqlite3.connect(source) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('INSERT INTO primary_forecasts VALUES (?,?)', ('c', '{"new":true}'));writer.commit()
        result = create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
        assert result['source_transaction']['journal_mode'] == 'wal'
        assert result['source_transaction_counts']['forecasts'] == 3
        with sqlite3.connect(result['snapshot']) as snapshot:
            assert snapshot.execute("SELECT payload FROM primary_forecasts WHERE id='c'").fetchone() == ('{"new":true}',)


def test_concurrent_wal_writer_does_not_mix_old_and_new_snapshot_rows(tmp_path, monkeypatch):
    import threading
    import cryptoforge.forecast_memory_snapshot as module
    source = tmp_path / 'memory.sqlite'; database(source)
    with sqlite3.connect(source) as setup:
        assert setup.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    ready = threading.Event(); done = threading.Event(); errors = []
    def write_concurrently():
        try:
            assert ready.wait(5)
            with sqlite3.connect(source, timeout=2) as db:
                db.execute("UPDATE primary_forecasts SET payload='changed' WHERE id='a'")
                db.execute("INSERT INTO primary_forecasts VALUES ('c','new')")
                db.commit()
        except BaseException as exc:errors.append(exc)
        finally:done.set()
    worker = threading.Thread(target=write_concurrently);worker.start()
    original = module._count; first = True
    def during_source_transaction(db, tables):
        nonlocal first
        value = original(db, tables)
        if first:
            first = False;ready.set();assert done.wait(5)
        return value
    monkeypatch.setattr(module, '_count', during_source_transaction)
    try:
        result = create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    finally:
        ready.set();worker.join(timeout=5)
    assert not worker.is_alive() and not errors
    assert result['source_transaction_counts']['forecasts'] == 2
    with sqlite3.connect(result['snapshot']) as snapshot:
        assert snapshot.execute('SELECT id,payload FROM primary_forecasts ORDER BY id').fetchall() == [
            ('a', '{"value":1}'), ('b', '{"value":2}')]
    with sqlite3.connect(source) as actual:
        assert actual.execute('SELECT count(*) FROM primary_forecasts').fetchone()[0] == 3
