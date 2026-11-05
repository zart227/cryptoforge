"""Fixed default-deny seccomp probe with reduced mounts; no candidate runtime API."""
import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import signal
import struct
import subprocess
import time

from cryptoforge import research_runtime_mounts as mounts
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields

seccomp = mounts.seccomp
inventory = mounts.inventory
ALLOWED = ['read', 'write', 'close', 'fstat', 'lseek', 'mmap', 'mprotect', 'munmap', 'brk',
    'rt_sigaction', 'rt_sigprocmask', 'rt_sigreturn', 'madvise', 'futex', 'clock_gettime',
    'exit', 'exit_group', 'openat', 'newfstatat', 'getdents64', 'readlink', 'fcntl', 'getrandom']
ALLOW_NUMBERS = {'read': 0, 'write': 1, 'close': 3, 'fstat': 5, 'lseek': 8, 'mmap': 9,
    'mprotect': 10, 'munmap': 11, 'brk': 12, 'rt_sigaction': 13, 'rt_sigprocmask': 14,
    'rt_sigreturn': 15, 'madvise': 28, 'futex': 202, 'clock_gettime': 228, 'exit': 60,
    'exit_group': 231, 'openat': 257, 'newfstatat': 262, 'getdents64': 217, 'readlink': 89,
    'fcntl': 72, 'getrandom': 318}
DENY_NUMBERS = {**seccomp.SYSCALL_NUMBERS, 'getppid': 110}
TESTED = [*seccomp.TESTED, 'getppid']
BPF_SHA = '821fd908d01ddf34c504bd8cc900f15559241ae30d9a0817b0c538ec3d663e6f'
POLICY = {'schema_version': 'trusted-syscall-allowlist-policy-v1', 'architecture': 'x86_64',
    'default_action': 'errno_EPERM', 'allowed_syscalls': ALLOWED, 'allowed_syscall_numbers': ALLOW_NUMBERS,
    'tested_denials': TESTED, 'reviewed_bpf_bytes': 248, 'reviewed_bpf_sha256': BPF_SHA,
    'library_sha256': seccomp.LIBRARY_SHA, 'wall_seconds': 5, 'cleanup_seconds': 1,
    'cpu_seconds': 2, 'memory_bytes': 134217728, 'maximum_output_bytes': 64000,
    'candidate_execution_enabled': False, 'candidate_runtime_integration_enabled': False,
    'security_audit_complete': False}


# The inherited fixed program imports everything before installing its filter.
# It accepts no Python, paths, mount mappings or syscall policies from a candidate.
_EXTENSION = seccomp._EXTENSION
_EXTENSION = _EXTENSION.replace('before=status_now();context=lib.seccomp_init(0x7fff0000)',
    'baseline_getppid=os.getppid();before=status_now();context=lib.seccomp_init(0x00050001)')
_EXTENSION = _EXTENSION.replace('numbers={name:lib.seccomp_syscall_resolve_name(name.encode()) for name in denied}',
    'numbers={name:lib.seccomp_syscall_resolve_name(name.encode()) for name in denied+["getppid"]}\n'
    'allowed='+repr(ALLOWED)+'\nallow_numbers={name:lib.seccomp_syscall_resolve_name(name.encode()) for name in allowed}')
_EXTENSION = _EXTENSION.replace('if any(number<0 for number in numbers.values()):',
    'if any(number<0 for number in [*numbers.values(),*allow_numbers.values()]):')
_EXTENSION = _EXTENSION.replace('for number in numbers.values():', 'for number in allow_numbers.values():')
_EXTENSION = _EXTENSION.replace('lib.seccomp_rule_add_array(context,0x00050000|errno.EPERM,number,0,None)',
    'lib.seccomp_rule_add_array(context,0x7fff0000,number,0,None)')
_EXTENSION = _EXTENSION.replace("'bpf':[ctypes.c_int(-1),null,ctypes.c_uint(0)]}",
    "'bpf':[ctypes.c_int(-1),null,ctypes.c_uint(0)],'getppid':[]}")
_EXTENSION = _EXTENSION.replace("'syscall_numbers':numbers,'denial_errno':results,",
    "'syscall_numbers':numbers,'allowed_syscall_numbers':allow_numbers,'default_action':'errno_EPERM',"
    "'baseline_getppid_succeeded':baseline_getppid>0,'denial_errno':results,")
