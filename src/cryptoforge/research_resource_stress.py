"""Fixed OOM/CPU probes inside disposable diagnostic scopes; no candidate API."""
from datetime import datetime, timezone
import argparse
import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import time

from cryptoforge import research_code_resources as controls
from cryptoforge import research_local_export as private
from cryptoforge import research_data_protocol as temporal
from cryptoforge import semantic_source_collector as files
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields


POLICY = {'schema_version': 'research-resource-stress-policy-v1',
    'memory_max_bytes': 67108864, 'memory_swap_max_bytes': 0, 'tasks_max': 8,
    'cpu_quota_usec': 25000, 'cpu_period_usec': 100000, 'scope_runtime_seconds': 5,
    'parent_timeout_seconds': 10, 'minimum_ancestor_headroom_bytes': 335544320,
    'maximum_allocator_bytes': 100663296, 'cpu_stress_wall_seconds': 1.25,
    'oom_policy': 'continue_for_fixed_diagnostic_observer_only',
    'maximum_output_bytes': 32000, 'candidate_execution_enabled': False,
    'shared_candidate_budget_integrated': False}
UNIT = re.compile(r'cryptoforge-research-stress-[a-f0-9]{16}\.scope')
CHECKS = {'fixed_resource_controls', 'network_namespace_differs', 'only_loopback',
    'private_database_paths_hidden', 'environment_cleared', 'controller_readonly',
    'capabilities_dropped', 'no_new_privileges', 'local_database_ports_unreachable',
    'ancestor_headroom_checked', 'oom_group_disabled'}
COUNTERS = {'memory_events': {'max', 'oom', 'oom_kill'},
    'cpu': {'usage_usec', 'user_usec', 'system_usec', 'nr_periods', 'nr_throttled', 'throttled_usec'}}


INNER = r'''
import errno, json, os, signal, socket, sys, time
mode, unit, group, parent_net, checked_headroom = sys.argv[1:]
def read(name):
    with open('/probe-cgroup/'+name) as stream: return stream.read().strip()
def counters(name, keys):
    values = dict(line.split() for line in read(name).splitlines())
    return {key: int(values[key]) for key in keys}
def snapshot():
    return {'memory_events': counters('memory.events', ('max','oom','oom_kill')),
        'cpu': counters('cpu.stat', ('usage_usec','user_usec','system_usec','nr_periods','nr_throttled','throttled_usec')),
        'memory_current_bytes': int(read('memory.current')), 'memory_peak_bytes': int(read('memory.peak')),
        'memory_swap_current_bytes': int(read('memory.swap.current'))}
limits = {name: read(name) for name in ('memory.max','memory.swap.max','pids.max','cpu.max','memory.oom.group')}
with open('/proc/self/status') as stream:
    status = dict(line.split(':',1) for line in stream if ':' in line)
checks = {
    'fixed_resource_controls': limits == {'memory.max':'67108864','memory.swap.max':'0','pids.max':'8','cpu.max':'25000 100000','memory.oom.group':'0'},
    'network_namespace_differs': os.readlink('/proc/self/ns/net') != parent_net,
    'only_loopback': [name for _,name in socket.if_nameindex()] == ['lo'],
    'private_database_paths_hidden': not any(os.path.exists(path) for path in ('/home','/root','/run','/var','/workspace','/tmp/.s.PGSQL.5432')),
    'environment_cleared': dict(os.environ) == {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PWD':'/tmp'},
    'controller_readonly': False, 'capabilities_dropped': int(status['CapEff'].strip(),16) == 0,
    'no_new_privileges': status['NoNewPrivs'].strip() == '1',
    'ancestor_headroom_checked': checked_headroom == '335544320',
    'oom_group_disabled': limits['memory.oom.group'] == '0',
}
try:
    with open('/probe-cgroup/memory.max','w') as stream: stream.write('67108865')
except OSError as error:
    checks['controller_readonly'] = error.errno == errno.EROFS
if not all(checks.values()): raise RuntimeError('isolation controls incomplete before stress')
blocked=[]
for port in (54321,55432):
    with socket.socket() as connection:
        connection.settimeout(.1); blocked.append(connection.connect_ex(('127.0.0.1',port)) == errno.ECONNREFUSED)
checks['local_database_ports_unreachable'] = all(blocked)
if not all(checks.values()): raise RuntimeError('isolated port check incomplete')
before = snapshot(); child_exit = None; burn_seconds = None
if mode == 'memory_oom':
    child = os.fork()
    if child == 0:
        chunks=[]
        for _ in range(12):
            block=bytearray(8*1024*1024)
            for page in range(0,len(block),4096): block[page]=1
            chunks.append(block)
        os._exit(90)
    _, wait_status = os.waitpid(child,0)
    child_exit = os.waitstatus_to_exitcode(wait_status)
else:
    began=time.monotonic(); deadline=began+1.25; value=1
    while time.monotonic()<deadline: value=(value*1664525+1013904223)&0xffffffff
    burn_seconds=time.monotonic()-began
after = snapshot()
print(json.dumps({'schema_version':'research-resource-stress-child-v1','mode':mode,'unit':unit,
    'cgroup_path':group,'limits':limits,'checks':checks,'before':before,'after':after,
    'allocator_child_exit':child_exit,'cpu_burn_wall_seconds':burn_seconds,'python_version':sys.version.split()[0]}),flush=True)
'''


