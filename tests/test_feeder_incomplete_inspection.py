import fcntl
from pathlib import Path

import pytest

from cryptoforge.feeder_incomplete_inspection import inspect_incomplete_feeder
from cryptoforge.local_source_provenance import canonical, digest
from test_managed_reference_feeder import ENV, make, route


def incomplete(tmp_path):
    obj, clock = make(tmp_path)
    def fail(*args, **kwargs):raise RuntimeError('unknown child effect')
    with pytest.raises(RuntimeError):obj.run(ENV, route=route, invoke=fail)
    cycle = next((obj.root / 'cycles').iterdir())
    return obj, clock, cycle


def test_unfinished_first_stage_is_unknown_and_read_only(tmp_path):
    obj, clock, cycle = incomplete(tmp_path)
    before = {str(p.relative_to(cycle)):p.read_bytes() for p in cycle.rglob('*') if p.is_file()}
    report = inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
    after = {str(p.relative_to(cycle)):p.read_bytes() for p in cycle.rglob('*') if p.is_file()}
    assert before == after and report['first_missing_stage'] == 'reference_btc'
    assert report['effect'] == 'unknown_stage_effect' and not report['retry_authorized']
    assert not report['current_database_compared'] and not report['stage_output_reverified']


def test_failed_first_reference_does_not_imply_second_never_attempted(tmp_path):
    obj, clock, cycle = incomplete(tmp_path)
    (cycle / 'run/stage-1.json').write_bytes(canonical({'stage':'reference_btc','success':False,'error_type':'RuntimeError'}))
    report = inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
    assert report['first_missing_stage'] == 'reference_eth' and report['effect'] == 'unknown_stage_effect'
    (cycle / 'run/stage-2.json').write_bytes(canonical({'stage':'reference_eth','success':False,'error_type':'RuntimeError'}))
    report = inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
    assert report['first_missing_stage'] == 'select'
    assert report['effect'] == 'not_attempted_under_recorded_stage_control_flow'
    assert not report['retry_authorized']


def test_noncontiguous_or_impossible_stage_history_is_rejected(tmp_path):
    obj, clock, cycle = incomplete(tmp_path)
    (cycle / 'run/stage-2.json').write_bytes(canonical({'stage':'reference_eth','success':False}))
    with pytest.raises(ValueError, match='noncontiguous'):
        inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
    (cycle / 'run/stage-1.json').write_bytes(canonical({'stage':'reference_btc','success':False}))
    (cycle / 'run/stage-3.json').write_bytes(canonical({'stage':'select','success':False}))
    with pytest.raises(ValueError, match='failed prerequisite'):
        inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)


def test_changed_plan_and_completed_cycle_are_rejected(tmp_path):
    obj, clock, cycle = incomplete(tmp_path)
    (cycle / 'run/plan.json').write_bytes(canonical({'unexpected':True}))
    with pytest.raises(ValueError, match='plan'):
        inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
    (cycle / 'complete.json').write_bytes(canonical({}))
    with pytest.raises(ValueError, match='completion'):
        inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)


def test_foreign_identity_alias_and_busy_feeder_cannot_be_inspected(tmp_path):
    obj, clock, cycle = incomplete(tmp_path)
    with pytest.raises(ValueError):
        inspect_incomplete_feeder(dict(obj.reference, manifest_sha256='f'*64), cycle.name, clock=clock)
    with pytest.raises(ValueError):inspect_incomplete_feeder(obj.reference, '../outside', clock=clock)
    with (obj.root / 'writer.lock').open('rb') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)


def test_original_source_integrity_receipt_is_checked(tmp_path, monkeypatch):
    import cryptoforge.feeder_incomplete_inspection as module
    obj, clock, cycle = incomplete(tmp_path)
    facts = {'query': {'pair':'BTC/USDT'}, 'candle_freshness_pass':True, 'records':[{}]*120}
    monkeypatch.setattr(module, 'validate_observation', lambda raw:facts)
    stage = {'stage':'reference_btc','success':True,'exit_code':0,'output_bytes':1,'output_sha256':'a'*64,
             'observation':{'raw_observation':{},'original_integrity_sha256':digest(canonical(facts))}}
    path = cycle / 'run/stage-1.json';path.write_bytes(canonical(stage))
    report = inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
    assert report['recorded_stages'][0]['observation_integrity_pass']
    stage['observation']['original_integrity_sha256'] = 'f'*64;path.write_bytes(canonical(stage))
    with pytest.raises(ValueError, match='observation'):
        inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)


def test_unexpected_extra_stage_cannot_be_ignored(tmp_path):
    obj, clock, cycle = incomplete(tmp_path)
    (cycle / 'run/stage-5.json').write_bytes(canonical({}))
    with pytest.raises(ValueError, match='unexpected stage'):
        inspect_incomplete_feeder(obj.reference, cycle.name, clock=clock)