assert mounts.PROBE.count(seccomp._EXTENSION) == 1
PROBE = mounts.PROBE.replace(seccomp._EXTENSION, _EXTENSION)
assert 'context=lib.seccomp_init(0x7fff0000)' not in PROBE
assert 'lib.seccomp_rule_add_array(context,0x00050000|errno.EPERM' not in PROBE


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reduced_runtime': mounts.implementation(), 'fixed_program_sha256': digest(PROBE)}


_LOADED = implementation(); _POLICY_SHA = digest(POLICY)


def _guard(policy=POLICY):
    if digest(policy) != _POLICY_SHA or implementation() != _LOADED:
        raise ValueError('fixed_syscall_allowlist_profile_required')


def argv(canary, namespaces, profile):
    args = mounts.argv(canary, namespaces, profile)
    args[args.index(mounts.PROBE)] = PROBE
    return args


def bpf_semantics(raw):
    """Check this small forward-only BPF against the fixed policy, without loading it.

    Its only inputs are architecture and syscall number; comparisons are EQ/GE
    against constants. Boundaries and adjacent values therefore cover every
    equivalence class of the entire unsigned32 syscall-number domain.
    """
    if type(raw) is not bytes or len(raw) != 248:
        raise ValueError('fixed248byte_bpf_required')
    instructions = list(struct.iter_unpack('<HBBI', raw))
    if (instructions[:3] != [(0x20, 0, 0, 4), (0x15, 0, 28, 0xc000003e), (0x20, 0, 0, 0)]
            or any(code not in (0x15, 0x35, 0x06) for code, _, _, _ in instructions[3:])):
        raise ValueError('fixed_bpf_instruction_shape_required')
    for i, (code, yes, no, _) in enumerate(instructions):
        if code in (0x15, 0x35) and max(i+1+yes, i+1+no) >= len(instructions):
            raise ValueError('bounded_forward_bpf_jumps_required')
    def evaluate(arch, number):
        index = accumulator = 0
        for _ in instructions:
            code, yes, no, k = instructions[index]
            if code == 0x20: accumulator = arch if k == 4 else number; index += 1
            elif code == 0x06: return k
            else:
                matches = accumulator == k if code == 0x15 else accumulator >= k
                index += 1+(yes if matches else no)
            if index >= len(instructions): break
        raise ValueError('bpf_terminal_return_required')
    boundaries = {0, 0xffffffff}
    for code, _, _, k in instructions[3:]:
        if code in (0x15, 0x35):
            boundaries.update(n for n in (k-1, k, k+1) if 0 <= n <= 0xffffffff)
    architectures = (0, 0xc000003d, 0xc000003e, 0xc000003f, 0xffffffff)
    for arch in architectures:
        for number in boundaries:
            expected = (0 if arch != 0xc000003e or 0x40000000 <= number < 0xffffffff
                else 0x7fff0000 if number in ALLOW_NUMBERS.values() else 0x00050001)
            if evaluate(arch, number) != expected:
                raise ValueError('bpf_differs_from_fixed_default_deny_policy')
    return {'instruction_count': len(instructions), 'number_equivalence_representatives': len(boundaries),
        'architecture_representatives': len(architectures), 'cases_checked': len(boundaries)*len(architectures),
        'all_uint32_number_classes_checked': True, 'unsupported_ABI_action': 'kill_thread',
        'seccomp_filter_loaded_by_verifier': False}


