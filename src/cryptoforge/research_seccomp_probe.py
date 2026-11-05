"""Fixed disposable seccomp deny-rule diagnostic; never executes candidate code."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time

from cryptoforge import research_code_isolation as isolation,research_local_export as private
from cryptoforge import semantic_source_collector as files
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical,digest,exact_fields

LIBRARY='/usr/lib/x86_64-linux-gnu/libseccomp.so.2.5.5'
LIBRARY_SHA='b4d9140a7797ccf3ac14f5d9d579b64f157111662940cb8330c632b11a8cea8e'
BPF_SHA='a7b6405ecface464b2df4aea34c6d0a425d11ec81f04f72c5e3575053db3c751'
SYSCALL_NUMBERS={'bpf': 321, 'clone': 56, 'clone3': 435, 'connect': 42, 'execve': 59, 'execveat': 322, 'fork': 57, 'mount': 165, 'ptrace': 101, 'setns': 308, 'socket': 41, 'socketpair': 53, 'umount2': 166, 'unshare': 272, 'vfork': 58}
DENY=['socket','socketpair','connect','fork','vfork','clone','clone3','execve','execveat','ptrace','bpf','mount','umount2','unshare','setns']
TESTED=['socket','socketpair','connect','fork','clone3','execve','execveat','bpf']
POLICY={'schema_version':'trusted-seccomp-diagnostic-policy-v1','architecture':'x86_64','libseccomp_version':[2,5,5],
    'library_path':LIBRARY,'library_sha256':LIBRARY_SHA,'default_action':'allow','denied_syscalls':DENY,
    'reviewed_bpf_sha256':BPF_SHA,'syscall_numbers':SYSCALL_NUMBERS,'deny_action':'errno_EPERM','tested_denials':TESTED,'wall_seconds':5,'cleanup_seconds':1,
    'cpu_seconds':2,'memory_bytes':134217728,'maximum_output_bytes':64000,
    'candidate_execution_enabled':False,'runtime_integration_enabled':False,'full_syscall_allowlist_qualified':False}


# Start from the fixed namespace/canary checks, then install a filter in that child only.
_EXTENSION=r'''
import base64, ctypes, platform
resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
if platform.machine()!='x86_64':raise RuntimeError('fixed architecture required')
lib=ctypes.CDLL('/usr/lib/x86_64-linux-gnu/libseccomp.so.2.5.5',use_errno=True)
class Version(ctypes.Structure):_fields_=[('major',ctypes.c_uint),('minor',ctypes.c_uint),('micro',ctypes.c_uint)]
lib.seccomp_version.argtypes=[];lib.seccomp_version.restype=ctypes.POINTER(Version)
v=lib.seccomp_version().contents
if [v.major,v.minor,v.micro]!=[2,5,5]:raise RuntimeError('fixed seccomp version required')
lib.seccomp_arch_native.argtypes=[];lib.seccomp_arch_native.restype=ctypes.c_uint32
if lib.seccomp_arch_native()!=0xc000003e:raise RuntimeError('native x86_64 syscall ABI required')
lib.seccomp_init.argtypes=[ctypes.c_uint32];lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_release.argtypes=[ctypes.c_void_p];lib.seccomp_release.restype=None
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p];lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.c_void_p];lib.seccomp_rule_add_array.restype=ctypes.c_int
lib.seccomp_export_bpf.argtypes=[ctypes.c_void_p,ctypes.c_int];lib.seccomp_export_bpf.restype=ctypes.c_int
lib.seccomp_load.argtypes=[ctypes.c_void_p];lib.seccomp_load.restype=ctypes.c_int
# Socket creation is permitted before the filter even in an isolated network namespace.
with socket.socket(socket.AF_INET,socket.SOCK_STREAM):pass
left,right=socket.socketpair();left.close();right.close()
def status_now():
    with open('/proc/self/status') as stream:return dict(line.split(':',1) for line in stream if ':' in line)
before=status_now();context=lib.seccomp_init(0x7fff0000)
if not context:raise RuntimeError('seccomp context unavailable')
denied=['socket','socketpair','connect','fork','vfork','clone','clone3','execve','execveat','ptrace','bpf','mount','umount2','unshare','setns']
numbers={name:lib.seccomp_syscall_resolve_name(name.encode()) for name in denied}
try:
    if any(number<0 for number in numbers.values()):raise RuntimeError('all named syscall rules required')
    for number in numbers.values():
        if lib.seccomp_rule_add_array(context,0x00050000|errno.EPERM,number,0,None)!=0:raise RuntimeError('seccomp rule rejected')
    with open('/tmp/fixed-filter.bpf','wb') as stream:
        if lib.seccomp_export_bpf(context,stream.fileno())!=0:raise RuntimeError('filter export rejected')
    with open('/tmp/fixed-filter.bpf','rb') as stream:bpf=stream.read(8193)
    if not 0<len(bpf)<=8192 or len(bpf)%8:raise RuntimeError('bounded BPF instructions required')
    os.unlink('/tmp/fixed-filter.bpf')
    if lib.seccomp_load(context)!=0:raise RuntimeError('seccomp load rejected')
finally:lib.seccomp_release(context)
after=status_now();results={}
for name,operation in [('socket',lambda:socket.socket(socket.AF_INET,socket.SOCK_STREAM)),('socketpair',socket.socketpair)]:
    try:
        result=operation()
        if isinstance(result,tuple):
            for item in result:item.close()
        else:result.close()
        results[name]=None
    except OSError as error:results[name]=error.errno
try:
    child=os.fork()
except OSError as error:results['fork']=error.errno
else:
    if child==0:os._exit(0)
    os.waitpid(child,0);results['fork']=None
libc=ctypes.CDLL(None,use_errno=True);libc.syscall.argtypes=[ctypes.c_long];libc.syscall.restype=ctypes.c_long
null=ctypes.c_void_p(0)
# Invalid harmless arguments cannot execute a program, connect or create a process if a rule is absent.
arguments={'connect':[ctypes.c_long(-1),null,ctypes.c_long(0)],'clone3':[null,ctypes.c_size_t(0)],
    'execve':[null,null,null],'execveat':[ctypes.c_long(-1),null,null,null,ctypes.c_long(0)],
    'bpf':[ctypes.c_int(-1),null,ctypes.c_uint(0)]}
for name,args in arguments.items():
    ctypes.set_errno(0);value=libc.syscall(numbers[name],*args)
    results[name]=ctypes.get_errno() if value==-1 else None
filter_observation={'libseccomp_version':[v.major,v.minor,v.micro],'architecture':'x86_64',
    'syscall_numbers':numbers,'denial_errno':results,'before_filters':int(before['Seccomp_filters'].strip()),
    'after_filters':int(after['Seccomp_filters'].strip()),'after_mode':int(after['Seccomp'].strip()),
    'no_new_privileges':after['NoNewPrivs'].strip()=='1','baseline_socket_creation_succeeded':True,
    'bpf_sha256':hashlib.sha256(bpf).hexdigest(),'bpf_bytes':len(bpf),'bpf_base64':base64.b64encode(bpf).decode()}
'''
_OLD="print(json.dumps({'schema_version': 'trusted-code-isolation-probe-v1', 'checks': checks,"
assert isolation.PROBE.count(_OLD)==1
PROBE=isolation.PROBE.replace(_OLD,_EXTENSION+"\nprint(json.dumps({'filter':filter_observation,'schema_version': 'trusted-code-isolation-probe-v1', 'checks': checks,",1)


def implementation():
    return {'probe':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'namespace_probe':isolation._sha(isolation.__file__),
        'fixed_program_sha256':digest(PROBE)}


_LOADED=implementation();_POLICY_SHA=digest(POLICY)


def _guard(policy=POLICY):
    if digest(policy)!=_POLICY_SHA or implementation()!=_LOADED:raise ValueError('fixed_seccomp_diagnostic_required')


def argv(canary,namespaces):
    args=isolation.probe_argv(canary,namespaces)
    args[args.index(isolation.PROBE)]=PROBE
    return args


def validate(observed,namespaces):
    exact_fields(observed,{'schema_version','checks','namespaces','environment_keys','canary_sha256','python_version','filter'})
    # Keep all inherited mechanical isolation checks, without upgrading broader readiness flags.
    exact_fields(observed['checks'],{'namespaces_differ','only_loopback_interface','home_and_host_sockets_hidden','environment_cleared',
        'capabilities_dropped','no_new_privileges','canary_readonly','root_readonly','temporary_write_succeeded'})
    exact_fields(observed['namespaces'],set(namespaces))
    f=observed['filter'];exact_fields(f,{'libseccomp_version','architecture','syscall_numbers','denial_errno','before_filters','after_filters',
        'after_mode','no_new_privileges','baseline_socket_creation_succeeded','bpf_sha256','bpf_bytes','bpf_base64'})
    exact_fields(f['syscall_numbers'],set(DENY));exact_fields(f['denial_errno'],set(TESTED))
    try:raw=base64.b64decode(f['bpf_base64'],validate=True)
    except (ValueError,TypeError):raise ValueError('canonical_bpf_export_required') from None
    if (observed['schema_version']!='trusted-code-isolation-probe-v1' or observed['python_version']!='3.12.3'
            or observed['environment_keys']!=['LANG','PATH','PWD'] or any(v is not True for v in observed['checks'].values())
            or observed['canary_sha256']!=hashlib.sha256(isolation.CANARY).hexdigest()
            or any(observed['namespaces'][k]==v for k,v in namespaces.items())
            or f['libseccomp_version']!=[2,5,5] or f['architecture']!='x86_64'
            or type(f['before_filters']) is not int or not 0<=f['before_filters']<=1000
            or type(f['after_filters']) is not int or f['after_filters']!=f['before_filters']+1 or f['after_mode']!=2
            or f['no_new_privileges'] is not True or f['baseline_socket_creation_succeeded'] is not True
            or any(type(n) is not int or not 0<=n<=1024 for n in f['syscall_numbers'].values())
            or len(set(f['syscall_numbers'].values()))!=len(DENY)
            or any(type(n) is not int or n!=1 for n in f['denial_errno'].values())
            or type(f['bpf_bytes']) is not int or f['bpf_bytes']!=len(raw) or not 0<len(raw)<=8192 or len(raw)%8
            or f['syscall_numbers']!=SYSCALL_NUMBERS or f['bpf_sha256']!=BPF_SHA or hashlib.sha256(raw).hexdigest()!=f['bpf_sha256'] or base64.b64encode(raw).decode()!=f['bpf_base64']):
        raise ValueError('complete_fixed_seccomp_observation_required')
    return {'denied_syscalls_compiled':15,'denials_mechanically_checked':8,'filter_count_increment':1,
        'bpf_sha256':f['bpf_sha256'],'default_allow_denylist_only':True,'candidate_runtime_qualified':False}


def inspect(directory,policy=POLICY):
    _guard(policy);directory=Path(directory).absolute();private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():raise ValueError('new_private_seccomp_directory_required')
    directory.mkdir(mode=0o700);files._write(directory,'canary.txt',isolation.CANARY)
    canary=directory/'canary.txt';namespaces={k:os.readlink('/proc/self/ns/'+k) for k in ('net','pid','user','mnt')}
    before=time.monotonic();runtime=None;observed=None;summary=None;status='unavailable';process=None;args=None
    try:
        runtime={**isolation._runtime(),'libseccomp_sha256':isolation._sha(LIBRARY)}
        if runtime['libseccomp_sha256']!=LIBRARY_SHA:raise ValueError('reviewed_library_required')
        version=subprocess.run([isolation.BWRAP,'--version'],env={'PATH':os.defpath,'LANG':'C.UTF-8'},capture_output=True,timeout=1)
        if version.returncode or version.stdout.decode().strip()!='bubblewrap 0.9.0':raise ValueError('reviewed_namespace_runtime_required')
        args=argv(canary,namespaces)
        process=subprocess.Popen(args,env={'PATH':os.defpath,'LANG':'C.UTF-8'},stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,close_fds=True,start_new_session=True)
        raw,_=process.communicate(timeout=5)
        if process.returncode or len(raw)>64000:raise ValueError('fixed_seccomp_probe_failed')
        observed=strict_json(raw.decode(),max_bytes=64000);summary=validate(observed,namespaces)
        if runtime!={**isolation._runtime(),'libseccomp_sha256':isolation._sha(LIBRARY)}:raise ValueError('seccomp_runtime_changed')
        _guard();status='trusted_denylist_probe_observed'
    except (OSError,ValueError,subprocess.SubprocessError,UnicodeError):pass
    finally:
        if process is not None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate(timeout=1)
        if canary.read_bytes()!=isolation.CANARY:raise ValueError('host_seccomp_canary_changed')
    core={'schema_version':'trusted-seccomp-diagnostic-v1','checked_at':datetime.now(timezone.utc).isoformat(),'status':status,
        'policy_sha256':digest(policy),'implementation':_LOADED,'runtime':runtime,'argv_sha256':None if args is None else digest(args),
        'original_canary_path':str(canary),'parent_namespaces':namespaces,'observation':observed,'summary':summary,'process_reaped':process is not None and process.poll() is not None,
        'observed_wall_seconds':time.monotonic()-before,'default_allow_denylist_only':True,'candidate_executed':False,
        'candidate_execution_enabled':False,'runtime_integration_enabled':False,'full_syscall_allowlist_qualified':False,
        'runtime_mount_audited':False,'security_audit_completed':False,'shared_candidate_budget_integrated':False,
        'aggregate_resource_limits_qualified':False,'model_or_fit_or_provider_operations':0,'external_network_requests':0}
    result={**core,'receipt_sha256':digest(core)};files._write(directory,'receipt.json',result);files._sync(directory);files._sync(directory.parent)
    return result



def verify(directory):
    _guard();directory=private._safe_directory(directory,private=True)
    result=strict_json(private._private_read(directory,'receipt.json',64000).decode(),max_bytes=64000)
    exact_fields(result,{'schema_version','checked_at','status','policy_sha256','implementation','runtime','argv_sha256','original_canary_path','parent_namespaces','observation','summary','process_reaped','observed_wall_seconds','default_allow_denylist_only','candidate_executed','candidate_execution_enabled','runtime_integration_enabled','full_syscall_allowlist_qualified','runtime_mount_audited','security_audit_completed','shared_candidate_budget_integrated','aggregate_resource_limits_qualified','model_or_fit_or_provider_operations','external_network_requests','receipt_sha256'})
    core={k:v for k,v in result.items() if k!='receipt_sha256'}
    if result.get('receipt_sha256')!=digest(core) or result.get('schema_version')!='trusted-seccomp-diagnostic-v1':raise ValueError('seccomp_receipt_checksum_required')
    if result.get('implementation')!=_LOADED or result.get('policy_sha256')!=digest(POLICY):raise ValueError('seccomp_profile_changed')
    if result.get('status')!='trusted_denylist_probe_observed':raise ValueError('completed_seccomp_probe_required')
    flags=('candidate_executed','candidate_execution_enabled','runtime_integration_enabled','full_syscall_allowlist_qualified',
        'runtime_mount_audited','security_audit_completed','shared_candidate_budget_integrated','aggregate_resource_limits_qualified')
    if any(result.get(k) is not False for k in flags) or result.get('default_allow_denylist_only') is not True or result.get('process_reaped') is not True:
        raise ValueError('narrow_seccomp_diagnostic_scope_required')
    if private._private_read(directory,'canary.txt',1024)!=isolation.CANARY:raise ValueError('original_seccomp_canary_required')
    if result['runtime']!={**isolation._runtime(),'libseccomp_sha256':isolation._sha(LIBRARY)} or result['runtime']['libseccomp_sha256']!=LIBRARY_SHA:
        raise ValueError('original_seccomp_runtime_required')
    if result['summary']!=validate(result['observation'],result['parent_namespaces']):raise ValueError('seccomp_summary_changed')
    original=Path(result['original_canary_path'])
    private._safe_directory(original.parent,private=True)
    if original.name!='canary.txt' or private._private_read(original.parent,original.name,1024)!=isolation.CANARY:raise ValueError('original_probe_canary_binding_required')
    if any(type(result[k]) is not int or result[k]!=0 for k in ('model_or_fit_or_provider_operations','external_network_requests')):raise ValueError('diagnostic_only_operations_required')
    if result['argv_sha256']!=digest(argv(original,result['parent_namespaces'])):
        raise ValueError('original_seccomp_command_binding_required')
    return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','verify'):subs.add_parser(name).add_argument('--directory',type=Path,required=True)
    args=parser.parse_args(argv)
    try:result=inspect(args.directory) if args.command=='inspect' else verify(args.directory)
    except (OSError,ValueError):print('Fixed seccomp diagnostic refused; candidate execution disabled');return 2
    print('Fixed seccomp diagnostic: '+result['status']+'; candidate execution disabled')
    return 0 if result['status']=='trusted_denylist_probe_observed' else 2


if __name__=='__main__':raise SystemExit(main())
