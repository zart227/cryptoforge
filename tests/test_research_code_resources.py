from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

import pytest

from cryptoforge import research_code_resources as resources
from cryptoforge.research_training_diagnostics import digest


UNIT = 'cryptoforge-research-resource-' + 'a' * 16 + '.scope'


def child(mode='observe'):
    checks = {name: True for name in ('memory_max_configured', 'swap_disabled', 'tasks_max_configured',
        'cpu_quota_configured', 'network_namespace_differs', 'only_loopback', 'private_database_paths_hidden',
        'environment_cleared', 'controller_mount_readonly', 'local_database_ports_unreachable',
        'capabilities_dropped', 'no_new_privileges')}
    checks['task_limit_enforced' if mode == 'observe' else 'timeout_child_ignores_sigterm'] = True
    return {'schema_version': 'trusted-resource-child-v1', 'mode': mode, 'unit': UNIT,
        'cgroup_path': '/user.slice/user-1000.slice/user@1000.service/app.slice/' + UNIT,
        'controls': {'memory.max': '67108864', 'memory.swap.max': '0', 'pids.max': '8', 'cpu.max': '25000 100000'},
        'checks': checks, 'created_children': 1, 'python_version': '3.12.3'}


def mock_process(monkeypatch, *, mode='observe', value=None, raw=None, returncode=None, communicate_error=None):
    calls = []
    class Process:
        pid = 12345
        def __init__(self, argv, **kwargs):
            calls.append(('start', argv, kwargs))
            self.returncode = None if communicate_error is not None else (0 if mode == 'observe' else -signal.SIGTERM)
            if returncode is not None: self.returncode = returncode
            self.waits = 0
        def communicate(self, **kwargs):
            self.waits += 1; calls.append(('communicate', kwargs))
            if communicate_error is not None and self.waits == 1: raise communicate_error
            self.returncode = -signal.SIGKILL if communicate_error is not None else self.returncode
            return (json.dumps(child(mode) if value is None else value).encode() if raw is None else raw), None
        def poll(self): return self.returncode
    monkeypatch.setattr(resources.subprocess, 'Popen', Process)
    monkeypatch.setattr(resources.secrets, 'token_hex', lambda size: 'a' * 16)
    monkeypatch.setattr(resources, 'cleanup', lambda unit: calls.append(('cleanup', unit)) or {'unit_removed': True, 'stop_returncode': 5})
    ticks = iter([0.0, 4.1]); monkeypatch.setattr(resources.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(resources.os, 'killpg', lambda pid, sig: calls.append(('killpg', pid, sig)))
    return calls


def test_fixed_scope_argv_clears_environment_and_limits_entire_tree(monkeypatch):
    monkeypatch.setenv('CRYPTOFORGE_LOCAL_API_KEY', 'never-inherited')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'never-inherited-either')
    argv = resources.probe_argv(UNIT, 'observe', 'net:[123]')
    assert argv[:3] == ['/usr/bin/systemd-run', '--user', '--scope']
    for value in ('MemoryMax=67108864', 'MemorySwapMax=0', 'TasksMax=8', 'CPUQuota=25%',
        'CPUQuotaPeriodSec=100ms', 'RuntimeMaxSec=3s', 'TimeoutStopSec=1s', 'SendSIGKILL=yes'):
        assert '--property=' + value in argv
    assert '--collect' in argv and '--expand-environment=no' in argv
    assert argv[argv.index('--') + 1:][:2] == ['/usr/bin/env', '-i']
    assert 'never-inherited' not in repr(argv) + repr(resources._environment())
    assert 'never-inherited-either' not in repr(argv) + repr(resources._environment())


@pytest.mark.parametrize('unit', ['other.service', 'cryptoforge-executor.service', UNIT + '/x',
    '../' + UNIT, UNIT.replace('.scope', '.service'), UNIT.replace('a' * 16, 'z' * 16)])