def validate(observed, namespaces):
    exact_fields(observed, {'schema_version', 'checks', 'namespaces', 'environment_keys',
        'canary_sha256', 'python_version', 'filter', 'mount_checks'})
    exact_fields(observed['checks'], {'namespaces_differ', 'only_loopback_interface', 'home_and_host_sockets_hidden',
        'environment_cleared', 'capabilities_dropped', 'no_new_privileges', 'canary_readonly',
        'root_readonly', 'temporary_write_succeeded'})
    exact_fields(observed['namespaces'], set(namespaces)); exact_fields(observed['mount_checks'], mounts.MOUNT_CHECKS)
    f = observed['filter']
    exact_fields(f, {'libseccomp_version', 'architecture', 'syscall_numbers', 'allowed_syscall_numbers',
        'default_action', 'baseline_getppid_succeeded', 'denial_errno', 'before_filters', 'after_filters',
        'after_mode', 'no_new_privileges', 'baseline_socket_creation_succeeded', 'bpf_sha256', 'bpf_bytes', 'bpf_base64'})
    exact_fields(f['allowed_syscall_numbers'], set(ALLOWED)); exact_fields(f['syscall_numbers'], set(DENY_NUMBERS))
    exact_fields(f['denial_errno'], set(TESTED))
    try: raw = base64.b64decode(f['bpf_base64'], validate=True)
    except (ValueError, TypeError): raise ValueError('canonical_allowlist_bpf_required') from None
    if (observed['schema_version'] != 'trusted-code-isolation-probe-v1' or observed['python_version'] != '3.12.3'
            or observed['environment_keys'] != ['LANG', 'PATH', 'PWD']
            or any(v is not True for v in [*observed['checks'].values(), *observed['mount_checks'].values()])
            or observed['canary_sha256'] != hashlib.sha256(seccomp.isolation.CANARY).hexdigest()
            or any(observed['namespaces'][k] == v for k, v in namespaces.items())
            or f['libseccomp_version'] != [2, 5, 5] or f['architecture'] != 'x86_64'
            or f['allowed_syscall_numbers'] != ALLOW_NUMBERS or f['syscall_numbers'] != DENY_NUMBERS
            or any(type(n) is not int for n in [*f['allowed_syscall_numbers'].values(), *f['syscall_numbers'].values()])
            or type(f['before_filters']) is not int or not 0 <= f['before_filters'] <= 1000
            or type(f['after_filters']) is not int or f['after_filters'] != f['before_filters']+1
            or type(f['after_mode']) is not int or f['after_mode'] != 2 or f['no_new_privileges'] is not True
            or f['baseline_socket_creation_succeeded'] is not True or f['baseline_getppid_succeeded'] is not True
            or f['default_action'] != 'errno_EPERM' or any(type(n) is not int or n != 1 for n in f['denial_errno'].values())
            or type(f['bpf_bytes']) is not int or f['bpf_bytes'] != 248 or len(raw) != 248
            or f['bpf_sha256'] != BPF_SHA or hashlib.sha256(raw).hexdigest() != BPF_SHA
            or base64.b64encode(raw).decode() != f['bpf_base64']):
        raise ValueError('complete_fixed_allowlist_observation_required')
    return {'fixed_child_default_deny_filter_observed': True, 'allowed_syscalls_compiled': len(ALLOWED),
        'denials_mechanically_checked': len(TESTED), 'unlisted_harmless_getppid_denied': True,
        'filter_count_increment': 1, 'bpf_sha256': BPF_SHA, 'mount_checks': observed['mount_checks'],
        'candidate_runtime_qualified': False, 'security_audit_complete': False,
        'offline_bpf_semantics': bpf_semantics(raw)}


def inspect(directory):
    _guard();directory=Path(directory).absolute();seccomp.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():raise ValueError('new_private_allowlist_directory_required')
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
        _guard();status='trusted_syscall_allowlist_probe_observed'
    except (OSError,ValueError,subprocess.SubprocessError,UnicodeError):pass
    finally:
        if process is not None:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.communicate(timeout=1)
        if canary.read_bytes()!=seccomp.isolation.CANARY:raise ValueError('runtime_mount_canary_changed')
    core={'schema_version':'trusted-syscall-allowlist-probe-v1','checked_at':datetime.now(timezone.utc).isoformat(),'status':status,
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
    if result['receipt_sha256']!=digest(core) or result['schema_version']!='trusted-syscall-allowlist-probe-v1':raise ValueError('runtime_mount_receipt_checksum_required')
    if result['implementation']!=_LOADED or result['policy_sha256']!=digest(POLICY):raise ValueError('original_runtime_mount_implementation_required')
    if result['status']!='trusted_syscall_allowlist_probe_observed' or result['process_reaped'] is not True:raise ValueError('complete_runtime_mount_probe_required')
    if any(result[k] is not False for k in ('candidate_execution_enabled','candidate_runtime_integration_enabled','security_audit_complete','aggregate_resource_limits_qualified')):
        raise ValueError('fixed_allowlist_diagnostic_scope_required')
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
    except (OSError,ValueError):print('Fixed syscall allowlist refused; candidate execution disabled');return 2
    print('Fixed syscall allowlist: '+result['status']+'; candidate execution disabled')
    return 0 if result['status']=='trusted_syscall_allowlist_probe_observed' else 2


if __name__=='__main__':raise SystemExit(main())
