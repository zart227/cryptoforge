"""Fixed Python runtime mount inventory/probe; no candidate or arbitrary mount API."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import signal
import stat
import subprocess
import time

from cryptoforge import research_seccomp_probe as seccomp
from cryptoforge.research_training_diagnostics import canonical,digest,exact_fields

STDLIB=Path('/usr/lib/python3.12')
LIBS=['libm.so.6','libz.so.1','libexpat.so.1','libc.so.6','libffi.so.8','libcrypto.so.3','libseccomp.so.2.5.5','ld-linux-x86-64.so.2']
LINKS={'sitecustomize.py':'/etc/python3.12/sitecustomize.py','_sysconfigdata__linux_x86_64-linux-gnu.py':'_sysconfigdata__x86_64-linux-gnu.py',
    'config-3.12-x86_64-linux-gnu/libpython3.12.so':'../../x86_64-linux-gnu/libpython3.12.so.1'}
POLICY={'schema_version':'trusted-runtime-mounts-policy-v1','python_path':'/usr/bin/python3.12','stdlib_path':str(STDLIB),
    'library_names':LIBS,'stdlib_symlinks':LINKS,'maximum_files':2048,'maximum_file_bytes':16777216,
    'maximum_total_bytes':134217728,'maximum_inventory_bytes':524288,'candidate_execution_enabled':False,
    'candidate_runtime_integration_enabled':False,'security_audit_complete':False}
MOUNT_CHECKS={'python_directory_exact','library_directory_exact','unrelated_runtime_paths_hidden','external_stdlib_links_unreadable',
    'internal_sysconfig_link_available','python_prefix_matches','usr_placeholder_readonly'}
_EXTRA=r'''
mount_checks={
 'python_directory_exact':sorted(os.listdir('/usr/bin'))==['python3','python3.12'],
 'library_directory_exact':sorted(os.listdir('/usr/lib/x86_64-linux-gnu'))==sorted(['libm.so.6','libz.so.1','libexpat.so.1','libc.so.6','libffi.so.8','libcrypto.so.3','libseccomp.so.2.5.5','ld-linux-x86-64.so.2']),
 'unrelated_runtime_paths_hidden':not any(os.path.exists(p) for p in ('/usr/share','/usr/local','/usr/sbin','/etc','/opt','/var','/home','/root','/run','/workspace')),
 'external_stdlib_links_unreadable':not any(os.path.exists(p) for p in ('/usr/lib/python3.12/sitecustomize.py','/usr/lib/python3.12/config-3.12-x86_64-linux-gnu/libpython3.12.so')),
 'internal_sysconfig_link_available':os.path.isfile('/usr/lib/python3.12/_sysconfigdata__linux_x86_64-linux-gnu.py'),
 'python_prefix_matches':sys.prefix=='/usr' and sys.base_prefix=='/usr',
 'usr_placeholder_readonly':readonly('/usr/forbidden-write'),
}
'''
_PREFIX="print(json.dumps({'filter':filter_observation,"
assert seccomp.PROBE.count(_PREFIX)==1
PROBE=seccomp.PROBE.replace(_PREFIX,_EXTRA+"\nprint(json.dumps({'mount_checks':mount_checks,'filter':filter_observation,",1)


def implementation():
    return {'audit':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'seccomp':seccomp.implementation(),'fixed_program_sha256':digest(PROBE)}


_LOADED=implementation();_POLICY_SHA=digest(POLICY)


def _guard(policy=POLICY):
    if digest(policy)!=_POLICY_SHA or implementation()!=_LOADED:raise ValueError('fixed_runtime_mount_profile_required')


def _hash_file(path):
    path=Path(path)
    before_open=path.lstat()
    if not stat.S_ISREG(before_open.st_mode):raise ValueError('regular_runtime_file_required')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if (before.st_dev,before.st_ino)!=(before_open.st_dev,before_open.st_ino):raise ValueError('runtime_file_replaced_before_open')
        if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=POLICY['maximum_file_bytes']:raise ValueError('bounded_regular_runtime_file_required')
        checksum=hashlib.sha256();count=0
        while chunk:=stream.read(1048576):
            count+=len(chunk)
            if count>POLICY['maximum_file_bytes']:raise ValueError('runtime_file_grew')
            checksum.update(chunk)
        after=os.fstat(stream.fileno())
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if identity(before)!=identity(after) or count!=before.st_size:raise ValueError('runtime_file_changed_during_inventory')
        return {'bytes':count,'sha256':checksum.hexdigest()}


def inventory():
    _guard()
    if STDLIB.resolve()!=STDLIB or STDLIB.is_symlink() or not STDLIB.is_dir():raise ValueError('original_stdlib_directory_required')
    bindings=[{'source':str(Path(POLICY['python_path']).resolve()),'destination':'/usr/bin/python3.12','kind':'file'},
        {'source':str(STDLIB),'destination':str(STDLIB),'kind':'directory'}]
    bindings +=[{'source':str((Path('/usr/lib/x86_64-linux-gnu')/n).resolve()),'destination':'/usr/lib/x86_64-linux-gnu/'+n,'kind':'file'} for n in LIBS]
    rows=[];links={};total=0
    def add(path,relative):
        nonlocal total
        if len(rows)>=2048:raise ValueError('runtime_file_count_exceeded')
        value=_hash_file(path);total+=value['bytes']
        if total>POLICY['maximum_total_bytes']:raise ValueError('runtime_byte_budget_exceeded')
        rows.append({'path':relative,**value})
    for b in bindings:
        if b['kind']=='file':add(Path(b['source']),b['destination'])
    for directory,dirs,names in os.walk(STDLIB,followlinks=False):
        dirs.sort();names.sort()
        for name in [*dirs,*names]:
            p=Path(directory)/name;relative=str(p.relative_to(STDLIB))
            if p.is_symlink():
                links[relative]=os.readlink(p)
                if relative not in LINKS or links[relative]!=LINKS[relative]:raise ValueError('unreviewed_runtime_symlink')
                if name in dirs:dirs.remove(name)
            elif p.is_dir():continue
            elif p.is_file():add(p,str(p))
            else:raise ValueError('runtime_special_file_forbidden')
    if links!=LINKS:raise ValueError('original_reviewed_stdlib_links_required')
    core={'schema_version':'fixed-runtime-inventory-v1','bindings':bindings,'files':sorted(rows,key=lambda r:r['path']),
        'stdlib_symlinks':links,'file_count':len(rows),'total_bytes':total,'stdlib_security_reviewed':False}
    result={**core,'inventory_sha256':digest(core)}
    if len(canonical(result).encode())>524288:raise ValueError('runtime_inventory_byte_limit')
    _guard();return result


def argv(canary,namespaces,profile):
    # The inventory may supply only the current exact fixed mapping, not arbitrary mounts.
    fixed=[{'source':str(Path(POLICY['python_path']).resolve()),'destination':'/usr/bin/python3.12','kind':'file'},
        {'source':str(STDLIB),'destination':str(STDLIB),'kind':'directory'}]
    fixed +=[{'source':str((Path('/usr/lib/x86_64-linux-gnu')/n).resolve()),'destination':'/usr/lib/x86_64-linux-gnu/'+n,'kind':'file'} for n in LIBS]
    if profile['bindings']!=fixed:raise ValueError('fixed_runtime_mapping_required')
    args=[seccomp.isolation.BWRAP,'--unshare-all','--unshare-user','--disable-userns','--assert-userns-disabled',
        '--die-with-parent','--new-session','--clearenv']
    for path in ('/usr','/usr/bin','/usr/lib','/usr/lib/x86_64-linux-gnu','/usr/lib64'):args+=['--dir',path]
    for b in fixed:args+=['--ro-bind',b['source'],b['destination']]
    args+=['--symlink','python3.12','/usr/bin/python3','--symlink','../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2',
        '--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
        '--proc','/proc','--dev','/dev','--remount-ro','/proc','--remount-ro','/dev','--size','8388608','--tmpfs','/tmp',
        '--ro-bind',str(canary),'/probe-input','--cap-drop','ALL','--remount-ro','/','--chdir','/tmp',
        '--setenv','LANG','C.UTF-8','--setenv','PATH','/usr/bin:/bin','--setenv','PWD','/tmp',
        '--','/usr/bin/python3','-I','-S','-c',PROBE,canonical(namespaces)]
    return args


def validate(observed,namespaces):
    observed=deepcopy(observed)
    if 'mount_checks' not in observed:raise ValueError('fixed_mount_checks_required')
    checks=observed.pop('mount_checks');exact_fields(checks,MOUNT_CHECKS)
    if any(v is not True for v in checks.values()):raise ValueError('minimal_runtime_mount_check_failed')
    return {'mount_checks':checks,'seccomp':seccomp.validate(observed,namespaces),
        'fixed_probe_mount_inventory_verified':True,'candidate_runtime_mount_audited':False,'security_audit_complete':False}


def inspect(directory):
    _guard();directory=Path(directory).absolute();seccomp.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():raise ValueError('new_private_runtime_mount_directory_required')
    directory.mkdir(mode=0o700);seccomp.files._write(directory,'canary.txt',seccomp.isolation.CANARY)
    canary=directory/'canary.txt';namespaces={k:os.readlink('/proc/self/ns/'+k) for k in ('net','pid','user','mnt')}
    before=time.monotonic();profile=None;observed=None;summary=None;process=None;args=None;status='unavailable'
    try:
        profile=inventory();seccomp.files._write(directory,'runtime-inventory.json',profile)
        if seccomp.isolation._sha(seccomp.LIBRARY)!=seccomp.LIBRARY_SHA:raise ValueError('reviewed_seccomp_library_required')
        version=subprocess.run([seccomp.isolation.BWRAP,'--version'],capture_output=True,timeout=1,env={'PATH':os.defpath,'LANG':'C.UTF-8'})
        if version.returncode or version.stdout.decode().strip()!='bubblewrap 0.9.0':raise ValueError('reviewed_bwrap_required')
        args=argv(canary,namespaces,profile)
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            env={'PATH':os.defpath,'LANG':'C.UTF-8'},close_fds=True,start_new_session=True)
        raw,_=process.communicate(timeout=5)
        if process.returncode or len(raw)>64000:raise ValueError('fixed_runtime_mount_probe_failed')
        observed=seccomp.strict_json(raw.decode(),max_bytes=64000);summary=validate(observed,namespaces)
        if inventory()!=profile:raise ValueError('original_runtime_changed_during_probe')
        _guard();status='trusted_runtime_mount_probe_observed'
    except (OSError,ValueError,subprocess.SubprocessError,UnicodeError):pass
    finally:
        if process is not None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate(timeout=1)
        if canary.read_bytes()!=seccomp.isolation.CANARY:raise ValueError('runtime_mount_canary_changed')
    core={'schema_version':'trusted-runtime-mount-probe-v1','checked_at':datetime.now(timezone.utc).isoformat(),'status':status,
        'implementation':_LOADED,'policy_sha256':digest(POLICY),'inventory_sha256':None if profile is None else profile['inventory_sha256'],
        'bwrap_sha256':seccomp.isolation._sha(seccomp.isolation.BWRAP),'original_canary_path':str(canary),
        'parent_namespaces':namespaces,'argv_sha256':None if args is None else digest(args),'observation':observed,'summary':summary,
        'observed_wall_seconds':time.monotonic()-before,'process_reaped':process is not None and process.poll() is not None,
        'candidate_execution_enabled':False,'candidate_runtime_integration_enabled':False,'security_audit_complete':False,
        'aggregate_resource_limits_qualified':False,'external_network_requests':0,'model_or_fit_or_provider_operations':0}
    result={**core,'receipt_sha256':digest(core)};seccomp.files._write(directory,'receipt.json',result);seccomp.files._sync(directory)
    return result


def verify(directory):
    _guard();directory=seccomp.private._safe_directory(directory,private=True)
    result=seccomp.strict_json(seccomp.private._private_read(directory,'receipt.json',64000).decode(),max_bytes=64000)
    exact_fields(result,{'schema_version','checked_at','status','implementation','policy_sha256','inventory_sha256','bwrap_sha256',
        'original_canary_path','parent_namespaces','argv_sha256','observation','summary','observed_wall_seconds','process_reaped',
        'candidate_execution_enabled','candidate_runtime_integration_enabled','security_audit_complete','aggregate_resource_limits_qualified',
        'external_network_requests','model_or_fit_or_provider_operations','receipt_sha256'})
    core={k:v for k,v in result.items() if k!='receipt_sha256'}
    if result['receipt_sha256']!=digest(core) or result['schema_version']!='trusted-runtime-mount-probe-v1':raise ValueError('runtime_mount_receipt_checksum_required')
    if result['implementation']!=_LOADED or result['policy_sha256']!=digest(POLICY):raise ValueError('original_runtime_mount_implementation_required')
    if result['status']!='trusted_runtime_mount_probe_observed' or result['process_reaped'] is not True:raise ValueError('complete_runtime_mount_probe_required')
    if any(result[k] is not False for k in ('candidate_execution_enabled','candidate_runtime_integration_enabled','security_audit_complete','aggregate_resource_limits_qualified')):
        raise ValueError('fixed_diagnostic_scope_required')
    if any(type(result[k]) is not int or result[k]!=0 for k in ('external_network_requests','model_or_fit_or_provider_operations')):raise ValueError('diagnostic_operations_only')
    profile=inventory();saved=seccomp.strict_json(seccomp.private._private_read(directory,'runtime-inventory.json',524288).decode(),max_bytes=524288)
    if saved!=profile or result['inventory_sha256']!=profile['inventory_sha256']:raise ValueError('original_runtime_inventory_changed')
    if result['bwrap_sha256']!=seccomp.isolation._sha(seccomp.isolation.BWRAP):raise ValueError('namespace_runtime_changed')
    original=Path(result['original_canary_path']);seccomp.private._safe_directory(original.parent,private=True)
    if original.name!='canary.txt' or seccomp.private._private_read(original.parent,original.name,1024)!=seccomp.isolation.CANARY:
        raise ValueError('original_mount_canary_required')
    if seccomp.private._private_read(directory,'canary.txt',1024)!=seccomp.isolation.CANARY:raise ValueError('saved_mount_canary_changed')
    if result['argv_sha256']!=digest(argv(original,result['parent_namespaces'],profile)):raise ValueError('fixed_mount_command_binding_required')
    if result['summary']!=validate(result['observation'],result['parent_namespaces']):raise ValueError('fixed_mount_observation_changed')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','verify'):commands.add_parser(name).add_argument('--directory',type=Path,required=True)
    args=parser.parse_args(argv)
    try:result=inspect(args.directory) if args.command=='inspect' else verify(args.directory)
    except (OSError,ValueError):print('Fixed runtime mounts refused; candidate execution disabled');return 2
    print('Fixed runtime mounts: '+result['status']+'; candidate execution disabled')
    return 0 if result['status']=='trusted_runtime_mount_probe_observed' else 2


if __name__=='__main__':raise SystemExit(main())