LAUNCHER = r'''
import os, re, sys
unit, mode, parent_net = sys.argv[1:]
assert re.fullmatch(r'cryptoforge-research-stress-[a-f0-9]{16}\.scope',unit)
assert mode in ('memory_oom','cpu_throttle')
with open('/proc/self/cgroup') as stream: group=stream.read().strip()
assert group.startswith('0::/') and '\n' not in group
group=group[3:]
assert group.endswith('/'+unit) and '..' not in group.split('/')
controller=os.path.realpath('/sys/fs/cgroup'+group)
assert controller.startswith('/sys/fs/cgroup/') and controller.endswith('/'+unit)
# No allocation occurs unless every finite ancestor limit leaves headroom.
ancestor=os.path.dirname(controller)
while ancestor.startswith('/sys/fs/cgroup'):
    maximum=ancestor+'/memory.max'
    if os.path.exists(maximum):
        with open(maximum) as stream: limit=stream.read().strip()
        if limit!='max':
            with open(ancestor+'/memory.current') as stream: current=int(stream.read())
            assert int(limit)-current>=335544320
    if ancestor=='/sys/fs/cgroup': break
    ancestor=os.path.dirname(ancestor)
with open('/proc/meminfo') as stream:
    available=int(next(line.split()[1] for line in stream if line.startswith('MemAvailable:')))*1024
assert available>=335544320
argv=['/usr/bin/bwrap','--unshare-all','--unshare-user','--disable-userns','--assert-userns-disabled',
    '--die-with-parent','--new-session','--clearenv','--ro-bind','/usr','/usr',
    '--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
    '--proc','/proc','--dev','/dev','--remount-ro','/proc','--remount-ro','/dev',
    '--size','8388608','--tmpfs','/tmp','--ro-bind',controller,'/probe-cgroup',
    '--cap-drop','ALL','--remount-ro','/','--chdir','/tmp',
    '--setenv','LANG','C.UTF-8','--setenv','PATH','/usr/bin:/bin','--setenv','PWD','/tmp',
    '--','/usr/bin/python3','-I','-S','-c',INNER,mode,unit,group,parent_net,'335544320']
os.execve('/usr/bin/bwrap',argv,{'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
'''.replace('INNER,mode', repr(INNER)+',mode')


def implementation():
    return {'stress': controls._sha(__file__), 'controls': controls._sha(controls.__file__),
        'fixed_inner_sha256': hashlib.sha256(INNER.encode()).hexdigest(),
        'fixed_launcher_sha256': hashlib.sha256(LAUNCHER.encode()).hexdigest()}


_LOADED = implementation()
_POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('stress_source_or_policy_changed')


def checked_unit(unit):
    if type(unit) is not str or UNIT.fullmatch(unit) is None:
        raise ValueError('generated_stress_scope_required')
    return unit