def test_cleanup_and_argv_reject_units_outside_generated_scope_allowlist(unit):
    with pytest.raises(ValueError): resources.probe_argv(unit, 'observe', 'net:[123]')
    with pytest.raises(ValueError): resources.cleanup(unit)


@pytest.mark.parametrize('mode,namespace', [('execute', 'net:[123]'), ('observe', 'net:broken'), ('sh', 'net:[1]')])
def test_no_arbitrary_command_or_namespace_input(mode, namespace):
    with pytest.raises(ValueError): resources.probe_argv(UNIT, mode, namespace)


def test_cleanup_stops_only_own_unit_and_checks_removal(monkeypatch):
    calls = []
    def control(*args):
        calls.append(args)
        return SimpleNamespace(returncode=5 if args[0] == 'stop' else 0, stdout=b'not-found\n')
    monkeypatch.setattr(resources, '_control', control)
    assert resources.cleanup(UNIT)['unit_removed']
    assert calls == [('stop', UNIT), ('show', '--property=LoadState', '--value', UNIT)]


def test_cleanup_escalates_stop_timeout_to_kill_entire_own_group(monkeypatch):
    calls = []
    def control(*args):
        calls.append(args)
        if len(calls) == 1: raise subprocess.TimeoutExpired('systemctl', 3)
        return SimpleNamespace(returncode=0, stdout=b'not-found\n')
    monkeypatch.setattr(resources, '_control', control)
    assert resources.cleanup(UNIT)['unit_removed']
    assert calls[1:3] == [('kill', '--kill-whom=all', '--signal=KILL', UNIT), ('stop', UNIT)]


@pytest.mark.parametrize('mode', ['observe', 'timeout_tree'])
def test_valid_observations_require_controls_and_cleanup_and_keep_execution_disabled(monkeypatch, mode):
    calls = mock_process(monkeypatch, mode=mode)
    result = resources.run_probe(mode)
    assert result['observation']['checks']['local_database_ports_unreachable']
    assert result['cgroup_removed'] and result['cleanup']['unit_removed']
    assert result['runtime_deadline_tree_observed'] == (mode == 'timeout_tree')
    assert ('cleanup', UNIT) in calls
    kwargs = calls[0][2]
    assert kwargs['stdin'] == subprocess.DEVNULL and kwargs['stderr'] == subprocess.DEVNULL
    assert kwargs['close_fds'] and kwargs['start_new_session']


@pytest.mark.parametrize('exception', [subprocess.TimeoutExpired('probe', 8), KeyboardInterrupt(), OSError('private')])
def test_parent_timeout_or_interruption_always_cleans_scope_and_reaps_supervisor(monkeypatch, exception):
    calls = mock_process(monkeypatch, communicate_error=exception)
    with pytest.raises(type(exception)): resources.run_probe('observe')
    assert ('cleanup', UNIT) in calls
    assert ('killpg', 12345, signal.SIGKILL) in calls
    assert len([call for call in calls if call[0] == 'communicate']) == 2


@pytest.mark.parametrize('mutation', ['false_check', 'memory', 'tasks', 'cpu', 'unit', 'mode', 'path',
    'python', 'children_boolean', 'children_too_many', 'extra_check', 'extra_field'])
def test_changed_or_incomplete_runtime_observation_is_never_ready(monkeypatch, mutation):
    value = child()
    if mutation == 'false_check': value['checks']['network_namespace_differs'] = False
    elif mutation == 'memory': value['controls']['memory.max'] = 'max'
    elif mutation == 'tasks': value['controls']['pids.max'] = 'max'
    elif mutation == 'cpu': value['controls']['cpu.max'] = 'max 100000'
    elif mutation == 'unit': value['unit'] = 'other.scope'
    elif mutation == 'mode': value['mode'] = 'execute'
    elif mutation == 'path': value['cgroup_path'] = '/user.slice/../../' + UNIT
    elif mutation == 'python': value['python_version'] = 'unknown'
    elif mutation == 'children_boolean': value['created_children'] = True
    elif mutation == 'children_too_many': value['created_children'] = 100
    elif mutation == 'extra_check': value['checks']['unchecked'] = True
    else: value['commands'] = ['execute']
    mock_process(monkeypatch, value=value)
    with pytest.raises(ValueError): resources.run_probe('observe')


