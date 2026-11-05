"""Account for two fixed offline verifiers in bounded transient user services."""
import argparse
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import resource
import secrets
import subprocess
import sys
import time

from cryptoforge import research_code_resources as resources
from cryptoforge import research_label_oracle as labels, research_syscall_allowlist as allowlist
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields

files = labels.values.files; private = labels.values.private
MODES = ('source_labels', 'syscall_allowlist')
UNIT = re.compile(r'cryptoforge-research-accounting-[a-f0-9]{16}\.service')
PROPERTIES = ('MemoryMax=134217728', 'MemorySwapMax=0', 'TasksMax=8', 'CPUQuota=50%',
    'CPUQuotaPeriodSec=100ms', 'RuntimeMaxSec=15s', 'TimeoutStopSec=1s', 'SendSIGKILL=yes',
    'KillMode=control-group', 'CPUAccounting=yes', 'MemoryAccounting=yes', 'TasksAccounting=yes',
    'IOAccounting=yes', 'StandardOutput=null', 'StandardError=null', 'LimitFSIZE=2097152',
    'LimitCORE=0', 'LimitNOFILE=64', 'LimitCPU=8', 'LimitAS=536870912', 'NoNewPrivileges=yes')
FIELDS = {'LoadState', 'ActiveState', 'SubState', 'MainPID', 'ExecMainCode', 'ExecMainStatus',
    'Result', 'CPUUsageNSec', 'MemoryPeak', 'TasksCurrent', 'IOReadBytes', 'IOWriteBytes', 'ControlGroup'}
POLICY = {'schema_version': 'research-cli-accounting-policy-v2', 'modes': list(MODES),
    'memory_max_bytes': 134217728, 'swap_max_bytes': 0, 'tasks_max': 8,
    'cpu_quota_usec': 50000, 'cpu_period_usec': 100000, 'unit_runtime_seconds': 15,
    'parent_deadline_seconds': 20, 'helper_timeout_seconds': 3, 'cleanup_helper_timeout_seconds': 3,
    'maximum_receipt_bytes': 64000, 'stdout_stderr': 'null',
    'candidate_execution_enabled': False, 'server_resource_accounting_complete': False,
    'aggregate_disk_quota_enforced': False}