def probe_argv(unit, mode, namespace):
    _guard(); checked_unit(unit)
    if mode not in ('memory_oom', 'cpu_throttle') or re.fullmatch(r'net:\[[0-9]+\]', namespace) is None:
        raise ValueError('fixed_stress_mode_and_namespace_required')
    properties = ('MemoryMax=67108864', 'MemorySwapMax=0', 'TasksMax=8', 'CPUQuota=25%',
        'CPUQuotaPeriodSec=100ms', 'RuntimeMaxSec=5s', 'TimeoutStopSec=1s', 'SendSIGKILL=yes', 'OOMPolicy=continue')
    return [controls.SYSTEMD_RUN, '--user', '--scope', '--quiet', '--collect', '--expand-environment=no',
        '--unit='+unit, *['--property='+value for value in properties], '--', controls.ENV, '-i',
        'PATH=/usr/bin:/bin', 'LANG=C.UTF-8', controls.PYTHON, '-I', '-S', '-c', LAUNCHER, unit, mode, namespace]


def cleanup(unit):
    checked_unit(unit)
    try:
        controls._control('stop', unit)
    except subprocess.TimeoutExpired:
        controls._control('kill', '--kill-whom=all', '--signal=KILL', unit)
        controls._control('stop', unit)
    state = controls._control('show', '--property=LoadState', '--value', unit)
    if state.stdout.strip() != b'not-found':
        controls._control('kill', '--kill-whom=all', '--signal=KILL', unit)
        controls._control('stop', unit)
        state = controls._control('show', '--property=LoadState', '--value', unit)
    return {'unit_removed': state.stdout.strip() == b'not-found'}


def validate_observation(value, unit, mode):
    checked_unit(unit)
    exact_fields(value, {'schema_version', 'mode', 'unit', 'cgroup_path', 'limits', 'checks', 'before', 'after',
        'allocator_child_exit', 'cpu_burn_wall_seconds', 'python_version'})
    group = value['cgroup_path']
    if (value['schema_version'] != 'research-resource-stress-child-v1' or value['mode'] != mode or value['unit'] != unit
            or value['python_version'] != '3.12.3' or type(group) is not str or not group.startswith('/user.slice/')
            or not group.endswith('/'+unit) or any(part in ('', '.', '..') for part in group.split('/')[1:])
            or value['limits'] != {'memory.max': '67108864', 'memory.swap.max': '0', 'pids.max': '8',
                'cpu.max': '25000 100000', 'memory.oom.group': '0'}):
        raise ValueError('fixed_stress_runtime_controls_required')
    exact_fields(value['checks'], CHECKS)
    if any(flag is not True for flag in value['checks'].values()):
        raise ValueError('stress_isolation_checks_incomplete')
    for name in ('before', 'after'):
        snapshot = value[name]
        exact_fields(snapshot, {'memory_events', 'cpu', 'memory_current_bytes', 'memory_peak_bytes', 'memory_swap_current_bytes'})
        for key, fields in COUNTERS.items():
            exact_fields(snapshot[key], fields)
            if any(type(number) is not int or not 0 <= number < 2**63 for number in snapshot[key].values()):
                raise ValueError('nonnegative_kernel_counters_required')
        for key in ('memory_current_bytes', 'memory_peak_bytes', 'memory_swap_current_bytes'):
            if type(snapshot[key]) is not int or not 0 <= snapshot[key] < 2**63:
                raise ValueError('nonnegative_kernel_memory_required')
        if snapshot['memory_swap_current_bytes'] != 0:
            raise ValueError('stress_swap_must_remain_disabled')
    before, after = value['before'], value['after']
    if any(after[key][field] < before[key][field] for key, fields in COUNTERS.items() for field in fields):
        raise ValueError('kernel_counter_regression')
    if after['memory_peak_bytes'] < before['memory_peak_bytes']:
        raise ValueError('kernel_memory_peak_regression')
    delta = {key: {field: after[key][field]-before[key][field] for field in fields} for key, fields in COUNTERS.items()}
    if mode == 'memory_oom':
        if (type(value['allocator_child_exit']) is not int or value['allocator_child_exit'] != -signal.SIGKILL
                or value['cpu_burn_wall_seconds'] is not None
                or any(delta['memory_events'][field] <= 0 for field in ('max', 'oom', 'oom_kill'))):
            raise ValueError('actual_cgroup_oom_kill_not_observed')
    elif mode == 'cpu_throttle':
        seconds = value['cpu_burn_wall_seconds']
        if (value['allocator_child_exit'] is not None or type(seconds) not in (int, float) or not 1.25 <= seconds < 5
                or any(delta['cpu'][field] <= 0 for field in ('usage_usec', 'nr_periods', 'nr_throttled', 'throttled_usec'))
                or delta['memory_events']['oom_kill'] != 0):
            raise ValueError('actual_cpu_bandwidth_throttling_not_observed')
    else:
        raise ValueError('fixed_stress_mode_required')
    return delta


