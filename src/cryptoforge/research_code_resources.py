"""Fixed trusted cgroup diagnostics; no candidate/command or database access API."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import time

from cryptoforge import semantic_source_collector as files
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields


SYSTEMD_RUN = '/usr/bin/systemd-run'
SYSTEMCTL = '/usr/bin/systemctl'
BWRAP = '/usr/bin/bwrap'
PYTHON = '/usr/bin/python3'
ENV = '/usr/bin/env'
SCOPE_SECONDS = 3
PARENT_SECONDS = 8
POLICY = {'schema_version': 'trusted-code-resources-v1', 'memory_max_bytes': 67108864,
    'memory_swap_max_bytes': 0, 'tasks_max': 8, 'cpu_quota_usec': 25000, 'cpu_period_usec': 100000,
    'scope_runtime_seconds': SCOPE_SECONDS, 'parent_wait_seconds': PARENT_SECONDS,
    'candidate_execution_enabled': False, 'shared_candidate_budget_integrated': False}
UNIT = re.compile(r'cryptoforge-research-resource-[a-f0-9]{16}\.scope')

INNER = r'''
import errno, hashlib, json, os, signal, socket, sys, time
mode, unit, group, parent_net = sys.argv[1:]
def read(name):
    with open('/probe-cgroup/' + name) as stream: return stream.read().strip()
def events(): return dict(line.split() for line in read('pids.events').splitlines())
controls = {name: read(name) for name in ('memory.max', 'memory.swap.max', 'pids.max', 'cpu.max')}
with open('/proc/self/status') as stream:
    status = dict(line.split(':', 1) for line in stream if ':' in line)
checks = {
    'memory_max_configured': controls['memory.max'] == '67108864',
    'swap_disabled': controls['memory.swap.max'] == '0',
    'tasks_max_configured': controls['pids.max'] == '8',
    'cpu_quota_configured': controls['cpu.max'].split() == ['25000', '100000'],
    'network_namespace_differs': os.readlink('/proc/self/ns/net') != parent_net,
    'only_loopback': [name for _, name in socket.if_nameindex()] == ['lo'],
    'private_database_paths_hidden': not any(os.path.exists(path) for path in
        ('/home', '/root', '/run', '/var', '/workspace', '/tmp/.s.PGSQL.5432')),
    'environment_cleared': dict(os.environ) == {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PWD': '/tmp'},
    'controller_mount_readonly': False,
    'capabilities_dropped': int(status['CapEff'].strip(), 16) == 0,
    'no_new_privileges': status['NoNewPrivs'].strip() == '1',
}
try:
    with open('/probe-cgroup/pids.max', 'w') as stream: stream.write('9')
except OSError as error:
    checks['controller_mount_readonly'] = error.errno == errno.EROFS
if not all(checks.values()): raise RuntimeError('fixed profile checks failed')
# Network checks occur only after observing a different namespace with sole loopback.
blocked = []
for port in (54321, 55432):
    with socket.socket() as connection:
        connection.settimeout(0.1)
        blocked.append(connection.connect_ex(('127.0.0.1', port)) == errno.ECONNREFUSED)
checks['local_database_ports_unreachable'] = all(blocked)
children = []
before = int(events()['max'])
if mode == 'observe':
    denied = False
    try:
        for _ in range(16):
            try: child = os.fork()
            except OSError as error:
                denied = error.errno == errno.EAGAIN; break
            if child == 0:
                time.sleep(30); os._exit(0)
            children.append(child)
    finally:
        for child in children:
            os.kill(child, signal.SIGKILL); os.waitpid(child, 0)
    checks['task_limit_enforced'] = denied and int(events()['max']) > before
else:
    ready_read, ready_write = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(ready_read)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        os.write(ready_write, b'1'); os.close(ready_write)
        time.sleep(30); os._exit(0)
    os.close(ready_write)
    checks['timeout_child_ignores_sigterm'] = os.read(ready_read, 1) == b'1'
    os.close(ready_read)
    children.append(child)
core = {'schema_version': 'trusted-resource-child-v1', 'mode': mode, 'unit': unit,
    'cgroup_path': group, 'controls': controls, 'checks': checks,
    'created_children': len(children), 'python_version': sys.version.split()[0]}
print(json.dumps(core), flush=True)
if mode == 'timeout_tree': time.sleep(30)
if not all(checks.values()): raise RuntimeError('trusted probe incomplete')
'''

LAUNCHER = r'''
import json, os, re, sys
unit, mode, parent_net = sys.argv[1:]
assert re.fullmatch(r'cryptoforge-research-resource-[a-f0-9]{16}\.scope', unit)
assert mode in ('observe', 'timeout_tree')
with open('/proc/self/cgroup') as stream: group = stream.read().strip()
assert group.startswith('0::/') and '\n' not in group
group = group[3:]
assert group.endswith('/' + unit) and '..' not in group.split('/')
controller = os.path.realpath('/sys/fs/cgroup' + group)
assert controller.startswith('/sys/fs/cgroup/') and controller.endswith('/' + unit)
argv = ['/usr/bin/bwrap', '--unshare-all', '--unshare-user', '--disable-userns',
    '--assert-userns-disabled', '--die-with-parent', '--new-session', '--clearenv',
    '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
    '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev',
    '--remount-ro', '/proc', '--remount-ro', '/dev', '--size', '8388608', '--tmpfs', '/tmp',
    '--ro-bind', controller, '/probe-cgroup', '--cap-drop', 'ALL', '--remount-ro', '/', '--chdir', '/tmp',
    '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'PWD', '/tmp',
    '--', '/usr/bin/python3', '-I', '-S', '-c', INNER, mode, unit, group, parent_net]
os.execve('/usr/bin/bwrap', argv, {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
'''.replace('INNER, mode', repr(INNER) + ', mode')


def _environment():
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'XDG_RUNTIME_DIR': '/run/user/' + str(os.getuid()),
        'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/' + str(os.getuid()) + '/bus'}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _runtime():
    return {name: _sha(Path(path).resolve()) for name, path in
        (('systemd_run', SYSTEMD_RUN), ('systemctl', SYSTEMCTL), ('bwrap', BWRAP), ('python', PYTHON), ('env', ENV))}


def _checked_unit(unit):
    if not isinstance(unit, str) or UNIT.fullmatch(unit) is None:
        raise ValueError('generated diagnostic unit required')
    return unit


def probe_argv(unit, mode, parent_net):
    _checked_unit(unit)
    if mode not in ('observe', 'timeout_tree') or re.fullmatch(r'net:\[[0-9]+\]', parent_net) is None:
        raise ValueError('fixed trusted probe mode and namespace required')
    properties = ('MemoryMax=67108864', 'MemorySwapMax=0', 'TasksMax=8', 'CPUQuota=25%',
        'CPUQuotaPeriodSec=100ms', 'RuntimeMaxSec=3s', 'TimeoutStopSec=1s', 'SendSIGKILL=yes')
    return [SYSTEMD_RUN, '--user', '--scope', '--quiet', '--collect',
        '--expand-environment=no', '--unit=' + unit, *['--property=' + value for value in properties],
        '--', ENV, '-i', 'PATH=/usr/bin:/bin', 'LANG=C.UTF-8', PYTHON, '-I', '-S', '-c',
        LAUNCHER, unit, mode, parent_net]


def _control(*arguments):
    return subprocess.run([SYSTEMCTL, '--user', *arguments], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, env=_environment(), check=False)


def cleanup(unit):
    _checked_unit(unit)
    try:
        stopped = _control('stop', unit)
    except subprocess.TimeoutExpired:
        _control('kill', '--kill-whom=all', '--signal=KILL', unit)
        stopped = _control('stop', unit)
    state = _control('show', '--property=LoadState', '--value', unit)
    return {'unit_removed': state.stdout.strip() == b'not-found', 'stop_returncode': stopped.returncode}


def run_probe(mode):
    unit = 'cryptoforge-research-resource-' + secrets.token_hex(8) + '.scope'
    parent_net = os.readlink('/proc/self/ns/net'); argv = probe_argv(unit, mode, parent_net)
    process, output, returncode, removal = None, None, None, None
    started = time.monotonic()
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True, env=_environment())
        output, _ = process.communicate(timeout=PARENT_SECONDS)
        returncode = process.returncode
    finally:
        try:
            removal = cleanup(unit)
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL); process.communicate(timeout=1)
    elapsed = time.monotonic() - started
    if output is None or len(output) > 32000:
        raise ValueError('bounded fixed probe output required')
    observation = strict_json(output.decode(), max_bytes=32000)
    exact_fields(observation, {'schema_version', 'mode', 'unit', 'cgroup_path', 'controls', 'checks',
        'created_children', 'python_version'})
    expected = {'memory_max_configured', 'swap_disabled', 'tasks_max_configured', 'cpu_quota_configured',
        'network_namespace_differs', 'only_loopback', 'private_database_paths_hidden', 'environment_cleared',
        'controller_mount_readonly', 'local_database_ports_unreachable', 'capabilities_dropped',
        'no_new_privileges'} | ({'task_limit_enforced'} if mode == 'observe' else {'timeout_child_ignores_sigterm'})
    exact_fields(observation['checks'], expected)
    group = observation['cgroup_path']
    if (not isinstance(group, str) or not group.startswith('/user.slice/') or not group.endswith('/' + unit)
            or any(part in ('.', '..', '') for part in group.split('/')[1:])):
        raise ValueError('trusted unit cgroup path required')
    cgroup_removed = not (Path('/sys/fs/cgroup') / group.lstrip('/')).exists()
    if (observation['schema_version'] != 'trusted-resource-child-v1' or observation['mode'] != mode
            or observation['unit'] != unit or observation['python_version'] != '3.12.3'
            or any(value is not True for value in observation['checks'].values())
            or observation['controls'] != {'memory.max': '67108864', 'memory.swap.max': '0',
                'pids.max': '8', 'cpu.max': '25000 100000'}
            or type(observation['created_children']) is not int or not 1 <= observation['created_children'] <= 8
            or not removal['unit_removed'] or not cgroup_removed
            or (returncode != 0 if mode == 'observe' else returncode != -signal.SIGTERM)
            or (mode == 'timeout_tree' and not SCOPE_SECONDS - 0.5 <= elapsed < PARENT_SECONDS)):
        raise ValueError('trusted resource controls incomplete')
    return {'mode': mode, 'unit': unit, 'argv_sha256': digest(argv), 'returncode': returncode,
        'observation': observation, 'cleanup': removal, 'cgroup_removed': cgroup_removed,
        'observed_wall_seconds': elapsed, 'runtime_deadline_tree_observed': mode == 'timeout_tree'}


def inspect(directory):
    directory = Path(directory); directory.mkdir(mode=0o700)
    source = _sha(__file__); runtime, profile, probes, error = None, None, [], None
    try:
        runtime = _runtime()
        commands = ([SYSTEMD_RUN, '--version'], [BWRAP, '--version'],
            [SYSTEMCTL, '--user', 'show', '--property=Version', '--value'])
        observed = [subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=3, check=False, env=_environment()) for argv in commands]
        profile = [result.stdout.decode().splitlines()[0] for result in observed]
        if any(result.returncode for result in observed) or profile != [
            'systemd 255 (255.4-1ubuntu8.18)', 'bubblewrap 0.9.0', '255.4-1ubuntu8.18']:
            raise ValueError('unchecked trusted resource profile')
        for mode in ('observe', 'timeout_tree'): probes.append(run_probe(mode))
        if _runtime() != runtime or _sha(__file__) != source:
            raise ValueError('trusted resource implementation changed')
    except (OSError, ValueError, IndexError, RuntimeError, subprocess.SubprocessError, UnicodeError):
        error = 'trusted_resource_controls_unavailable_or_unchecked'
    core = {'schema_version': 'trusted-code-resource-readiness-v1', 'policy': dict(POLICY),
        'checked_at': datetime.now(timezone.utc).isoformat(), 'implementation_sha256': source,
        'runtime': runtime, 'profile': profile, 'probes': probes, 'safe_error': error,
        'status': 'trusted_resource_controls_observed' if error is None else 'unavailable',
        'candidate_executed': False, 'candidate_execution_enabled': False, 'execution_authorized': False,
        'shared_candidate_budget_integrated': False, 'runtime_mount_audited': False,
        'seccomp_policy_verified': False, 'security_audit_completed': False,
        'memory_oom_stress_tested': False, 'cpu_throttle_stress_tested': False,
        'database_connections': 0, 'provider_requests': 0, 'training_executed': False}
    result = {**core, 'receipt_sha256': digest(core)}
    files._write(directory, 'readiness.json', result); files._sync(directory); files._sync(directory.parent)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv); result = inspect(args.directory)
    print('Trusted cgroup resource probe: ' + result['status'] + '; candidate execution disabled')
    return 0 if result['status'] == 'trusted_resource_controls_observed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
