from datetime import UTC,datetime,timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from cryptoforge.local_source_provenance import canonical,parse
from cryptoforge.managed_reference_feeder import ManagedReferenceFeeder,FeederRetention

ROOT=Path(__file__).resolve().parents[1]
ENV=dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='do-not-persist-this-key')


class Clock:
    def __init__(self):self.at=datetime(2026,10,26,13,tzinfo=UTC)
    def __call__(self):return self.at
    def advance(self,seconds):self.at+=timedelta(seconds=seconds)


def route(fresh=True,identity='a'*64):
    return dict(rest_instance_identity_verified=True,row_binding=dict(sql_identity_sha256=identity,candle_freshness_pass=fresh))


def make(tmp_path,policy=None):
    clock=Clock()
    obj=ManagedReferenceFeeder.create(tmp_path/'managed',ROOT,ENV,policy=policy,clock=clock,route=route)
    return obj,clock


def invoke(plan,output,*,env):
    assert env['CRYPTOFORGE_BACKEND']=='local'
    return dict(success=True,reference_refresh_verified=True,stages=[])


def test_new_cycles_keep_registration_and_real_file_receipts(tmp_path):
    obj,clock=make(tmp_path);first=obj.run(ENV,route=route,invoke=invoke)
    clock.advance(1);second=obj.run(ENV,route=route,invoke=invoke)
    assert first['cycle_root']!=second['cycle_root']
    resumed=ManagedReferenceFeeder.open(obj.reference,clock=clock)
    status=resumed.status()
    assert status['completed_cycles']==2 and status['latest']['success']
    assert all(status[k] is False for k in ('full_worker_or_host_qualified','live_admission_granted','economic_profitability_established'))
    assert 'do-not-persist-this-key' not in ''.join(p.read_text() for p in obj.root.rglob('*.json'))


def test_retention_only_deletes_old_successes_and_preserves_last_two(tmp_path):
    obj,clock=make(tmp_path,FeederRetention(maximum_cycles=3))
    research=tmp_path/'original-research-receipt.json';research.write_text('keep original')
    paths=[]
    for _ in range(4):
        paths.append(Path(obj.run(ENV,route=route,invoke=invoke)['cycle_root']));clock.advance(1)
    assert not paths[0].exists() and all(p.exists() for p in paths[1:])
    assert research.read_text()=='keep original'
    assert obj.status()['completed_cycles']==3
    receipt=parse((paths[-1]/'started.json').read_bytes())
    assert len(receipt['pruned_operational_cycles'])==1


def test_failed_cycles_are_protected_and_quota_stops_before_mutation(tmp_path):
    obj,clock=make(tmp_path,FeederRetention(maximum_cycles=3));calls=[]
    def failed(plan,output,*,env):calls.append(True);return dict(success=False,reference_refresh_verified=False)
    for _ in range(3):obj.run(ENV,route=route,invoke=failed);clock.advance(1)
    with pytest.raises(ValueError,match='protected operational retention'):
        obj.run(ENV,route=route,invoke=failed)
    assert len(calls)==3 and obj.status()['completed_cycles']==3


def test_unknown_operation_blocks_next_run_before_new_effect(tmp_path):
    obj,clock=make(tmp_path)
    def unknown(*a,**k):raise RuntimeError('unknown cache writes')
    with pytest.raises(RuntimeError):obj.run(ENV,route=route,invoke=unknown)
    with pytest.raises(ValueError,match='incomplete operational cycle'):
        ManagedReferenceFeeder.open(obj.reference,clock=clock).run(ENV,route=route,invoke=invoke)


def test_stale_or_changed_postcheck_cannot_report_success(tmp_path):
    obj,clock=make(tmp_path);routes=iter([route(),route(fresh=False)])
    result=obj.run(ENV,route=lambda:next(routes),invoke=invoke)
    assert not result['success'] and result['reference_refresh_verified']
    clock.advance(1);routes=iter([route(),route(identity='b'*64)])
    assert obj.run(ENV,route=lambda:next(routes),invoke=invoke)['success'] is False