def run_probe(mode):
    unit = 'cryptoforge-research-stress-'+secrets.token_hex(8)+'.scope'
    namespace = os.readlink('/proc/self/ns/net')
    argv = probe_argv(unit, mode, namespace)
    process = None; output = None; removal = None; started = time.monotonic()
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True, env=controls._environment())
        output, _ = process.communicate(timeout=POLICY['parent_timeout_seconds'])
    finally:
        try:
            removal = cleanup(unit)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL); process.communicate(timeout=1)
    elapsed = time.monotonic()-started
    if output is None or len(output) > POLICY['maximum_output_bytes'] or process.returncode != 0:
        raise ValueError('bounded_successful_stress_observation_required')
    observation = strict_json(output.decode(), max_bytes=POLICY['maximum_output_bytes'])
    delta = validate_observation(observation, unit, mode)
    removed = not (Path('/sys/fs/cgroup')/observation['cgroup_path'].lstrip('/')).exists()
    if not removal['unit_removed'] or not removed:
        raise ValueError('stress_scope_cleanup_incomplete')
    _guard()
    return {'mode': mode, 'unit': unit, 'argv_sha256': digest(argv), 'returncode': process.returncode,
        'parent_net_namespace': namespace,
        'observation': observation, 'counter_delta': delta, 'cleanup': removal, 'cgroup_removed': removed,
        'observed_wall_seconds': elapsed,
        'accounting_scope': 'diagnostic_scope_to_after_snapshot_excludes_supervisor_cli_control_and_cleanup'}


def inspect(directory):
    _guard(); directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('new_stress_receipt_directory_required')
    runtime = profile = None; probes = []; error = None
    try:
        runtime = controls._runtime()
        commands = ([controls.SYSTEMD_RUN, '--version'], [controls.BWRAP, '--version'],
            [controls.SYSTEMCTL, '--user', 'show', '--property=Version', '--value'])
        results = [subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=3, check=False, env=controls._environment()) for argv in commands]
        profile = [result.stdout.decode().splitlines()[0] for result in results]
        if any(result.returncode for result in results) or profile != [
                'systemd 255 (255.4-1ubuntu8.18)', 'bubblewrap 0.9.0', '255.4-1ubuntu8.18']:
            raise ValueError('unreviewed_stress_runtime')
        for mode in ('memory_oom', 'cpu_throttle'): probes.append(run_probe(mode))
        if controls._runtime() != runtime:
            raise ValueError('stress_runtime_changed')
        _guard()
    except (OSError, ValueError, IndexError, RuntimeError, subprocess.SubprocessError, UnicodeError):
        error = 'trusted_stress_unavailable_or_incomplete'
    core = {'schema_version': 'research-resource-stress-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'implementation': _LOADED, 'policy': dict(POLICY), 'runtime': runtime, 'profile': profile,
        'kernel_release': os.uname().release, 'probes': probes, 'safe_error': error,
        'status': 'trusted_stress_observed' if error is None else 'unavailable',
        'memory_oom_stress_tested': error is None, 'cpu_throttle_stress_tested': error is None,
        'candidate_executed': False, 'execution_authorized': False, 'candidate_execution_enabled': False,
        'shared_candidate_budget_integrated': False, 'full_cli_accounting_verified': False,
        'minimal_mount_policy_qualified': False, 'seccomp_policy_verified': False, 'security_audit_completed': False,
        'database_connections': 0, 'provider_requests': 0, 'model_prediction_performed': False,
        'training_executed': False, 'production_promotion_authorized': False}
    result = {**core, 'receipt_sha256': digest(core)}
    directory.mkdir(mode=0o700); files._write(directory, 'stress.json', result)
    files._sync(directory); files._sync(directory.parent)
    return result


