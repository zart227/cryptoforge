from datetime import UTC, datetime, timedelta
import json
import sqlite3

import pytest

from cryptoforge.forecast_retention_reader import RehearsalForecastReader
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from test_forecast_retention_rehearsal import setup, run, sha


def reader(data):
    receipt=data[-1]/'output/receipt.json'
    return RehearsalForecastReader(receipt,sha(receipt))


def repin_mutated_active(data):
    output=data[-1]/'output';receipt=output/'receipt.json';r=json.loads(receipt.read_text());active=output/'active.sqlite'
    r['files']['active.sqlite']={'bytes':active.stat().st_size,'sha256':sha(active)}
    with sqlite3.connect(active) as db:
        r['counts']['active']={'forecasts':db.execute('select count(*) from primary_forecasts').fetchone()[0],
                               'outcomes':db.execute('select count(*) from primary_forecast_outcomes').fetchone()[0]}
    receipt.write_text(json.dumps(r))


def test_combined_reader_matches_original_for_all_rows_and_outcomes(setup):
    source=setup[0];run(setup);combined=reader(setup);original=PrimaryForecastMemory(source)
    as_of=datetime.now(UTC)+timedelta(minutes=2)
    assert list(combined.iter_rows())==list(original.iter_rows())
    assert list(combined.iter_labeled_asof(as_of=as_of))==list(original.iter_labeled_asof(as_of=as_of))
    assert combined.rows(limit=2)==original.rows(limit=2)
    assert combined.matured_batch(as_of=as_of,limit=3)==original.matured_batch(as_of=as_of,limit=3)
    for fid in ('a','b','c','d','missing'):
        assert combined.available_outcome(fid,as_of=as_of)==original.available_outcome(fid,as_of=as_of)


def test_late_correction_in_active_is_available_for_archived_forecast(setup):
    source=setup[0];run(setup);active=setup[-1]/'output/active.sqlite'
    new_time=datetime.now(UTC)+timedelta(minutes=3)
    with sqlite3.connect(active) as db:
        db.execute('insert into primary_forecast_outcomes values (?,?,?,?,?)',(5,'a','new',new_time.isoformat(),'{"x":3}'))
    with sqlite3.connect(source) as db:
        db.execute('insert into primary_forecast_outcomes values (?,?,?,?,?)',(5,'a','new',new_time.isoformat(),'{"x":3}'))
    repin_mutated_active(setup); combined=reader(setup);original=PrimaryForecastMemory(source)
    for when in (new_time-timedelta(minutes=1),new_time+timedelta(minutes=1)):
        assert combined.available_outcome('a',as_of=when)==original.available_outcome('a',as_of=when)
        assert list(combined.iter_labeled_asof(as_of=when))==list(original.iter_labeled_asof(as_of=when))
    assert combined.available_outcome('a',as_of=new_time)=={'x':3}


def test_colliding_outcome_ids_are_rejected_even_when_files_are_repinned(setup):
    run(setup);active=setup[-1]/'output/active.sqlite'
    with sqlite3.connect(active) as db:
        db.execute('insert into primary_forecast_outcomes values (?,?,?,?,?)',(1,'b','bad',datetime.now(UTC).isoformat(),'{}'))
    repin_mutated_active(setup)
    with pytest.raises(ValueError,match='overlapping outcome ids'):list(reader(setup).iter_rows())


def test_colliding_forecast_ids_and_orphan_outcomes_rejected(setup):
    run(setup);active=setup[-1]/'output/active.sqlite'
    with sqlite3.connect(active) as db:db.execute('insert into primary_forecasts values (?,?)',('a','{}'))
    repin_mutated_active(setup)
    with pytest.raises(ValueError,match='overlapping forecast ids'):list(reader(setup).iter_rows())
    with sqlite3.connect(active) as db:
        db.execute("delete from primary_forecasts where id='a'")
        db.execute('insert into primary_forecast_outcomes values (?,?,?,?,?)',(5,'missing','bad',datetime.now(UTC).isoformat(),'{}'))
    repin_mutated_active(setup)
    with pytest.raises(ValueError,match='orphan outcome'):list(reader(setup).iter_rows())


def test_mutated_file_and_wrong_receipt_pin_are_rejected(setup):
    run(setup);combined=reader(setup);active=setup[-1]/'output/active.sqlite'
    with sqlite3.connect(active) as db:db.execute("update primary_forecasts set payload='{}' where id='b'")
    with pytest.raises(ValueError,match='file mismatch'):list(combined.iter_rows())
    with pytest.raises(ValueError,match='receipt hash'):
        list(RehearsalForecastReader(setup[-1]/'output/receipt.json','0'*64).iter_rows())


def test_naive_cutoff_is_rejected(setup):
    run(setup);combined=reader(setup)
    with pytest.raises(ValueError,match='aware'):combined.available_outcome('a',as_of=datetime(2026,1,1))
    with pytest.raises(ValueError,match='aware'):list(combined.iter_labeled_asof(as_of=datetime(2026,1,1)))
    with pytest.raises(ValueError,match='aware'):combined.matured_batch(as_of=datetime(2026,1,1))
    with pytest.raises(ValueError,match='positive'):combined.rows(limit=0)


def test_changed_input_during_iteration_is_detected_on_close(setup):
    run(setup); combined=reader(setup);rows=combined.iter_rows()
    next(rows)
    with (setup[-1]/'output/active.sqlite').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='changed during read'):rows.close()


def test_sidecar_is_rejected(setup):
    run(setup);active=setup[-1]/'output/active.sqlite'
    active.with_name(active.name+'-wal').write_bytes(b'')
    with pytest.raises(ValueError,match='sidecars'):list(reader(setup).iter_rows())
