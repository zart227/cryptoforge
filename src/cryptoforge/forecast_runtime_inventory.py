"""Bounded read-only observation of a forecast ledger's local runtime.

This is not a quiescence proof: processes may start or open files immediately
before or after inspection, and inaccessible processes are explicitly counted.
No process command line or environment is read or emitted.
"""
from datetime import UTC, datetime
import os
from pathlib import Path
import stat
import subprocess
from time import monotonic

UNITS=('cryptoforge-supabase-executor.service','cryptoforge-supabase-executor.timer',
       'cryptoforge-primary-forecast-outcomes.service','cryptoforge-primary-forecast-outcomes.timer')
FIELDS=('Id','LoadState','ActiveState','SubState','Result','MainPID','UnitFileState')


def _unit_status():
    command=['systemctl','--user','show',*UNITS,*['-p'+field for field in FIELDS],'--no-pager']
    try:
        p=subprocess.run(command,capture_output=True,text=True,timeout=8,check=False)
    except (OSError,subprocess.TimeoutExpired):return {'status':'unavailable','units':{}}
    if p.returncode!=0 or len(p.stdout)>32768:return {'status':'unavailable','units':{}}
    units={}
    for block in p.stdout.strip().split('\n\n'):
        row={}
        for line in block.splitlines():
            key,sep,value=line.partition('=')
            if not sep or key not in FIELDS or key in row:return {'status':'invalid','units':{}}
            row[key]=value
        name=row.get('Id')
        if name not in UNITS or name in units or not {'Id','LoadState','ActiveState','SubState'}<=row.keys():
            return {'status':'invalid','units':{}}
        if any(len(value)>128 for value in row.values()):return {'status':'invalid','units':{}}
        units[name]=row
    return {'status':'ok','units':units} if set(units)==set(UNITS) else {'status':'invalid','units':{}}


def _files(path):
    result={}
    for suffix in ('','-wal','-shm','-journal'):
        name=Path(str(path)+suffix)
        if name.is_symlink():raise ValueError('original ledger files required')
        try:st=name.stat()
        except FileNotFoundError:
            if not suffix:raise ValueError('existing ledger required')
            continue
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:raise ValueError('original ledger files required')
        result[suffix or 'database']={'dev':st.st_dev,'ino':st.st_ino,'bytes':st.st_size,'mtime_ns':st.st_mtime_ns}
    return result


def _start_tick(path):
    content=(path/'stat').read_text()
    end=content.rfind(')')
    if end<0:raise ValueError('malformed process stat')
    fields=content[end+1:].split()
    if len(fields)<20 or not fields[19].isdigit():raise ValueError('malformed process start time')
    return int(fields[19])


def _fd_mode(info):
    for line in info.splitlines():
        if line.startswith('flags:'):
            try: flags=int(line.split(':',1)[1].strip(),8)&os.O_ACCMODE
            except ValueError:return 'unknown'
            return {os.O_RDONLY:'read',os.O_WRONLY:'write',os.O_RDWR:'read_write'}.get(flags,'unknown')
    return 'unknown'