def verify(directory):
    """Verify saved counters and bindings; never automatically repeat a stress run."""
    _guard(); directory = private._safe_directory(directory, private=True)
    result = temporal._read(directory, 'stress.json', 64000)
    exact_fields(result, {'schema_version', 'checked_at', 'implementation', 'policy', 'runtime', 'profile',
        'kernel_release', 'probes', 'safe_error', 'status', 'memory_oom_stress_tested', 'cpu_throttle_stress_tested',
        'candidate_executed', 'execution_authorized', 'candidate_execution_enabled', 'shared_candidate_budget_integrated',
        'full_cli_accounting_verified', 'minimal_mount_policy_qualified', 'seccomp_policy_verified',
        'security_audit_completed', 'database_connections', 'provider_requests', 'model_prediction_performed',
        'training_executed', 'production_promotion_authorized', 'receipt_sha256'})
    core = {key: value for key, value in result.items() if key != 'receipt_sha256'}
    if result.get('receipt_sha256') != digest(core) or result.get('implementation') != _LOADED or result.get('policy') != POLICY:
        raise ValueError('stress_receipt_or_implementation_changed')
    if (result['schema_version'] != 'research-resource-stress-v1' or result.get('status') != 'trusted_stress_observed'
            or result.get('safe_error') is not None or result['memory_oom_stress_tested'] is not True
            or result['cpu_throttle_stress_tested'] is not True
            or type(result['database_connections']) is not int or result['database_connections'] != 0
            or type(result['provider_requests']) is not int or result['provider_requests'] != 0):
        raise ValueError('successful_original_stress_receipt_required')
    exact_fields(result['runtime'], {'systemd_run', 'systemctl', 'bwrap', 'python', 'env'})
    if (any(type(value) is not str or re.fullmatch('[a-f0-9]{64}', value) is None for value in result['runtime'].values())
            or result['profile'] != ['systemd 255 (255.4-1ubuntu8.18)', 'bubblewrap 0.9.0', '255.4-1ubuntu8.18']
            or type(result['kernel_release']) is not str or re.fullmatch('[A-Za-z0-9._+\\-]{1,128}', result['kernel_release']) is None
            or type(result['checked_at']) is not str or len(result['checked_at']) > 64
            or datetime.fromisoformat(result['checked_at']).utcoffset() is None
            or type(result['probes']) is not list or len(result['probes']) != 2):
        raise ValueError('original_stress_environment_required')
    if [probe['mode'] for probe in result['probes']] != ['memory_oom', 'cpu_throttle']:
        raise ValueError('two_original_stress_observations_required')
    for probe in result['probes']:
        exact_fields(probe, {'mode', 'unit', 'argv_sha256', 'returncode', 'parent_net_namespace', 'observation',
            'counter_delta', 'cleanup', 'cgroup_removed', 'observed_wall_seconds', 'accounting_scope'})
        checked_unit(probe['unit'])
        seconds = probe['observed_wall_seconds']
        if (probe['argv_sha256'] != digest(probe_argv(probe['unit'], probe['mode'], probe['parent_net_namespace']))
                or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0
                or probe['accounting_scope'] != 'diagnostic_scope_to_after_snapshot_excludes_supervisor_cli_control_and_cleanup'):
            raise ValueError('fixed_stress_command_and_accounting_required')
        if probe['counter_delta'] != validate_observation(probe['observation'], probe['unit'], probe['mode']):
            raise ValueError('stress_counter_evidence_changed')
        if (probe['cleanup'] != {'unit_removed': True} or probe['cgroup_removed'] is not True
                or type(probe['returncode']) is not int or probe['returncode'] != 0):
            raise ValueError('original_stress_cleanup_incomplete')
        if (Path('/sys/fs/cgroup')/probe['observation']['cgroup_path'].lstrip('/')).exists():
            raise ValueError('original_stress_scope_present')
    if any(result.get(name) is not False for name in ('candidate_executed', 'execution_authorized', 'candidate_execution_enabled',
            'shared_candidate_budget_integrated', 'full_cli_accounting_verified', 'minimal_mount_policy_qualified',
            'seccomp_policy_verified', 'security_audit_completed', 'model_prediction_performed', 'training_executed',
            'production_promotion_authorized')):
        raise ValueError('stress_receipt_cannot_authorize_execution')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('command', choices=('inspect', 'verify'))
    parser.add_argument('--directory', type=Path, required=True); args = parser.parse_args(argv)
    try:
        result = inspect(args.directory) if args.command == 'inspect' else verify(args.directory)
    except Exception:
        print('Trusted resource stress refused; candidate execution disabled'); return 2
    print('Trusted resource stress: '+result['status']+'; candidate execution disabled')
    return 0 if result['status'] == 'trusted_stress_observed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