def implementation():
    return {'accounting': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'labels': labels.implementation(), 'allowlist': allowlist.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fixed_cli_accounting_implementation_required')


def _unit(unit):
    if type(unit) is not str or UNIT.fullmatch(unit) is None:
        raise ValueError('generated_research_accounting_unit_required')
    return unit


def _work(mode, pack, output, expected):
    """Fixed child entry; no command/program/provider/source collection arguments."""
    _guard()
    if mode not in MODES or canonical(implementation()) != expected:
        raise ValueError('original_fixed_verifier_required')
    directory = private._safe_directory(Path(output).parent, private=True)
    if Path(output).name != 'result.json' or any((directory/n).exists() for n in ('result.json', 'controls.json')):
        raise ValueError('new_fixed_accounting_outputs_required')
    pack = private._safe_directory(pack, private=True)
    group = Path('/proc/self/cgroup').read_text().strip()
    if not group.startswith('0::/user.slice/') or '\n' in group or UNIT.fullmatch(group.rsplit('/', 1)[-1]) is None:
        raise ValueError('own_accounting_cgroup_required')
    group = group[3:]
    if any(p in ('', '.', '..') for p in group.split('/')[1:]):
        raise ValueError('canonical_accounting_cgroup_required')
    folder = Path('/sys/fs/cgroup')/group.lstrip('/')
    controls = {n: (folder/n).read_text().strip() for n in ('memory.max', 'memory.swap.max', 'pids.max', 'cpu.max')}
    if controls != {'memory.max': '134217728', 'memory.swap.max': '0', 'pids.max': '8', 'cpu.max': '50000 100000'}:
        raise ValueError('fixed_cli_kernel_limits_required')
    files._write(directory, 'controls.json', {'cgroup_path': group, 'controls': controls,
        'limits': {n: list(resource.getrlimit(getattr(resource, 'RLIMIT_'+n))) for n in ('CPU', 'AS', 'FSIZE', 'CORE', 'NOFILE')},
        'environment_keys': sorted(os.environ)})
    report = labels.verify(pack) if mode == 'source_labels' else allowlist.verify(pack)
    _guard()
    files._write(directory, 'result.json', {'schema_version': 'fixed-accounted-verifier-v1', 'mode': mode,
        'pack': str(pack), 'report_sha256': digest(report), 'report_status': report['status'],
        'cgroup_path': group, 'implementation': _LOADED, 'fit_model_provider_or_source_operations': 0,
        'candidate_executed': False, 'native_training_functions_invoked': False})


def _command(unit, mode, pack, output, src):
    _guard(); _unit(unit)
    if mode not in MODES: raise ValueError('closed_offline_verifier_mode_required')
    bootstrap = 'import sys;sys.path.insert(0,'+repr(src)+');from cryptoforge import research_cli_accounting as m;m._work(*sys.argv[1:])'
    return [resources.SYSTEMD_RUN, '--user', '--quiet', '--no-block', '--remain-after-exit',
        '--service-type=exec', '--expand-environment=no', '--unit='+unit,
        *['--property='+v for v in PROPERTIES], '--', resources.ENV, '-i', 'PATH=/usr/bin:/bin',
        'LANG=C.UTF-8', resources.PYTHON, '-B', '-I', '-S', '-c', bootstrap,
        mode, str(pack), str(output), canonical(_LOADED)]


def argv(unit, mode, pack, output):
    # Execution always uses this loaded fixed package. The private reconstruction
    # helper is also used for historical command comparison, never to launch it.
    return _command(unit, mode, pack, output, str(Path(__file__).parents[1]))


def _control(unit, *args):
    _unit(unit)
    return subprocess.run([resources.SYSTEMCTL, '--user', *args, unit], env=resources._environment(),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)


def _show(unit):
    run = _control(unit, 'show', '--property='+','.join(sorted(FIELDS)))
    if run.returncode or len(run.stdout) > 16000: raise ValueError('bounded_accounting_properties_required')
    result = dict(line.split('=', 1) for line in run.stdout.decode().splitlines() if '=' in line)
    exact_fields(result, FIELDS)
    return result


def _quantity(value):
    if value in ('[not set]', '', str(2**64-1)): return None
    if type(value) is not str or re.fullmatch(r'[0-9]{1,20}', value) is None or int(value) >= 2**64-1:
        raise ValueError('bounded_systemd_accounting_quantity_required')
    return int(value)


def final_accounting(observed):
    exact_fields(observed, FIELDS)
    if (any(observed[k] != v for k, v in {'LoadState': 'loaded', 'ActiveState': 'active',
            'SubState': 'exited', 'MainPID': '0', 'ExecMainCode': '1', 'ExecMainStatus': '0', 'Result': 'success'}.items())
            or observed['ControlGroup'] != ''):
        raise ValueError('successfully_exited_fixed_service_required')
    cpu = _quantity(observed['CPUUsageNSec']); memory = _quantity(observed['MemoryPeak'])
    if cpu is None or memory is None or cpu <= 0 or not 0 < memory <= POLICY['memory_max_bytes']:
        raise ValueError('final_cpu_and_memory_peak_required')
    return {'cgroup_cpu_usage_ns': cpu, 'cgroup_charged_memory_peak_bytes': memory,
        'tasks_current': _quantity(observed['TasksCurrent']), 'io_read_bytes': _quantity(observed['IOReadBytes']),
        'io_write_bytes': _quantity(observed['IOWriteBytes']), 'io_unavailable_is_zero': False,
        'measurements_are_systemd_final_cached_cgroup_counters': True,
        'memory_is_sum_of_process_RSS': False, 'server_or_observer_included': False}


def _cleanup(unit):
    failures = []
    for args in (('stop',), ('reset-failed',)):
        try: _control(unit, *args)
        except (OSError, subprocess.SubprocessError): failures.append(args[0])
    try:
        state = _control(unit, 'show', '--property=LoadState', '--value')
        removed = state.stdout.strip() == b'not-found'
    except (OSError, subprocess.SubprocessError):
        removed = False; failures.append('show')
    return {'unit_removed': removed, 'cleanup_helper_failures': failures}


def inspect(directory, mode, pack):
    _guard()
    if mode not in MODES: raise ValueError('closed_offline_verifier_mode_required')
    pack = private._safe_directory(pack, private=True); directory = Path(directory).absolute()
    private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_private_cli_accounting_directory_required')
    directory.mkdir(mode=0o700)
    unit = 'cryptoforge-research-accounting-'+secrets.token_hex(8)+'.service'
    args = argv(unit, mode, pack, directory/'result.json'); runtime = resources._runtime()
    started = time.monotonic(); observed = result = controls = measured = None; cleanup = None; safe_error = None
    own_before = resource.getrusage(resource.RUSAGE_SELF); helpers_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        run = subprocess.run(args, env=resources._environment(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
        if run.returncode or len(run.stdout) > 16000: raise ValueError('fixed_service_start_failed')
        deadline = started+POLICY['parent_deadline_seconds']
        while time.monotonic() < deadline:
            observed = _show(unit)
            if observed['SubState'] in ('exited', 'failed', 'dead'): break
            time.sleep(.2)
        else: raise TimeoutError('fixed_cli_accounting_deadline')
        measured = final_accounting(observed)
        result = labels.values.temporal._read(directory, 'result.json', 64000)
        controls = labels.values.temporal._read(directory, 'controls.json', 64000)
        expected = {'schema_version': 'fixed-accounted-verifier-v1', 'mode': mode, 'pack': str(pack),
            'report_sha256': result.get('report_sha256'), 'report_status': result.get('report_status'),
            'cgroup_path': controls.get('cgroup_path'), 'implementation': _LOADED,
            'fit_model_provider_or_source_operations': 0, 'candidate_executed': False, 'native_training_functions_invoked': False}
        if canonical(result) != canonical(expected): raise ValueError('original_accounted_verifier_result_required')
        labels.values.temporal._sha(result['report_sha256'])
        expected_limits = {'CPU': [8, 8], 'AS': [536870912, 536870912], 'FSIZE': [2097152, 2097152],
            'CORE': [0, 0], 'NOFILE': [64, 64]}
        if (controls != {'cgroup_path': controls['cgroup_path'],
                'controls': {'memory.max': '134217728', 'memory.swap.max': '0', 'pids.max': '8', 'cpu.max': '50000 100000'},
                'limits': expected_limits, 'environment_keys': ['LANG', 'PATH']}
                or not controls['cgroup_path'].endswith('/'+unit)
                or not controls['cgroup_path'].startswith('/user.slice/')
                or (Path('/sys/fs/cgroup')/controls['cgroup_path'].lstrip('/')).exists()):
            raise ValueError('completed_accounting_cgroup_limits_required')
        if resources._runtime() != runtime: raise ValueError('accounting_runtime_changed')
        _guard()
    except (OSError, ValueError, TimeoutError, subprocess.SubprocessError, UnicodeError):
        safe_error = 'fixed_offline_cli_accounting_unavailable'
    finally:
        cleanup = _cleanup(unit)
    own_after = resource.getrusage(resource.RUSAGE_SELF); helpers_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    core = {'schema_version': 'research-cli-accounting-v2', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'fixed_offline_cli_accounted' if safe_error is None and cleanup['unit_removed'] else 'unavailable',
        'safe_error': safe_error, 'mode': mode, 'pack': str(pack), 'unit': unit, 'runtime': runtime,
        'implementation': _LOADED, 'policy_sha256': digest(POLICY), 'argv_sha256': digest(args),
        'unit_final_properties': observed, 'unit_accounting': measured, 'worker_result': result,
        'kernel_controls': controls, 'cleanup': cleanup, 'wall_seconds_including_cleanup': time.monotonic()-started,
        'observer_cpu_seconds': (own_after.ru_utime+own_after.ru_stime)-(own_before.ru_utime+own_before.ru_stime),
        'observer_helper_cpu_seconds': (helpers_after.ru_utime+helpers_after.ru_stime)-(helpers_before.ru_utime+helpers_before.ru_stime),
        'observer_process_lifetime_maxrss_kib': own_after.ru_maxrss,
        'original_package_source_directory': str(Path(__file__).parents[1]),
        'original_private_output_directory': str(directory), 'candidate_execution_enabled': False,
        'sandbox_security_qualified': False, 'aggregate_disk_quota_enforced': False,
        'server_resource_accounting_complete': False, 'provider_called': False, 'fit_performed': False,
        'model_prediction_performed': False, 'new_budget_actions': 0}
    report = {**core, 'receipt_sha256': digest(core)}
    if len(canonical(report).encode()) > 64000: raise ValueError('bounded_cli_accounting_receipt_required')
    files._write(directory, 'receipt.json', report); files._sync(directory)
    return report


def verify(directory):
    """Check original saved final counters and inputs without rerunning any unit."""
    _guard(); directory = private._safe_directory(directory, private=True)
    read = lambda n: labels.values.temporal._read(directory, n, 64000)
    result = read('receipt.json'); core = {k: v for k, v in result.items() if k != 'receipt_sha256'}
    expected_fields = {'schema_version', 'checked_at', 'status', 'safe_error', 'mode', 'pack', 'unit', 'runtime',
        'implementation', 'policy_sha256', 'argv_sha256', 'unit_final_properties', 'unit_accounting', 'worker_result',
        'kernel_controls', 'cleanup', 'wall_seconds_including_cleanup', 'observer_cpu_seconds', 'observer_helper_cpu_seconds',
        'observer_process_lifetime_maxrss_kib', 'original_private_output_directory', 'candidate_execution_enabled',
        'original_package_source_directory',
        'sandbox_security_qualified', 'aggregate_disk_quota_enforced', 'server_resource_accounting_complete',
        'provider_called', 'fit_performed', 'model_prediction_performed', 'new_budget_actions', 'receipt_sha256'}
    exact_fields(result, expected_fields)
    if (result['schema_version'] != 'research-cli-accounting-v2' or result['receipt_sha256'] != digest(core)
            or result['status'] != 'fixed_offline_cli_accounted' or result['safe_error'] is not None
            or result['implementation'] != _LOADED or result['policy_sha256'] != digest(POLICY)
            or result['mode'] not in MODES or result['cleanup']['unit_removed'] is not True
            or result['new_budget_actions'] != 0 or type(result['new_budget_actions']) is not int
            or any(result[k] is not False for k in ('candidate_execution_enabled', 'sandbox_security_qualified',
                'aggregate_disk_quota_enforced', 'server_resource_accounting_complete', 'provider_called',
                'fit_performed', 'model_prediction_performed'))):
        raise ValueError('complete_fixed_cli_accounting_receipt_required')
    _unit(result['unit'])
    if result['runtime'] != resources._runtime(): raise ValueError('original_accounting_runtime_required')
    original = private._safe_directory(result['original_private_output_directory'], private=True)
    source = private._safe_directory(result['original_package_source_directory'])
    original_module = source/'cryptoforge/research_cli_accounting.py'
    if allowlist.mounts._hash_file(original_module)['sha256'] != _LOADED['accounting']:
        raise ValueError('original_accounting_package_source_required')
    command = _command(result['unit'], result['mode'], result['pack'], original/'result.json', str(source))
    if result['argv_sha256'] != digest(command):
        raise ValueError('original_fixed_accounting_command_required')
    controls = read('controls.json'); worker = read('result.json')
    for n, saved in (('controls.json', controls), ('result.json', worker)):
        if labels.values.temporal._read(original, n, 64000) != saved:
            raise ValueError('original_accounting_output_binding_required')
    if worker != result['worker_result'] or controls != result['kernel_controls']:
        raise ValueError('original_accounting_worker_evidence_required')
    if final_accounting(result['unit_final_properties']) != result['unit_accounting']:
        raise ValueError('final_accounting_counters_changed')
    group = controls['cgroup_path']
    if (not group.startswith('/user.slice/') or not group.endswith('/'+result['unit'])
            or any(p in ('', '.', '..') for p in group.split('/')[1:])
            or (Path('/sys/fs/cgroup')/group.lstrip('/')).exists()):
        raise ValueError('original_accounting_cgroup_cleanup_required')
    expected_controls = {'memory.max': '134217728', 'memory.swap.max': '0', 'pids.max': '8', 'cpu.max': '50000 100000'}
    expected_limits = {'CPU': [8, 8], 'AS': [536870912, 536870912], 'FSIZE': [2097152, 2097152],
        'CORE': [0, 0], 'NOFILE': [64, 64]}
    if controls != {'cgroup_path': group, 'controls': expected_controls, 'limits': expected_limits, 'environment_keys': ['LANG', 'PATH']}:
        raise ValueError('original_cli_kernel_limits_required')
    pack = private._safe_directory(result['pack'], private=True)
    if result['mode'] == 'source_labels':
        read_pack = lambda n, size: labels.values.temporal._read(pack, n, size)
        binding = read_pack('binding.json', 16000); bound = labels.bind(binding['directory'])
        if (binding != bound[0] or read_pack('policy.json', 16000) != labels.POLICY
                or read_pack('spec.json', 16000) != labels.reference.SPEC
                or read_pack('selection.json', 2097152) != bound[2] or read_pack('target.json', 4000) != bound[5]):
            raise ValueError('original_label_pack_binding_required')
        report = labels.compose(*bound, read_pack('oracle.json', 262144))
        if report != read_pack('audit.json', 262144): raise ValueError('original_label_audit_required')
    else:
        report = allowlist.verify(pack)
    if worker != {'schema_version': 'fixed-accounted-verifier-v1', 'mode': result['mode'], 'pack': str(pack),
            'report_sha256': digest(report), 'report_status': report['status'], 'cgroup_path': group,
            'implementation': _LOADED, 'fit_model_provider_or_source_operations': 0,
            'candidate_executed': False, 'native_training_functions_invoked': False}:
        raise ValueError('original_verified_pack_accounting_required')
    for k in ('wall_seconds_including_cleanup', 'observer_cpu_seconds', 'observer_helper_cpu_seconds'):
        if type(result[k]) not in (int, float) or not math.isfinite(result[k]) or result[k] < 0:
            raise ValueError('finite_nonnegative_observer_measurement_required')
    if type(result['observer_process_lifetime_maxrss_kib']) is not int or result['observer_process_lifetime_maxrss_kib'] < 0:
        raise ValueError('observer_process_lifetime_RSS_required')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'inspect':
            command.add_argument('--mode', choices=MODES, required=True); command.add_argument('--pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect(args.directory, args.mode, args.pack) if args.command == 'inspect' else verify(args.directory)
    except Exception:
        print('Fixed offline CLI accounting refused; candidate execution disabled'); return 2
    print('Fixed offline CLI accounting: '+result['status']+'; server/global accounting incomplete')
    return 0 if result['status'] == 'fixed_offline_cli_accounted' else 2


if __name__ == '__main__':
    raise SystemExit(main())
