"""Fixed trusted namespace probe; exposes no command or candidate execution API."""
import argparse
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import time

from cryptoforge import semantic_source_collector as files
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields


BWRAP = '/usr/bin/bwrap'
PYTHON = '/usr/bin/python3'
WALL_SECONDS = 5
CLEANUP_SECONDS = 1
CANARY = b'cryptoforge-trusted-isolation-canary-v1\n'
PROBE = r'''
import errno, hashlib, json, os, resource, socket, sys
resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
def readonly(path):
    try:
        with open(path, 'wb') as stream: stream.write(b'forbidden')
    except OSError as error:
        return error.errno == errno.EROFS
    return False
parent = json.loads(sys.argv[1])
namespaces = {key: os.readlink('/proc/self/ns/' + key) for key in ('net', 'pid', 'user', 'mnt')}
with open('/proc/self/status') as stream:
    status = dict(line.split(':', 1) for line in stream if ':' in line)
with open('/probe-input', 'rb') as stream: canary = hashlib.sha256(stream.read()).hexdigest()
with open('/tmp/probe-write', 'w') as stream: stream.write('temporary')
os.unlink('/tmp/probe-write')
checks = {
    'namespaces_differ': all(value != parent[key] for key, value in namespaces.items()),
    'only_loopback_interface': [name for _, name in socket.if_nameindex()] == ['lo'],
    'home_and_host_sockets_hidden': not any(os.path.exists(path) for path in ('/home', '/root', '/run', '/workspace')),
    'environment_cleared': dict(os.environ) == {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PWD': '/tmp'},
    'capabilities_dropped': int(status['CapEff'].strip(), 16) == 0,
    'no_new_privileges': status['NoNewPrivs'].strip() == '1',
    'canary_readonly': readonly('/probe-input'),
    'root_readonly': readonly('/unwanted-host-write'),
    'temporary_write_succeeded': True,
}
print(json.dumps({'schema_version': 'trusted-code-isolation-probe-v1', 'checks': checks,
    'namespaces': namespaces, 'environment_keys': sorted(os.environ), 'canary_sha256': canary,
    'python_version': sys.version.split()[0]}))
'''


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _runtime():
    return {'bwrap_sha256': _sha(BWRAP), 'python_sha256': _sha(Path(PYTHON).resolve())}


def probe_argv(canary, namespaces):
    # No optional mounts, networking, environment, executable or user script.
    return [BWRAP, '--unshare-all', '--unshare-user', '--disable-userns', '--assert-userns-disabled',
        '--die-with-parent', '--new-session', '--clearenv', '--ro-bind', '/usr', '/usr',
        '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--proc', '/proc', '--dev', '/dev', '--remount-ro', '/proc', '--remount-ro', '/dev',
        '--size', '8388608', '--tmpfs', '/tmp', '--ro-bind', str(canary), '/probe-input',
        '--cap-drop', 'ALL', '--remount-ro', '/', '--chdir', '/tmp',
        '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PATH', '/usr/bin:/bin',
        '--setenv', 'PWD', '/tmp',
        '--', PYTHON, '-I', '-S', '-c', PROBE, canonical(namespaces)]


def inspect(directory):
    directory = Path(directory); directory.mkdir(mode=0o700)
    files._write(directory, 'canary.txt', CANARY)
    canary = (directory / 'canary.txt').resolve()
    namespaces = {key: os.readlink('/proc/self/ns/' + key) for key in ('net', 'pid', 'user', 'mnt')}
    observed, runtime, status, error, version, argv_sha = None, None, 'unavailable', None, None, None
    source_sha = _sha(__file__)
    started = time.monotonic()
    try:
        runtime = _runtime()
        version_result = subprocess.run([BWRAP, '--version'], capture_output=True, timeout=1,
            env={'PATH': os.defpath, 'LANG': 'C.UTF-8'}, check=False)
        version = version_result.stdout.decode().strip()
        if version_result.returncode or version != 'bubblewrap 0.9.0':
            raise ValueError('unchecked_bwrap_profile')
        argv = probe_argv(canary, namespaces); argv_sha = digest(argv)
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env={'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'},
            close_fds=True, start_new_session=True)
        try:
            raw, _ = process.communicate(timeout=WALL_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.communicate(timeout=CLEANUP_SECONDS)
            raise TimeoutError('trusted_probe_timed_out') from None
        if process.returncode or len(raw) > 32000: raise ValueError('trusted_probe_failed')
        observed = strict_json(raw.decode(), max_bytes=32000)
        exact_fields(observed, {'schema_version', 'checks', 'namespaces', 'environment_keys', 'canary_sha256', 'python_version'})
        expected_checks = {'namespaces_differ', 'only_loopback_interface', 'home_and_host_sockets_hidden',
            'environment_cleared', 'capabilities_dropped', 'no_new_privileges', 'canary_readonly',
            'root_readonly', 'temporary_write_succeeded'}
        exact_fields(observed['checks'], expected_checks)
        exact_fields(observed['namespaces'], set(namespaces))
        if (observed['schema_version'] != 'trusted-code-isolation-probe-v1'
                or observed['canary_sha256'] != hashlib.sha256(CANARY).hexdigest()
                or observed['python_version'] != '3.12.3'
                or any(observed['namespaces'][key] == value for key, value in namespaces.items())
                or observed['environment_keys'] != ['LANG', 'PATH', 'PWD']
                or any(value is not True for value in observed['checks'].values())):
            raise ValueError('trusted_probe_incomplete')
        if _runtime() != runtime or _sha(__file__) != source_sha:
            raise ValueError('probe_implementation_changed')
        status = 'trusted_probe_observed'
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError, UnicodeError):
        error = 'trusted_probe_unavailable_or_unchecked_profile'
    finally:
        if canary.read_bytes() != CANARY: raise ValueError('host canary changed')
    core = {'schema_version': 'research-code-isolation-readiness-v1', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': status, 'safe_error': error, 'runtime': runtime, 'bwrap_version': version,
        'parent_namespaces': namespaces, 'observation': observed, 'argv_sha256': argv_sha,
        'trusted_probe_only': True, 'candidate_executed': False, 'candidate_execution_enabled': False,
        'hard_process_count_limit_verified': False, 'aggregate_cpu_memory_control_verified': False,
        'seccomp_policy_verified': False, 'runtime_mount_audited': False, 'security_audit_completed': False,
        'shared_attempt_budget_integrated': False, 'execution_authorized': False,
        'wall_wait_seconds': WALL_SECONDS, 'cleanup_grace_seconds': CLEANUP_SECONDS,
        'observed_wall_seconds': time.monotonic() - started, 'implementation_sha256': source_sha,
        'network_requests': 0, 'api_calls': 0, 'training_executed': False}
    result = {**core, 'receipt_sha256': digest(core)}
    files._write(directory, 'readiness.json', result); files._sync(directory); files._sync(directory.parent)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv); result = inspect(args.directory)
    print('Trusted isolation probe: ' + result['status'] + '; candidate execution remains disabled')
    return 0 if result['status'] == 'trusted_probe_observed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
