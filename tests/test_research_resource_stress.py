"""Fixed stress counter evidence, isolation, interruption and scoped cleanup."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

import pytest

from cryptoforge import research_resource_stress as m


UNIT = 'cryptoforge-research-stress-'+'a'*16+'.scope'


def child(mode='memory_oom'):
    before = {'memory_events': {'max': 0, 'oom': 0, 'oom_kill': 0},
        'cpu': {'usage_usec': 10000, 'user_usec': 8000, 'system_usec': 2000, 'nr_periods': 1,
                'nr_throttled': 0, 'throttled_usec': 0},
        'memory_current_bytes': 12000000, 'memory_peak_bytes': 12000000, 'memory_swap_current_bytes': 0}
    after = deepcopy(before)
    after['cpu'].update(usage_usec=310000, user_usec=308000, nr_periods=14, nr_throttled=10, throttled_usec=800000)
    if mode == 'memory_oom':
        after['memory_events'] = {'max': 25, 'oom': 1, 'oom_kill': 1}; after['memory_peak_bytes'] = 67108864
    return {'schema_version': 'research-resource-stress-child-v1', 'mode': mode, 'unit': UNIT,
        'cgroup_path': '/user.slice/user-1000.slice/user@1000.service/app.slice/'+UNIT,
        'limits': {'memory.max': '67108864', 'memory.swap.max': '0', 'pids.max': '8',
                   'cpu.max': '25000 100000', 'memory.oom.group': '0'},
        'checks': {name: True for name in m.CHECKS}, 'before': before, 'after': after,
        'allocator_child_exit': -9 if mode == 'memory_oom' else None,
        'cpu_burn_wall_seconds': None if mode == 'memory_oom' else 1.3, 'python_version': '3.12.3'}


def fake_process(monkeypatch, *, mode='memory_oom', value=None, error=None):
    calls = []; process = None
    class Process:
        pid = 43210; returncode = None; waits = 0
        def __init__(self, argv, **kwargs): calls.append(('start', argv, kwargs))
        def communicate(self, timeout=None):
            self.waits += 1; calls.append(('communicate', timeout))
            if error is not None and self.waits == 1: raise error
            self.returncode = 0
            return json.dumps(child(mode) if value is None else value).encode(), None
        def poll(self): return self.returncode
    process = Process.__new__(Process)
    def popen(argv, **kwargs): Process.__init__(process, argv, **kwargs); return process
    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    monkeypatch.setattr(m.secrets, 'token_hex', lambda size: 'a'*16)
    monkeypatch.setattr(m.os, 'readlink', lambda path: 'net:[123]')
    monkeypatch.setattr(m, 'cleanup', lambda unit: calls.append(('cleanup', unit)) or {'unit_removed': True})
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: calls.append(('killpg', pid, sig)))
    return calls


@pytest.mark.parametrize('mode', ['memory_oom', 'cpu_throttle'])
def test_kernel_counters_validate_mechanism_and_scoped_cleanup(monkeypatch, mode):
    calls = fake_process(monkeypatch, mode=mode)
    result = m.run_probe(mode)
    assert result['cleanup'] == {'unit_removed': True} and result['cgroup_removed']
    assert result['counter_delta']['memory_events']['oom_kill'] == (1 if mode == 'memory_oom' else 0)
    assert result['counter_delta']['cpu']['nr_throttled'] == 10
    assert ('cleanup', UNIT) in calls
    assert calls[0][2]['stdin'] == subprocess.DEVNULL and calls[0][2]['start_new_session']
    assert result['accounting_scope'].endswith('excludes_supervisor_cli_control_and_cleanup')


def test_fixed_commands_and_headroom_preflight_have_no_candidate_input(monkeypatch):
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'must-not-inherit')
    argv = m.probe_argv(UNIT, 'memory_oom', 'net:[123]')
    for prop in ('MemoryMax=67108864', 'MemorySwapMax=0', 'TasksMax=8', 'CPUQuota=25%', 'RuntimeMaxSec=5s', 'OOMPolicy=continue'):
        assert '--property='+prop in argv
    assert 'must-not-inherit' not in repr(argv)+repr(m.controls._environment())
    assert "int(limit)-current>=335544320" in m.LAUNCHER
    assert 'available>=335544320' in m.LAUNCHER
    assert 'range(12)' in m.INNER and '8*1024*1024' in m.INNER
    assert m.POLICY['candidate_execution_enabled'] is False


@pytest.mark.parametrize('unit', ['cryptoforge-executor.service', '../'+UNIT, UNIT+'/x', UNIT.replace('.scope', '.service')])
def test_other_units_cannot_be_started_or_cleaned(unit):
    with pytest.raises(ValueError): m.probe_argv(unit, 'memory_oom', 'net:[123]')
    with pytest.raises(ValueError): m.cleanup(unit)


@pytest.mark.parametrize('mode,namespace', [('execute', 'net:[123]'), ('memory_oom', '../path'), ('sh', 'net:[1]')])
def test_arbitrary_command_namespace_modes_rejected(mode, namespace):
    with pytest.raises(ValueError): m.probe_argv(UNIT, mode, namespace)


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('probe', 10), KeyboardInterrupt(), OSError('private-path')])
def test_timeout_or_cancellation_cleans_scope_and_reaps_supervisor(monkeypatch, failure):
    calls = fake_process(monkeypatch, error=failure)
    with pytest.raises(type(failure)): m.run_probe('memory_oom')
    assert ('cleanup', UNIT) in calls and ('killpg', 43210, signal.SIGKILL) in calls
    assert sum(call[0] == 'communicate' for call in calls) == 2


@pytest.mark.parametrize('change', [
    lambda v: v['checks'].update(network_namespace_differs=False),
    lambda v: v['limits'].update({'memory.max': 'max'}),
    lambda v: v['limits'].update({'memory.oom.group': '1'}),
    lambda v: v.update(allocator_child_exit=0),
    lambda v: v.update(allocator_child_exit=True),
    lambda v: v['after']['memory_events'].update(oom_kill=0),
    lambda v: v['after']['memory_events'].update(oom=0),
    lambda v: v['after']['memory_events'].update(max=0),
    lambda v: v['after']['cpu'].update(usage_usec=0),
    lambda v: v['after'].update(memory_swap_current_bytes=4096),
    lambda v: v['after'].update(memory_peak_bytes=1),
    lambda v: v['after']['memory_events'].update(oom_kill=True),
    lambda v: v.update(cgroup_path='/user.slice/../'+UNIT),
    lambda v: v.update(python_version='other'),
])
def test_oom_claim_requires_positive_kernel_events_exact_controls_and_signal(change):
    value = child(); change(value)
    with pytest.raises(ValueError): m.validate_observation(value, UNIT, 'memory_oom')


@pytest.mark.parametrize('change', [
    lambda v: v['after']['cpu'].update(nr_throttled=0),
    lambda v: v['after']['cpu'].update(throttled_usec=0),
    lambda v: v['after']['cpu'].update(usage_usec=10000),
    lambda v: v.update(cpu_burn_wall_seconds=0),
    lambda v: v.update(cpu_burn_wall_seconds=float('nan')),
    lambda v: v['after']['memory_events'].update(oom_kill=1),
])
def test_cpu_claim_requires_actual_throttling_and_no_oom(change):
    value = child('cpu_throttle'); change(value)
    with pytest.raises(ValueError): m.validate_observation(value, UNIT, 'cpu_throttle')


def test_cleanup_retries_a_nonzero_stop_if_scope_still_loaded(monkeypatch):
    calls = []
    def control(*args):
        calls.append(args)
        return SimpleNamespace(returncode=1, stdout=b'loaded\n' if len(calls) == 2 else b'not-found\n')
    monkeypatch.setattr(m.controls, '_control', control)
    assert m.cleanup(UNIT) == {'unit_removed': True}
    assert calls == [('stop', UNIT), ('show', '--property=LoadState', '--value', UNIT),
        ('kill', '--kill-whom=all', '--signal=KILL', UNIT), ('stop', UNIT),
        ('show', '--property=LoadState', '--value', UNIT)]


def test_missing_runtime_writes_unavailable_private_receipt_without_host_fallback(tmp_path, monkeypatch):
    def missing(): raise OSError('private-path')
    monkeypatch.setattr(m.controls, '_runtime', missing)
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *a, **k: pytest.fail('no unrestricted host fallback'))
    report = m.inspect(tmp_path/'pack')
    assert report['status'] == 'unavailable' and report['candidate_execution_enabled'] is False
    assert not report['memory_oom_stress_tested'] and not report['cpu_throttle_stress_tested']
    assert (tmp_path/'pack').stat().st_mode & 0o777 == 0o700
    assert (tmp_path/'pack/stress.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match='successful_original_stress'): m.verify(tmp_path/'pack')


def test_unremoved_scope_cannot_be_a_successful_probe(monkeypatch):
    fake_process(monkeypatch)
    monkeypatch.setattr(m, 'cleanup', lambda unit: {'unit_removed': False})
    with pytest.raises(ValueError, match='cleanup_incomplete'): m.run_probe('memory_oom')


def test_policy_config_and_safe_cli_failure(tmp_path, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-resource-stress-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'private-secret-path')]) == 2
    assert 'private-secret-path' not in capsys.readouterr().out


@pytest.mark.parametrize('change', [
    lambda r: r.update(execution_authorized=True),
    lambda r: r.update(database_connections=1),
    lambda r: r.update(memory_oom_stress_tested=False),
    lambda r: r.update(profile=['unknown']),
    lambda r: r['probes'][0].update(argv_sha256='a'*64),
    lambda r: r['probes'][0].update(cgroup_removed=False),
    lambda r: r['probes'][0].update(returncode=False),
    lambda r: r['probes'][0].update(observed_wall_seconds=-1),
    lambda r: r['probes'][0].update(accounting_scope='entire_host'),
])
def test_rehashed_receipt_cannot_upgrade_claims_or_change_kernel_evidence(tmp_path, monkeypatch, change):
    runtime = {key: 'b'*64 for key in ('systemd_run', 'systemctl', 'bwrap', 'python', 'env')}
    monkeypatch.setattr(m.controls, '_runtime', lambda: runtime)
    profiles = iter(['systemd 255 (255.4-1ubuntu8.18)', 'bubblewrap 0.9.0', '255.4-1ubuntu8.18'])
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=(next(profiles)+'\n').encode()))
    def probe(mode):
        observation = child(mode)
        return {'mode': mode, 'unit': UNIT, 'argv_sha256': m.digest(m.probe_argv(UNIT, mode, 'net:[123]')),
            'returncode': 0, 'parent_net_namespace': 'net:[123]', 'observation': observation,
            'counter_delta': m.validate_observation(observation, UNIT, mode), 'cleanup': {'unit_removed': True},
            'cgroup_removed': True, 'observed_wall_seconds': 1.5,
            'accounting_scope': 'diagnostic_scope_to_after_snapshot_excludes_supervisor_cli_control_and_cleanup'}
    monkeypatch.setattr(m, 'run_probe', probe)
    report = m.inspect(tmp_path/'pack')
    assert report['status'] == 'trusted_stress_observed' and m.verify(tmp_path/'pack') == report
    change(report); report['receipt_sha256'] = m.digest({key: value for key, value in report.items() if key != 'receipt_sha256'})
    (tmp_path/'pack/stress.json').write_text(m.canonical(report)+'\n')
    with pytest.raises(ValueError): m.verify(tmp_path/'pack')


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS') != '1', reason='explicit bounded trusted stress opt-in')
def test_actual_bounded_oom_cpu_throttle_and_offline_receipt(tmp_path, monkeypatch):
    result = m.inspect(tmp_path/'actual')
    assert result['status'] == 'trusted_stress_observed', result
    monkeypatch.setattr(m, 'run_probe', lambda *_: pytest.fail('verify must not rerun stress'))
    assert m.verify(tmp_path/'actual') == result
    assert result['memory_oom_stress_tested'] and result['cpu_throttle_stress_tested']
    assert result['probes'][0]['counter_delta']['memory_events']['oom_kill'] >= 1
    assert result['probes'][1]['counter_delta']['cpu']['nr_throttled'] > 0
    assert all(probe['cleanup']['unit_removed'] and probe['cgroup_removed'] for probe in result['probes'])
    assert not result['candidate_executed'] and not result['execution_authorized']
    assert not result['full_cli_accounting_verified'] and not result['security_audit_completed']
