from datetime import UTC,datetime,timedelta
import json
import sqlite3
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from cryptoforge.forecast_memory_health import inspect_forecast_health

NOW = datetime(2026,10,28,12,tzinfo=UTC)


def database(path):
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        values = [('recent', NOW-timedelta(hours=1)), ('old', NOW-timedelta(hours=40)),
                  ('resolved', NOW-timedelta(hours=2)), ('future', NOW+timedelta(hours=1))]
        for name, end in values:
            db.execute('INSERT INTO primary_forecasts VALUES (?,?)', (name,json.dumps({
                'predicted_at':(end-timedelta(minutes=15)).isoformat(), 'target_information_end':end.isoformat()})))
        db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        db.execute('CREATE INDEX primary_forecast_outcome_lookup ON primary_forecast_outcomes(forecast,id)')
        db.executemany('INSERT INTO primary_forecast_outcomes (forecast,observed_at) VALUES (?,?)',
            [('resolved',NOW.isoformat()),('resolved',(NOW+timedelta(seconds=1)).isoformat())])


def test_independent_storage_and_maturity_health_reports_without_writes(tmp_path):
    path=tmp_path/'memory.sqlite';database(path);before=path.read_bytes()
    value=inspect_forecast_health(path,now=NOW,maximum_database_bytes=path.stat().st_size,minimum_free_bytes=0)
    assert value['recording_capacity_blocked'] and value['capacity_blockers']==['database_budget_reached']
    assert value['total_forecasts']==4 and value['total_outcome_versions']==2
    assert value['pending_last_36_hours']==1 and value['older_unresolved_matured_forecasts']==1
    assert value['forecasts_with_future_prediction_time']==1
    assert value['database_bytes']==len(before) and path.read_bytes()==before
    assert not value['future_cash_labels_created'] and not value['live_promotion_allowed']


def test_missing_file_and_low_disk_are_distinct(tmp_path,monkeypatch):
    monkeypatch.setattr('cryptoforge.forecast_memory_health.shutil.disk_usage',lambda _:SimpleNamespace(free=0))
    path=tmp_path/'memory.sqlite';result=inspect_forecast_health(path,now=NOW,minimum_free_bytes=1)
    assert not result['database_exists'] and result['capacity_blockers']==['disk_reserve_preserved']
    assert not path.exists()


def test_outcome_table_not_yet_created_still_counts_pending(tmp_path):
    path=tmp_path/'memory.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.execute('INSERT INTO primary_forecasts VALUES (?,?)',('x',json.dumps({'target_information_end':NOW.isoformat()})))
    result=inspect_forecast_health(path,now=NOW,minimum_free_bytes=0)
    assert result['pending_last_36_hours']==1 and result['total_outcome_versions']==0


def test_unrelated_database_or_alias_is_rejected(tmp_path):
    path=tmp_path/'memory.sqlite';database(path)
    with sqlite3.connect(path) as db:db.execute('CREATE TABLE other(id INTEGER)')
    with pytest.raises(ValueError,match='isolated'):inspect_forecast_health(path,now=NOW,minimum_free_bytes=0)
    alias=tmp_path/'alias';alias.symlink_to(path)
    with pytest.raises(ValueError,match='canonical'):inspect_forecast_health(alias,now=NOW,minimum_free_bytes=0)


def test_invalid_limit_or_naive_time_cannot_be_used(tmp_path):
    with pytest.raises(ValueError):inspect_forecast_health(tmp_path/'file',now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):inspect_forecast_health(tmp_path/'file',now=NOW,maximum_database_bytes=True)


def test_future_outcome_does_not_resolve_a_forecast_as_of_now(tmp_path):
    path=tmp_path/'memory.sqlite';database(path)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO primary_forecast_outcomes (forecast,observed_at) VALUES (?,?)',
                   ('recent',(NOW+timedelta(seconds=1)).isoformat()))
    value=inspect_forecast_health(path,now=NOW,minimum_free_bytes=0)
    assert value['pending_last_36_hours']==1


def test_not_yet_mature_distinguishes_waiting_from_missing_outcomes(tmp_path):
    path=tmp_path/'memory.sqlite';database(path)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO primary_forecasts VALUES (?,?)',('awaiting',json.dumps({
            'predicted_at':(NOW-timedelta(minutes=1)).isoformat(),
            'target_information_end':(NOW+timedelta(minutes=10)).isoformat()})))
    result=inspect_forecast_health(path,now=NOW,minimum_free_bytes=0)
    assert result['forecasts_not_yet_mature']==1
    assert result['pending_last_36_hours']==1


def test_cli_reads_only_configured_capacity_and_uses_file_precedence(tmp_path):
    path=tmp_path/'memory.sqlite';database(path)
    env_file=tmp_path/'settings';env_file.write_text('SECRET=do-not-print\nCRYPTOFORGE_PRIMARY_FORECAST_MAXIMUM_MB="512"\n')
    script=Path(__file__).resolve().parents[1]/'scripts/inspect_primary_forecast_health.py'
    env={**os.environ,'CRYPTOFORGE_PRIMARY_FORECAST_MAXIMUM_MB':'256'}
    result=subprocess.run([sys.executable,str(script),'--path',str(path),'--env-file',str(env_file)],env=env,capture_output=True,text=True,check=True)
    value=json.loads(result.stdout)
    assert value['maximum_database_bytes']==512*1024**2
    assert value['capacity_configuration_source']=='env_file_with_environment_fallback'
    assert 'do-not-print' not in result.stdout+result.stderr
    env_file.write_text('CRYPTOFORGE_PRIMARY_FORECAST_MAXIMUM_MB=invalid\n')
    assert subprocess.run([sys.executable,str(script),'--path',str(path),'--env-file',str(env_file)],env=env,capture_output=True).returncode != 0
