import os
from pathlib import Path
import subprocess
import sys

import pytest

from cryptoforge.forecast_runtime_inventory import UNITS,_fd_mode,_unit_status,inspect_runtime


def units(timer='active',service='inactive'):
    return {'status':'ok','units':{name:{'Id':name,'LoadState':'loaded','ActiveState':timer if name.endswith('.timer') else service,'SubState':'waiting'} for name in UNITS}}


def process(proc,pid,ledger=None,flags='02',start=100):
    d=proc/str(pid);(d/'fd').mkdir(parents=True);(d/'fdinfo').mkdir()
    (d/'stat').write_text(f'{pid} (test) '+' '.join(['S']+['0']*18+[str(start)])+'\n')
    if ledger:
        (d/'fd'/'7').symlink_to(ledger)
        (d/'fdinfo'/'7').write_text('pos:\t0\nflags:\t'+flags+'\n')
    return d


@pytest.fixture
def sample(tmp_path):
    ledger=tmp_path/'ledger.sqlite';ledger.write_bytes(b'example')
    proc=tmp_path/'proc';proc.mkdir();p=process(proc,1);(p/'comm').write_text('systemd\n')
    return ledger,proc


def test_active_timers_block_even_with_no_visible_open_file(sample):
    ledger,proc=sample
    result=inspect_runtime(ledger,proc_root=proc,unit_reader=units)
    assert 'writer_timer_active' in result['blockers']
    assert result['matching_processes']==[] and result['pid1_hint']=='systemd'
    assert not result['host_process_visibility_proved'] and not result['cutover_allowed']
    assert ledger.read_bytes()==b'example'


def test_matches_by_inode_and_reports_fd_access_not_other_process_data(sample):
    ledger,proc=sample;process(proc,123,ledger,'0100002')
    result=inspect_runtime(ledger,proc_root=proc,unit_reader=units)
    assert result['matching_processes']==[{'pid':123,'start_tick':100,'descriptors':[{'fd':7,'file':'database','access':'read_write'}]}]
    assert 'ledger_descriptors_observed' in result['blockers']
    assert 'command' not in str(result).lower()


def test_sidecars_unit_changes_and_running_service_block(sample):
    ledger,proc=sample;sidecar=Path(str(ledger)+'-wal');sidecar.write_text('')
    process(proc,345,sidecar,'01')
    observations=iter((units('active','inactive'),units('inactive','active')))
    result=inspect_runtime(ledger,proc_root=proc,unit_reader=lambda:next(observations))
    assert {'sqlite_sidecar_observed','unit_status_changed_during_scan','writer_service_active_or_transitioning','ledger_descriptors_observed'}<=set(result['blockers'])
    assert result['matching_processes'][0]['descriptors'][0]['file']=='-wal'


def test_unavailable_units_and_inaccessible_fdinfo_are_unknown(sample):
    ledger,proc=sample;p=process(proc,111,ledger);(p/'fdinfo'/'7').unlink()
    result=inspect_runtime(ledger,proc_root=proc,unit_reader=lambda:{'status':'unavailable','units':{}})
    assert {'unit_status_unavailable','process_visibility_incomplete'}<=set(result['blockers'])
    assert result['matching_fdinfo_unknown']==1


def test_rejects_ledger_aliases_hardlinks_and_limits(sample,tmp_path):
    ledger,proc=sample;alias=tmp_path/'alias';alias.symlink_to(ledger)
    with pytest.raises(ValueError,match='canonical'):inspect_runtime(alias,proc_root=proc,unit_reader=units)
    with pytest.raises(ValueError,match='inventory limit'):inspect_runtime(ledger,proc_root=proc,unit_reader=units,maximum_pids=0)
    hard=tmp_path/'hard';os.link(ledger,hard)
    with pytest.raises(ValueError,match='original'):inspect_runtime(ledger,proc_root=proc,unit_reader=units)


def test_unit_parser_rejects_incomplete_and_duplicate_data(monkeypatch):
    complete='\n\n'.join('\n'.join([f'Id={name}','LoadState=loaded','ActiveState=inactive','SubState=dead']) for name in UNITS)+'\n'
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args[0],0,complete,''))
    assert _unit_status()['status']=='ok'
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args[0],0,complete+'\nId=duplicate\n',''))
    assert _unit_status()['status']=='invalid'
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess(args[0],1,'','denied'))
    assert _unit_status()=={'status':'unavailable','units':{}}


def test_modes_and_detects_files_changing_during_scan(sample):
    ledger,proc=sample;calls=0
    def change():
        nonlocal calls
        calls+=1
        if calls==2:ledger.write_bytes(b'changed')
        return units('inactive','inactive')
    result=inspect_runtime(ledger,proc_root=proc,unit_reader=change)
    assert 'ledger_files_changed_during_scan' in result['blockers']
    assert [_fd_mode('flags:\t0'),_fd_mode('flags:\t1'),_fd_mode('flags:\t2'),_fd_mode('flags:\tnot-octal')]==['read','write','read_write','unknown']
    assert not result['cutover_allowed']


def test_reused_pid_is_reported_as_incomplete(sample,monkeypatch):
    import cryptoforge.forecast_runtime_inventory as module
    ledger,proc=sample;process(proc,123,ledger);original=module._start_tick;calls=0
    def changed(path):
        nonlocal calls
        value=original(path)
        if path.name=='123':
            calls+=1
            if calls==2:return value+1
        return value
    monkeypatch.setattr(module,'_start_tick',changed)
    result=inspect_runtime(ledger,proc_root=proc,unit_reader=units)
    assert result['processes_vanished_or_changed']==1
    assert result['matching_processes']==[] and 'process_visibility_incomplete' in result['blockers']


def test_inventory_deadline_fails_without_partial_result(sample,monkeypatch):
    import cryptoforge.forecast_runtime_inventory as module
    ledger,proc=sample;values=iter((0,2))
    monkeypatch.setattr(module,'monotonic',lambda:next(values))
    with pytest.raises(TimeoutError,match='deadline'):
        inspect_runtime(ledger,proc_root=proc,unit_reader=units,maximum_seconds=1)


def test_cli_receipt_is_new_and_never_replaces_existing(sample,tmp_path):
    ledger,_=sample;out=tmp_path/'receipts';out.mkdir();receipt=out/'status.json'
    script=Path(__file__).resolve().parents[1]/'scripts/inspect_forecast_runtime.py'
    args=[sys.executable,str(script),'--ledger',str(ledger),'--output',str(receipt)]
    subprocess.run(args,check=True,capture_output=True)
    before=receipt.read_bytes()
    assert subprocess.run(args,capture_output=True).returncode!=0
    assert receipt.read_bytes()==before
    assert subprocess.run(args[:-1]+[str(ledger.parent/'bad.json')],capture_output=True).returncode!=0
