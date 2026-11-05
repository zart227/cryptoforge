import json
import os
from pathlib import Path
import signal
import subprocess
from types import SimpleNamespace

import pytest

from cryptoforge import research_code_isolation as isolation


def test_probe_has_fixed_script_routes_and_no_command_or_candidate_argument(tmp_path):
    argv = isolation.probe_argv(tmp_path/'canary', {key: 'synthetic' for key in ('net','pid','user','mnt')})
    assert argv[0] == '/usr/bin/bwrap' and argv[argv.index('--')+1:] == [
        '/usr/bin/python3', '-I', '-S', '-c', isolation.PROBE,
        '{"mnt":"synthetic","net":"synthetic","pid":"synthetic","user":"synthetic"}']
    for flag in ('--unshare-all','--unshare-user','--disable-userns','--assert-userns-disabled',
                 '--die-with-parent','--new-session','--clearenv','--remount-ro','--cap-drop'):
        assert flag in argv
    assert '--share-net' not in argv and '--bind' not in argv and '--dev-bind' not in argv
    assert '/home' not in argv and '/run' not in argv and '/workspace' not in argv


def test_missing_runtime_is_recorded_without_host_fallback_or_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, '_runtime', lambda: (_ for _ in ()).throw(FileNotFoundError('synthetic missing runtime')))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('no host fallback'))
    root=tmp_path/'probe'; result=isolation.inspect(root)
    assert result['status']=='unavailable' and result['safe_error']=='trusted_probe_unavailable_or_unchecked_profile'
    assert result['trusted_probe_only'] and not result['candidate_execution_enabled'] and not result['execution_authorized']
    assert (root/'canary.txt').read_bytes()==isolation.CANARY
    assert (root/'readiness.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError): isolation.inspect(root)


def test_unknown_version_refuses_before_process_and_keeps_source_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(isolation, '_runtime', lambda: {'fixture': True})
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'bubblewrap 999.0\n'))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('unknown runtime must not run probe'))
    result = isolation.inspect(tmp_path/'probe')
    assert result['status']=='unavailable' and not result['candidate_executed']


def test_timeout_kills_and_reaps_only_fixed_probe_group_without_retry(tmp_path, monkeypatch):
    calls=[]
    class Process:
        pid=12345678
        def communicate(self, timeout):
            calls.append(timeout)
            if len(calls)==1: raise subprocess.TimeoutExpired('fixed-probe', timeout)
            return b'',None
    monkeypatch.setattr(isolation, '_runtime', lambda: {'fixture': True})
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0, stdout=b'bubblewrap 0.9.0\n'))
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: Process())
    killed=[];monkeypatch.setattr(os,'killpg',lambda pid,sig:killed.append((pid,sig)))
    result=isolation.inspect(tmp_path/'probe')
    assert calls==[5,1] and killed==[(12345678,signal.SIGKILL)]
    assert result['status']=='unavailable' and not result['execution_authorized']


def test_real_trusted_probe_observes_namespace_fs_env_and_caps(tmp_path):
    if os.environ.get('CRYPTOFORGE_TEST_BWRAP') != '1': pytest.skip('explicit trusted namespace test opt-in required')
    result=isolation.inspect(tmp_path/'probe')
    assert result['status']=='trusted_probe_observed',result
    assert all(result['observation']['checks'].values())
    assert result['observation']['environment_keys']==['LANG','PATH','PWD']
    for field in ('candidate_executed','candidate_execution_enabled','execution_authorized',
                  'hard_process_count_limit_verified','aggregate_cpu_memory_control_verified',
                  'seccomp_policy_verified','runtime_mount_audited','security_audit_completed',
                  'shared_attempt_budget_integrated','training_executed'):
        assert result[field] is False
    assert result['network_requests']==result['api_calls']==0