def test_changed_instance_before_refresh_never_calls_writer(tmp_path):
    obj,clock=make(tmp_path)
    def poison(*a,**kw):pytest.fail('writer invoked on wrong cluster')
    with pytest.raises(ValueError,match='instance differs'):
        obj.run(ENV,route=lambda:route(identity='b'*64),invoke=poison)
    assert obj.status()['completed_cycles']==0


def test_corrupted_history_is_never_pruned_or_reused(tmp_path):
    obj,clock=make(tmp_path);result=obj.run(ENV,route=route,invoke=invoke)
    path=Path(result['cycle_root'])/'before.json';raw=path.read_bytes()
    path.write_bytes(raw.replace(b'a'*64,b'b'*64))
    clock.advance(90000)
    with pytest.raises(ValueError,match='receipt/files differ'):
        obj.run(ENV,route=route,invoke=invoke)
    assert path.exists()


def test_registration_runtime_alias_and_clock_guards(tmp_path,monkeypatch):
    import cryptoforge.managed_reference_feeder as m
    obj,clock=make(tmp_path)
    alias=tmp_path/'alias';alias.symlink_to(obj.root)
    with pytest.raises(ValueError):ManagedReferenceFeeder.open(dict(obj.reference,root=str(alias)),clock=clock)
    clock.advance(-1)
    with pytest.raises(ValueError,match='clock'):obj.status()
    clock.advance(1)
    monkeypatch.setattr(m,'runtime_hashes',lambda root:{})
    with pytest.raises(ValueError,match='runtime'):ManagedReferenceFeeder.open(obj.reference,clock=clock)


def test_single_writer_and_disk_floor(tmp_path,monkeypatch):
    import fcntl
    from types import SimpleNamespace
    obj,clock=make(tmp_path)
    with (obj.root/'writer.lock').open('rb') as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):obj.run(ENV,route=route,invoke=invoke)
    monkeypatch.setattr('cryptoforge.managed_reference_feeder.shutil.disk_usage',lambda _:SimpleNamespace(free=2048*1024**2))
    with pytest.raises(ValueError,match='disk reserve'):obj.run(ENV,route=route,invoke=invoke)


@pytest.mark.parametrize('changes',[dict(maximum_cycles=True),dict(minimum_free_disk_mb=2047),dict(maximum_cycle_bytes=4096),dict(maximum_bytes=128*1024**2)])
def test_retention_caps_are_explicit_and_bounded(changes):
    with pytest.raises(ValueError):FeederRetention(**changes)


def test_true_process_death_leaves_durable_pending_and_blocks_automatic_repeat(tmp_path):
    code='''
import os,sys,json
from pathlib import Path
from cryptoforge.managed_reference_feeder import ManagedReferenceFeeder
root=Path(sys.argv[1])
env=dict(CRYPTOFORGE_BACKEND='local',CRYPTOFORGE_LOCAL_API_KEY='synthetic')
def route():return dict(rest_instance_identity_verified=True,row_binding=dict(sql_identity_sha256='a'*64,candle_freshness_pass=True))
obj=ManagedReferenceFeeder.create(root/'managed',Path.cwd(),env,route=route)
(root/'ref.json').write_text(json.dumps(obj.reference))
def die(*a,**kw):os._exit(42)
obj.run(env,route=route,invoke=die)
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==42,result.stderr
    obj=ManagedReferenceFeeder.open(json.loads((tmp_path/'ref.json').read_text()))
    with pytest.raises(ValueError,match='incomplete'):obj.status()


def test_proposed_units_have_pins_resource_limits_and_inactive_interval():
    spec=importlib.util.spec_from_file_location('manage_cli',ROOT/'scripts/manage_reference_feeder.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    text=m.service_text(dict(root='/synthetic/root',manifest_sha256='a'*64,registration_sha256='b'*64))
    assert '--manifest-sha256' in text and 'MemoryMax=768M' in text and 'KillMode=control-group' in text
    assert '\nWorkingDirectory='+str(ROOT)+'\n' in text
    assert 'OnUnitInactiveSec=120s' in m.TIMER and 'OnUnitActiveSec=' not in m.TIMER
    with pytest.raises(ValueError):m._quote('bad\nvalue')
