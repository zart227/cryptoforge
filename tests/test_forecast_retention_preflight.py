from datetime import UTC, datetime, timedelta
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from cryptoforge.forecast_memory_snapshot import create_forecast_snapshot
from cryptoforge.forecast_retention_preflight import assess_retention


@pytest.fixture
def ledger(tmp_path):
    now = datetime.now(UTC) + timedelta(minutes=1)
    cutoff = now - timedelta(hours=36)
    old = cutoff - timedelta(days=2)
    source = tmp_path / 'source.sqlite'
    def forecast(predicted, target):
        return json.dumps({'predicted_at': predicted, 'target_information_end': target})
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        db.execute('CREATE INDEX primary_forecast_outcome_lookup ON primary_forecast_outcomes(forecast,id)')
        valid = forecast(old.isoformat(), (old + timedelta(hours=1)).isoformat())
        db.executemany('INSERT INTO primary_forecasts VALUES (?,?)', [
            ('archive', valid), ('unresolved', valid), ('corrected', valid), ('future', valid),
            ('recent', forecast(cutoff.isoformat(), (cutoff + timedelta(hours=1)).isoformat())),
            ('missing', '{}'), ('duplicate', '{"predicted_at":"a","predicted_at":"b"}'),
            ('end_future', forecast(old.isoformat(), (now + timedelta(hours=1)).isoformat())),
        ])
        db.executemany('INSERT INTO primary_forecast_outcomes VALUES (?,?,?,?,?)', [
            (1, 'archive', '1', (old + timedelta(hours=2)).isoformat(), '{}'),
            (2, 'archive', '2', (old + timedelta(hours=3)).isoformat(), '{}'),
            (3, 'corrected', '3', (old + timedelta(hours=2)).isoformat(), '{}'),
            (4, 'corrected', '4', cutoff.isoformat(), '{}'),
            (5, 'future', '5', (now + timedelta(hours=1)).isoformat(), '{}'),
            (6, 'recent', '6', now.isoformat(), '{}'),
            (7, 'missing', '7', old.isoformat(), '{}'),
            (8, 'duplicate', '8', old.isoformat(), '{}'),
            (9, 'end_future', '9', old.isoformat(), '{}'),
        ])
    before = source.read_bytes()
    result = create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    manifest = tmp_path / 'snapshot/manifest.json'
    pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
    return source, before, manifest, pin, now.isoformat(), cutoff.isoformat(), result


def call(ledger, **kwargs):
    _, _, manifest, pin, now, cutoff, _ = ledger
    return assess_retention(manifest, pin, as_of=now, cutoff=cutoff, **kwargs)


def test_conservative_classification_preserves_all_versions_and_source(ledger):
    source, before, manifest, _, _, _, result = ledger
    snapshot = manifest.parent / 'forecast-snapshot.sqlite'; snapshot_before = snapshot.read_bytes()
    report = call(ledger)
    assert report['source_counts'] == {'forecasts': 8, 'outcomes': 9}
    assert report['buckets']['archive_candidates']['forecasts'] == 1
    assert report['buckets']['archive_candidates']['outcome_versions'] == 2
    assert report['buckets']['protected']['forecasts'] == 7
    assert report['buckets']['protected']['outcome_versions'] == 7
    assert report['protected_reasons_first_match'] == {
        'recent_outcome_version': 1, 'invalid_or_future_forecast_time': 3,
        'invalid_or_future_outcome_time': 1, 'recent_forecast': 1, 'unresolved': 1}
    assert not report['split_readiness'] and not report['data_deleted']
    assert source.read_bytes() == before and snapshot.read_bytes() == snapshot_before
    assert result['snapshot_sha256'] == report['snapshot_sha256']


def test_manifest_or_snapshot_tamper_and_sidecars_rejected(ledger):
    _, _, manifest, _, _, _, _ = ledger
    snapshot = manifest.parent / 'forecast-snapshot.sqlite'
    sidecar = snapshot.parent / (snapshot.name + '-wal'); sidecar.write_text('')
    with pytest.raises(ValueError, match='sidecars'):call(ledger)
    sidecar.unlink()
    manifest.write_bytes(manifest.read_bytes() + b' ')
    with pytest.raises(ValueError, match='manifest hash'):call(ledger)


def test_mutated_snapshot_is_rejected(ledger):
    _, _, manifest, _, _, _, _ = ledger
    snapshot = manifest.parent / 'forecast-snapshot.sqlite'
    with snapshot.open('ab') as stream:stream.write(b'altered')
    with pytest.raises(ValueError, match='size mismatch'):call(ledger)


