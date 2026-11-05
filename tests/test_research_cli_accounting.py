"""Final counters cover fixed verifier descendants; missing IO remains unknown."""
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import shutil
import subprocess

import pytest
from cryptoforge import research_cli_accounting as m
from cryptoforge.research_training_diagnostics import canonical, digest
from test_research_revision_bridge import native_fixture
from test_research_value_audit import value_base
from test_research_label_oracle import label_base


def properties():
    return {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'exited', 'MainPID': '0',
        'ExecMainCode': '1', 'ExecMainStatus': '0', 'Result': 'success', 'ControlGroup': '',
        'CPUUsageNSec': '123456', 'MemoryPeak': '1048576', 'TasksCurrent': '[not set]',
        'IOReadBytes': '[not set]', 'IOWriteBytes': '[not set]'}


def test_final_cpu_and_cgroup_charge_peak_are_not_RSS_or_server_cost():
    result = m.final_accounting(properties())
    assert result['cgroup_cpu_usage_ns'] == 123456 and result['cgroup_charged_memory_peak_bytes'] == 1048576
    assert result['tasks_current'] is result['io_read_bytes'] is result['io_write_bytes'] is None
    assert not result['memory_is_sum_of_process_RSS'] and not result['server_or_observer_included']
    p = properties(); p.update(IOReadBytes='0', IOWriteBytes='19')
    assert m.final_accounting(p)['io_read_bytes'] == 0 and m.final_accounting(p)['io_write_bytes'] == 19


@pytest.mark.parametrize('value', ['', '[not set]', str(2**64-1)])
def test_unavailable_quantities_remain_null(value):
    assert m._quantity(value) is None


@pytest.mark.parametrize('value', ['-1', '1.2', 'NaN', str(2**64), True, 1])
def test_non_uint64_quantities_are_refused(value):
    with pytest.raises(ValueError): m._quantity(value)


@pytest.mark.parametrize('key,value', [
    ('CPUUsageNSec', '[not set]'), ('MemoryPeak', '[not set]'), ('MemoryPeak', '134217729'),
    ('MainPID', '123'), ('SubState', 'running'), ('ExecMainStatus', '1'), ('ControlGroup', '/still-running'),
])
def test_final_snapshot_requires_actual_successful_exit_and_available_bounded_counters(key, value):
    p = properties(); p[key] = value
    with pytest.raises(ValueError): m.final_accounting(p)


def test_only_closed_modes_generated_units_and_fixed_resource_flags(tmp_path):
    unit = 'cryptoforge-research-accounting-'+'a'*16+'.service'
    args = m.argv(unit, 'source_labels', tmp_path/'pack', tmp_path/'result.json')
    assert '--remain-after-exit' in args and '--no-block' in args and '--service-type=exec' in args
    assert '--wait' not in args and '--scope' not in args
    assert '--property=MemoryMax=134217728' in args and '--property=CPUQuota=50%' in args
    assert '--property=StandardOutput=null' in args and '--property=StandardError=null' in args
    with pytest.raises(ValueError): m.argv(unit, 'candidate_python', tmp_path, tmp_path/'result.json')
    with pytest.raises(ValueError): m.argv('cryptoforge-supabase-executor.service', 'source_labels', tmp_path, tmp_path/'result.json')


def test_control_rejects_other_user_units_before_running_any_helper(monkeypatch):
    monkeypatch.setattr(m.subprocess, 'run', lambda *_a, **_k: pytest.fail('unrelated unit must not be touched'))
    with pytest.raises(ValueError): m._control('cryptoforge-supabase-executor.service', 'stop')


def test_failed_start_preserves_private_unavailable_receipt_and_cleans_own_unit(tmp_path, monkeypatch):
    called = []; pack = tmp_path/'input'; pack.mkdir(mode=0o700)
    monkeypatch.setattr(m.subprocess, 'run', lambda *_a, **_k: subprocess.CompletedProcess([], 1, b''))
    monkeypatch.setattr(m, '_cleanup', lambda unit: called.append(unit) or {'unit_removed': True, 'cleanup_helper_failures': []})
    result = m.inspect(tmp_path/'probe', 'source_labels', pack)
    assert result['status'] == 'unavailable' and result['unit_accounting'] is None
    assert len(called) == 1 and m.UNIT.fullmatch(called[0])
    assert stat.S_IMODE((tmp_path/'probe').stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path/'probe/receipt.json').stat().st_mode) == 0o600
    with pytest.raises(ValueError): m.verify(tmp_path/'probe')


