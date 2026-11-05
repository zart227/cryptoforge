from datetime import UTC, datetime, timedelta
import hashlib
import json
import sqlite3

import pytest

from cryptoforge.forecast_memory_snapshot import create_forecast_snapshot
from cryptoforge.forecast_retention_preflight import assess_retention
from cryptoforge.forecast_retention_rehearsal import rehearse_split


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def setup(tmp_path, tmp_path_factory):
    source = tmp_path/'source.sqlite';now=datetime.now(UTC)+timedelta(minutes=1)
    old=now-timedelta(days=7); cutoff=now-timedelta(hours=36)
    payload=lambda time: json.dumps({'predicted_at':time.isoformat(),'target_information_end':time.isoformat()})
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE primary_forecasts (id TEXT PRIMARY KEY,payload TEXT) WITHOUT ROWID')
        db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        db.execute('CREATE INDEX primary_forecast_outcome_lookup ON primary_forecast_outcomes(forecast,id)')
        db.executemany('INSERT INTO primary_forecasts VALUES (?,?)', [('a',payload(old)),('b',payload(old)),('c',payload(old)),('d',payload(now))])
        db.executemany('INSERT INTO primary_forecast_outcomes VALUES (?,?,?,?,?)',[(1,'a','x',old.isoformat(),'{"x":1}'),(2,'a','y',old.isoformat(),'{"x":2}'),(3,'c','z',now.isoformat(),'{}'),(4,'d','z',now.isoformat(),'{}')])
    create_forecast_snapshot(source,tmp_path/'snapshot',minimum_free_bytes=0)
    manifest=tmp_path/'snapshot/manifest.json';pin=sha(manifest)
    preflight=assess_retention(manifest,pin,as_of=now.isoformat(),cutoff=cutoff.isoformat())
    receipt=tmp_path/'preflight.json';receipt.write_text(json.dumps(preflight))
    work=tmp_path_factory.mktemp('separate-split-work')
    return source,manifest,pin,receipt,sha(receipt),work


def run(data, **kwargs):
    _,manifest,pin,receipt,rpin,work=data
    return rehearse_split(manifest,pin,receipt,rpin,work/'output',minimum_free_bytes=0,**kwargs)


def test_isolated_split_preserves_rows_versions_and_sources(setup):
    source,manifest,_,receipt,_,work=setup
    before={p:sha(p) for p in (source,manifest,receipt,manifest.parent/'forecast-snapshot.sqlite')}
    result=run(setup)
    assert result['counts'] == {'archive':{'forecasts':1,'outcomes':2},'active':{'forecasts':3,'outcomes':2}}
    assert result['integrity_check']=='ok' and not result['actual_recording_restored']
    assert all(sha(path)==digest for path,digest in before.items())
    with sqlite3.connect(work/'output/archive.sqlite') as db:
        assert db.execute('select id,forecast,payload from primary_forecast_outcomes order by id').fetchall()==[(1,'a','{"x":1}'),(2,'a','{"x":2}')]
    with sqlite3.connect(work/'output/active.sqlite') as db:
        assert db.execute('select id from primary_forecasts order by id').fetchall()==[('b',),('c',),('d',)]
    assert (work/'output/receipt.json').exists()


def test_existing_output_and_bad_pin_never_overwrite(setup):
    _,manifest,pin,receipt,rpin,work=setup
    output=work/'output';output.mkdir();marker=output/'marker';marker.write_text('keep')
    with pytest.raises(ValueError,match='new separate'):run(setup)
    assert marker.read_text()=='keep' and not (output/'receipt.json').exists()
    with pytest.raises(ValueError,match='pinned preflight'):
        rehearse_split(manifest,pin,receipt,'0'*64,work/'new',minimum_free_bytes=0)
    assert not (work/'new').exists()


def test_tampered_preflight_with_new_hash_is_rejected(setup):
    _,manifest,pin,receipt,_,work=setup
    report=json.loads(receipt.read_text());report['buckets']['protected']['forecasts']+=1
    receipt.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='does not match'):
        rehearse_split(manifest,pin,receipt,sha(receipt),work/'output',minimum_free_bytes=0)
    assert not (work/'output').exists()


def test_resource_limits_leave_no_output(setup):
    _,manifest,pin,receipt,rpin,work=setup
    with pytest.raises(ValueError,match='disk reserve'):
        rehearse_split(manifest,pin,receipt,rpin,work/'output',minimum_free_bytes=10**18)
    with pytest.raises(ValueError,match='row limit'):run(setup,maximum_rows=1)
    assert not (work/'output').exists()


def test_rejects_output_inside_source_or_snapshot(setup):
    source,manifest,pin,receipt,rpin,_=setup
    for output in (source.parent/'bad',manifest.parent/'bad'):
        with pytest.raises(ValueError,match='separate'):
            rehearse_split(manifest,pin,receipt,rpin,output,minimum_free_bytes=0)
        assert not output.exists()


def test_interrupted_copy_keeps_partial_without_receipt(setup,monkeypatch):
    import cryptoforge.forecast_retention_rehearsal as module
    def fail(*args,**kwargs):raise TimeoutError('simulated verification interruption')
    monkeypatch.setattr(module,'_typed_digest',fail)
    with pytest.raises(TimeoutError):run(setup)
    output=setup[-1]/'output'
    assert (output/'archive.sqlite').exists() and not (output/'receipt.json').exists()
    with pytest.raises(ValueError,match='new separate'):run(setup)


def test_new_active_outcome_can_collide_with_archive_id(setup):
    run(setup)
    archive = setup[-1]/'output/archive.sqlite'
    with sqlite3.connect(f'file:{archive}?mode=ro', uri=True) as db:
        archived_id = db.execute('select min(id) from primary_forecast_outcomes').fetchone()[0]
    # Demonstrate default SQLite allocation without changing either rehearsal file.
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE primary_forecast_outcomes (id INTEGER PRIMARY KEY,forecast TEXT,digest TEXT,observed_at TEXT,payload TEXT)')
        new_id = db.execute('INSERT INTO primary_forecast_outcomes (forecast,digest,observed_at,payload) VALUES (?,?,?,?)',('b','d','time','{}')).lastrowid
    assert new_id == archived_id == 1