def test_too_recent_cutoff_naive_timestamps_and_row_limit_fail(ledger):
    _, _, manifest, pin, now, _, _ = ledger
    with pytest.raises(ValueError, match='36 hours'):
        assess_retention(manifest, pin, as_of=now, cutoff=now)
    with pytest.raises(ValueError, match='aware'):
        assess_retention(manifest, pin, as_of='2030-01-01T00:00:00', cutoff='2029-01-01T00:00:00+00:00')
    with pytest.raises(ValueError, match='row limit'):call(ledger, maximum_rows=1)


def test_orphan_blocks_all_archive_candidates(tmp_path):
    source = tmp_path / 'source.sqlite'
    now = datetime.now(UTC) + timedelta(minutes=1); old = now - timedelta(days=7)
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        db.execute('INSERT INTO primary_forecasts VALUES (?,?)', ('a', json.dumps({'predicted_at':old.isoformat(),'target_information_end':old.isoformat()})))
        db.executemany('INSERT INTO primary_forecast_outcomes VALUES (?,?,?,?,?)', [(1,'a','d',old.isoformat(),'{}'),(2,'missing','e',old.isoformat(),'{}')])
    create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    manifest = tmp_path / 'snapshot/manifest.json'
    report = assess_retention(manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), as_of=now.isoformat(), cutoff=(now-timedelta(hours=36)).isoformat())
    assert report['orphan_outcomes'] == 1 and report['buckets']['archive_candidates']['forecasts'] == 0
    assert report['protected_reasons_first_match'] == {'orphan_outcomes_block_split': 1}


def test_forecast_only_snapshot_protects_unresolved(tmp_path):
    source = tmp_path / 'source.sqlite'; now = datetime.now(UTC) + timedelta(minutes=1); old = now - timedelta(days=7)
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.execute('INSERT INTO primary_forecasts VALUES (?,?)', ('a', json.dumps({'predicted_at':old.isoformat(),'target_information_end':old.isoformat()})))
    create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    manifest = tmp_path / 'snapshot/manifest.json'
    report = assess_retention(manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), as_of=now.isoformat(), cutoff=(now-timedelta(hours=36)).isoformat())
    assert report['protected_reasons_first_match'] == {'unresolved': 1}
    assert report['buckets']['protected']['outcome_versions'] == 0


def test_manifest_alias_and_as_of_before_snapshot_rejected(ledger, tmp_path):
    _, _, manifest, pin, now, cutoff, _ = ledger
    alias = tmp_path / 'manifest.json'; alias.symlink_to(manifest)
    with pytest.raises(ValueError, match='canonical'):assess_retention(alias, pin, as_of=now, cutoff=cutoff)
    with pytest.raises(ValueError, match='observation time'):
        assess_retention(manifest, pin, as_of='2020-01-01T00:00:00+00:00', cutoff='2019-01-01T00:00:00+00:00')


def test_outcome_before_target_is_protected(tmp_path):
    source = tmp_path / 'source.sqlite'; now = datetime.now(UTC) + timedelta(minutes=1); old = now - timedelta(days=7)
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        db.execute('INSERT INTO primary_forecasts VALUES (?,?)', ('a', json.dumps({'predicted_at':old.isoformat(),'target_information_end':(old+timedelta(hours=1)).isoformat()})))
        db.execute('INSERT INTO primary_forecast_outcomes VALUES (?,?,?,?,?)', (1,'a','d',old.isoformat(),'{}'))
    create_forecast_snapshot(source, tmp_path / 'snapshot', minimum_free_bytes=0)
    manifest = tmp_path / 'snapshot/manifest.json'
    report = assess_retention(manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), as_of=now.isoformat(), cutoff=(now-timedelta(hours=36)).isoformat())
    assert report['protected_reasons_first_match'] == {'invalid_or_future_outcome_time': 1}


def test_receipt_is_created_once_in_separate_directory(ledger, tmp_path):
    _, _, manifest, pin, now, cutoff, _ = ledger
    directory = tmp_path / 'receipts'; directory.mkdir()
    script = Path(__file__).resolve().parents[1] / 'scripts/preflight_forecast_retention.py'
    base = [sys.executable, str(script), '--manifest', str(manifest), '--manifest-sha256', pin,
            '--as-of', now, '--cutoff', cutoff, '--output']
    output = directory / 'receipt.json'
    subprocess.run(base + [str(output)], check=True, capture_output=True)
    before = output.read_bytes()
    assert subprocess.run(base + [str(output)], capture_output=True).returncode != 0
    assert output.read_bytes() == before
    forbidden = manifest.parent / 'receipt.json'
    assert subprocess.run(base + [str(forbidden)], capture_output=True).returncode != 0
    assert not forbidden.exists()