def inspect_runtime(ledger, *, proc_root='/proc', unit_reader=None, maximum_pids=10000, maximum_seconds=30):
    if (type(maximum_pids) is not int or maximum_pids<1 or
            type(maximum_seconds) is not int or not 1<=maximum_seconds<=120):
        raise ValueError('bounded inventory limits required')
    started=datetime.now(UTC);deadline=monotonic()+maximum_seconds
    ledger=Path(ledger).absolute()
    if ledger.resolve()!=ledger:raise ValueError('canonical ledger required')
    proc=Path(proc_root);before=_files(ledger)
    reader=unit_reader or _unit_status
    units_before=reader()
    try:pid1=(proc/'1/comm').read_text().strip()
    except (OSError,UnicodeError):pid1='unavailable'
    # This value is a hint only; systemd may itself run in a container.
    pid1_hint='systemd' if pid1=='systemd' else 'other_or_unavailable'
    try:pids=sorted((int(p.name) for p in proc.iterdir() if p.name.isdigit()))
    except OSError as exc:raise ValueError('process inventory unavailable') from exc
    if len(pids)>maximum_pids:raise ValueError('process inventory limit exceeded')
    matches=[];inaccessible=0;vanished=0;unknown_fdinfo=0;scanned=0;changed_pid=0
    keys={(v['dev'],v['ino']):name for name,v in before.items()}
    for pid in pids:
        if monotonic()>deadline:raise TimeoutError('process inventory deadline')
        process=proc/str(pid)
        try:
            start=_start_tick(process)
            descriptors=list((process/'fd').iterdir())
        except (FileNotFoundError,ProcessLookupError):vanished+=1;continue
        except (PermissionError,ValueError,OSError):inaccessible+=1;continue
        scanned+=1;found=[]
        for descriptor in descriptors:
            if monotonic()>deadline:raise TimeoutError('process inventory deadline')
            if not descriptor.name.isdigit():continue
            try:info=descriptor.stat()
            except (FileNotFoundError,ProcessLookupError):continue
            except (PermissionError,OSError):inaccessible+=1;continue
            kind=keys.get((info.st_dev,info.st_ino))
            if kind is None:continue
            try:mode=_fd_mode((process/'fdinfo'/descriptor.name).read_text())
            except (OSError,UnicodeError):mode='unknown'
            if mode=='unknown':unknown_fdinfo+=1
            found.append({'fd':int(descriptor.name),'file':kind,'access':mode})
        try:finish=_start_tick(process)
        except (OSError,ValueError):vanished+=1;continue
        if finish!=start:changed_pid+=1;continue
        if found:matches.append({'pid':pid,'start_tick':start,'descriptors':sorted(found,key=lambda x:x['fd'])})
    units_after=reader();after=_files(ledger)
    if monotonic()>deadline:raise TimeoutError('process inventory deadline')
    blockers=['full_writer_inventory_and_fencing_not_proved','host_process_visibility_not_proved',
              'point_in_time_scan_not_quiescence']
    if units_before.get('status')!='ok' or units_after.get('status')!='ok':blockers.append('unit_status_unavailable')
    elif units_before!=units_after:blockers.append('unit_status_changed_during_scan')
    if any(row.get('ActiveState')=='active' for name,row in units_after.get('units',{}).items() if name.endswith('.timer')):
        blockers.append('writer_timer_active')
    if any(row.get('ActiveState') in ('active','activating','deactivating','reloading') for name,row in units_after.get('units',{}).items() if name.endswith('.service')):
        blockers.append('writer_service_active_or_transitioning')
    if matches:blockers.append('ledger_descriptors_observed')
    if inaccessible or unknown_fdinfo or vanished or changed_pid:blockers.append('process_visibility_incomplete')
    if before!=after:blockers.append('ledger_files_changed_during_scan')
    if any(name!='database' for name in before.keys()|after.keys()):blockers.append('sqlite_sidecar_observed')
    return {'schema_version':'forecast-runtime-inventory-v1','started_at':started.isoformat(),
            'completed_at':datetime.now(UTC).isoformat(),'ledger':str(ledger),'files_before':before,'files_after':after,
            'pid1_hint':pid1_hint,'processes_enumerated':len(pids),'processes_scanned':scanned,
            'processes_vanished_or_changed':vanished+changed_pid,'inaccessible_entries':inaccessible,
            'matching_fdinfo_unknown':unknown_fdinfo,'matching_processes':matches,
            'unit_status_before':units_before,'unit_status_after':units_after,'blockers':blockers,
            'host_process_visibility_proved':False,'quiescence_proved':False,'cutover_allowed':False,
            'services_changed':False,'ledger_modified':False,
            'scope':'single read-only point observation; not exclusive ownership or complete writer inventory'}