@pytest.mark.parametrize('raw', [b'{}', b'not json', b'0' * 32001])
def test_invalid_or_oversized_output_is_rejected_after_cleanup(monkeypatch, raw):
    calls = mock_process(monkeypatch, raw=raw)
    with pytest.raises(ValueError): resources.run_probe('observe')
    assert ('cleanup', UNIT) in calls


def test_non_timeout_exit_cannot_be_presented_as_scope_deadline(monkeypatch):
    mock_process(monkeypatch, mode='timeout_tree', returncode=0)
    with pytest.raises(ValueError): resources.run_probe('timeout_tree')


def test_missing_runtime_has_no_host_process_fallback_and_writes_private_receipt(tmp_path, monkeypatch):
    def missing(): raise OSError('runtime absent')
    monkeypatch.setattr(resources, '_runtime', missing)
    monkeypatch.setattr(resources.subprocess, 'Popen', lambda *a, **k: pytest.fail('no host fallback'))
    directory = tmp_path / 'readiness'; result = resources.inspect(directory)
    assert result['status'] == 'unavailable' and not result['candidate_execution_enabled']
    assert not result['candidate_executed'] and not result['execution_authorized']
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / 'readiness.json').stat().st_mode & 0o777 == 0o600
    assert result['receipt_sha256'] == digest({key: value for key, value in result.items() if key != 'receipt_sha256'})
    with pytest.raises(FileExistsError): resources.inspect(directory)


def test_unchecked_systemd_profile_is_rejected_without_probes(tmp_path, monkeypatch):
    monkeypatch.setattr(resources, '_runtime', lambda: {'synthetic': 'a' * 64})
    monkeypatch.setattr(resources.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'unknown\n'))
    monkeypatch.setattr(resources, 'run_probe', lambda *args: pytest.fail('unchecked profile'))
    assert resources.inspect(tmp_path / 'profile')['status'] == 'unavailable'


def test_unremoved_scope_prevents_a_successful_result(monkeypatch):
    mock_process(monkeypatch)
    monkeypatch.setattr(resources, 'cleanup', lambda unit: {'unit_removed': False, 'stop_returncode': 0})
    with pytest.raises(ValueError): resources.run_probe('observe')


def test_policy_file_does_not_enable_candidate_execution():
    assert json.loads(Path('config/research-code-resources-v1.json').read_text()) == resources.POLICY
    assert resources.POLICY['candidate_execution_enabled'] is False
    assert resources.POLICY['shared_candidate_budget_integrated'] is False


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS') != '1', reason='explicit trusted host cgroup probe opt-in')
def test_actual_trusted_cgroup_tree_and_local_database_isolation(tmp_path):
    result = resources.inspect(tmp_path / 'real-trusted-cgroups')
    assert result['status'] == 'trusted_resource_controls_observed'
    assert len(result['probes']) == 2
    assert all(all(probe['observation']['checks'].values()) for probe in result['probes'])
    assert all(probe['cgroup_removed'] and probe['cleanup']['unit_removed'] for probe in result['probes'])
    assert result['probes'][0]['observation']['checks']['task_limit_enforced']
    assert result['probes'][1]['observation']['checks']['timeout_child_ignores_sigterm']
    assert result['probes'][1]['runtime_deadline_tree_observed']
    assert not result['candidate_execution_enabled'] and result['database_connections'] == 0
    assert not result['shared_candidate_budget_integrated'] and not result['security_audit_completed']
