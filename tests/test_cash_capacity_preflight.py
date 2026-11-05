from datetime import timedelta
import json
from pathlib import Path
import sqlite3

import pytest

from cryptoforge.cash_capacity_preflight import capacity_preflight
from cryptoforge.local_source_provenance import stamp
from test_paired_cash_rehearsal import setup


def test_original_short_profile_has_sufficient_count_caps_but_no_execution_admission(tmp_path):
    runner,clock=setup(tmp_path)
    result=capacity_preflight(runner.reference,free_disk_bytes=20*1024**3)
    assert result['count_and_budget_capacity_pass'] is True and result['blockers']==[]
    assert result['ticks_by_role']==dict(candidate=4,control=4,stress=4)
    assert result['source_polls']==1 and result['source_events']==4 and result['journal_records']==40
    assert result['metadata_only'] and result['outcome_stores_read'] is False
    assert result['execution_ready'] is False and result['observed_memory_or_io_capacity_inferred'] is False


def test_thirty_days_cannot_be_enabled_by_only_lowering_memory_floor(tmp_path):
    runner,clock=setup(tmp_path);start=stamp(runner.manifest['start']);end=start+timedelta(days=30)
    result=capacity_preflight(runner.reference,requested_start=start,requested_end=end,free_disk_bytes=100*1024**3)
    assert result['ticks_by_role']==dict(candidate=518400,control=518400,stress=518400)
    assert result['source_polls']==8641 and result['minimum_versions_without_revisions']==17520
    assert result['maximum_versions_if_every_row_revised']==2073840
    assert result['count_and_budget_capacity_pass'] is False and result['hypothetical_new_window']
    blocked={r['metric'] for r in result['blockers']}
    assert {'application_groups','v1_application_schema_hard_group_limit','capture_events_envelope',
        'minimum_native_marks_and_worker_reports','journal_records','whole_poll_batches'}<=blocked
    assert result['existing_limits_relaxed'] is False and result['new_registration_required']


def test_source_slots_use_exact_utc_end_exclusion_at_boundary(tmp_path):
    runner,clock=setup(tmp_path);start=stamp('2026-11-01T00:00:00Z')
    result=capacity_preflight(runner.reference,requested_start=start,requested_end=start+timedelta(minutes=5),free_disk_bytes=20*1024**3)
    assert result['source_polls']==1 and result['source_events']==4
    result=capacity_preflight(runner.reference,requested_start=start,requested_end=start+timedelta(minutes=5,microseconds=1),free_disk_bytes=20*1024**3)
    assert result['source_polls']==2


def test_metadata_preflight_never_opens_sqlite_outcomes_or_worker_groups(tmp_path,monkeypatch):
    runner,clock=setup(tmp_path);opened=[];original=Path.open
    def guard(path,*a,**k):
        assert path.suffix!='.sqlite' and path.name!='sealed.json' and 'groups' not in path.parts
        opened.append(str(path));return original(path,*a,**k)
    monkeypatch.setattr(Path,'open',guard)
    def forbidden(*a,**k):pytest.fail('capacity must not connect to outcome databases')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    result=capacity_preflight(runner.reference,free_disk_bytes=20*1024**3)
    assert result['metadata_only'] and opened


def test_changed_worker_protocol_cannot_supply_arbitrary_capacity_caps(tmp_path):
    runner,clock=setup(tmp_path);root=Path(runner.manifest['workers']['candidate']['root'])
    protocol=root/'protocol.json';value=json.loads(protocol.read_text());value['storage_policy']['maximum_events']=1000000
    protocol.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='metadata pin'):capacity_preflight(runner.reference)


@pytest.mark.parametrize('fault',['one_bound','reverse','too_long','disk_boolean','disk_negative'])
def test_invalid_capacity_requests_are_rejected(tmp_path,fault):
    runner,clock=setup(tmp_path);start=stamp(runner.manifest['start']);kwargs={}
    if fault=='one_bound':kwargs['requested_start']=start
    if fault=='reverse':kwargs.update(requested_start=start,requested_end=start-timedelta(seconds=1))
    if fault=='too_long':kwargs.update(requested_start=start,requested_end=start+timedelta(days=367))
    if fault=='disk_boolean':kwargs['free_disk_bytes']=True
    if fault=='disk_negative':kwargs['free_disk_bytes']=-1
    with pytest.raises(ValueError):capacity_preflight(runner.reference,**kwargs)


def test_disk_capacity_failure_is_explicit_and_does_not_mutate_registry(tmp_path):
    from test_cash_ack_recovery import inventory
    runner,clock=setup(tmp_path);before=inventory(runner.root)
    result=capacity_preflight(runner.reference,free_disk_bytes=0)
    assert result['count_and_budget_capacity_pass'] is False
    assert any(v['component']=='host' for v in result['blockers'])
    assert inventory(runner.root)==before


def test_cli_can_fail_closed_for_a_long_horizon_without_launching_anything(tmp_path):
    import subprocess,sys
    runner,clock=setup(tmp_path);reference=tmp_path/'reference.json';reference.write_text(json.dumps(runner.reference))
    start=stamp(runner.manifest['start']);output=tmp_path/'capacity.json'
    result=subprocess.run([sys.executable,'scripts/check_cash_capacity.py','--reference',str(reference),
        '--requested-start',start.isoformat(),'--requested-end',(start+timedelta(days=30)).isoformat(),
        '--require-capacity','--output',str(output)],capture_output=True,text=True)
    assert result.returncode==2,result.stderr
    report=json.loads(output.read_text());assert report['count_and_budget_capacity_pass'] is False and report['execution_ready'] is False


def test_cli_refuses_output_inside_original_evidence(tmp_path):
    import subprocess,sys
    runner,clock=setup(tmp_path);reference=tmp_path/'reference.json';reference.write_text(json.dumps(runner.reference))
    output=runner.root/'extra.json'
    result=subprocess.run([sys.executable,'scripts/check_cash_capacity.py','--reference',str(reference),'--output',str(output)],capture_output=True,text=True)
    assert result.returncode==1 and not output.exists()