def test_interruption_still_cleans_generated_unit(tmp_path, monkeypatch):
    called = []; pack = tmp_path/'input'; pack.mkdir(mode=0o700)
    def interrupted(*args, **kwargs): raise KeyboardInterrupt()
    monkeypatch.setattr(m.subprocess, 'run', interrupted)
    monkeypatch.setattr(m, '_cleanup', lambda unit: called.append(unit) or {'unit_removed': True, 'cleanup_helper_failures': []})
    with pytest.raises(KeyboardInterrupt): m.inspect(tmp_path/'probe', 'source_labels', pack)
    assert len(called) == 1 and m.UNIT.fullmatch(called[0])


def test_cleanup_helper_failure_is_recorded_without_claiming_removal(monkeypatch):
    monkeypatch.setattr(m, '_control', lambda *_a: (_ for _ in ()).throw(subprocess.TimeoutExpired('fixed', 3)))
    result = m._cleanup('cryptoforge-research-accounting-'+'a'*16+'.service')
    assert not result['unit_removed'] and result['cleanup_helper_failures'] == ['stop', 'reset-failed', 'show']


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_CGROUPS') != '1', reason='explicit fixed cgroup opt-in')
@pytest.mark.parametrize('mode', ['source_labels', 'syscall_allowlist'])
def test_real_entire_fixed_verifier_and_child_cpu_memory_immutable_replay(mode, label_base, tmp_path, monkeypatch):
    if mode == 'source_labels':
        pack = tmp_path/'labels'; m.labels.prepare(pack, label_base[0])
    else:
        pack = tmp_path/'filter'; assert m.allowlist.inspect(pack)['status'] == 'trusted_syscall_allowlist_probe_observed'
    result = m.inspect(tmp_path/'accounting', mode, pack)
    assert result['status'] == 'fixed_offline_cli_accounted' and result['cleanup']['unit_removed']
    assert result['unit_accounting']['cgroup_cpu_usage_ns'] > 0
    assert 0 < result['unit_accounting']['cgroup_charged_memory_peak_bytes'] <= 134217728
    assert result['kernel_controls']['controls']['cpu.max'] == '50000 100000'
    monkeypatch.setattr(m, '_control', lambda *_a: pytest.fail('offline verification must not contact systemd'))
    # Same reviewed bytes loaded from another checkout must reconstruct the
    # original command with its recorded package directory, without executing it.
    relocated = tmp_path/'other-checkout/src/cryptoforge/research_cli_accounting.py'
    relocated.parent.mkdir(parents=True)
    shutil.copyfile(m.__file__, relocated)
    monkeypatch.setattr(m, '__file__', str(relocated))
    assert m.verify(tmp_path/'accounting') == result
    forged = deepcopy(result); forged['aggregate_disk_quota_enforced'] = True
    forged['receipt_sha256'] = digest({k: v for k, v in forged.items() if k != 'receipt_sha256'})
    (tmp_path/'accounting/receipt.json').write_text(canonical(forged))
    with pytest.raises(ValueError): m.verify(tmp_path/'accounting')


def test_frozen_config_and_cli_safe_missing_pack_refusal(tmp_path, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-cli-accounting-v2.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out


def test_execution_argv_cannot_select_a_foreign_package_directory(tmp_path):
    unit = 'cryptoforge-research-accounting-'+'a'*16+'.service'
    command = m.argv(unit, 'source_labels', tmp_path, tmp_path/'result.json')
    bootstrap = command[command.index('-c')+1]
    assert repr(str(Path(m.__file__).parents[1])) in bootstrap
    assert 'original_package_source_directory' not in bootstrap
