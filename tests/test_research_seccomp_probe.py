"""Fixed deny-rule kernel evidence must not upgrade candidate runtime qualification."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat

import pytest
from cryptoforge import research_seccomp_probe as m
from cryptoforge.research_training_diagnostics import canonical,digest


PARENT={k:k+':[parent]' for k in ('net','pid','user','mnt')}


def observation():
    # Fixed exported23instruction BPF, not kernel execution evidence.
    # Saved reviewed bytes are represented explicitly to test checksum/contract guards.
    raw=base64.b64decode(json.loads((Path(m.__file__).parents[2]/'config/research-seccomp-probe-fixture-v1.json').read_text())['bpf_base64'])
    checks={k:True for k in ('namespaces_differ','only_loopback_interface','home_and_host_sockets_hidden','environment_cleared',
        'capabilities_dropped','no_new_privileges','canary_readonly','root_readonly','temporary_write_succeeded')}
    return {'schema_version':'trusted-code-isolation-probe-v1','checks':checks,
        'namespaces':{k:k+':[child]' for k in PARENT},'environment_keys':['LANG','PATH','PWD'],
        'canary_sha256':hashlib.sha256(m.isolation.CANARY).hexdigest(),'python_version':'3.12.3',
        'filter':{'libseccomp_version':[2,5,5],'architecture':'x86_64','syscall_numbers':dict(m.SYSCALL_NUMBERS),
            'denial_errno':{k:1 for k in m.TESTED},'before_filters':0,'after_filters':1,'after_mode':2,
            'no_new_privileges':True,'baseline_socket_creation_succeeded':True,'bpf_sha256':m.BPF_SHA,
            'bpf_bytes':len(raw),'bpf_base64':base64.b64encode(raw).decode()}}


def test_fixed_export_and_narrow_mechanical_summary():
    result=m.validate(observation(),PARENT)
    assert result=={'denied_syscalls_compiled':15,'denials_mechanically_checked':8,'filter_count_increment':1,
        'bpf_sha256':m.BPF_SHA,'default_allow_denylist_only':True,'candidate_runtime_qualified':False}
    assert json.loads((Path(m.__file__).parents[2]/'config/research-seccomp-probe-v1.json').read_text())==m.POLICY


@pytest.mark.parametrize('alter',[
    lambda o:o['checks'].update(home_and_host_sockets_hidden=False),
    lambda o:o['namespaces'].update(net=PARENT['net']),lambda o:o.update(python_version='3.13.0'),
    lambda o:o['filter'].update(architecture='aarch64'),lambda o:o['filter'].update(libseccomp_version=[2,5,4]),
    lambda o:o['filter'].update(after_filters=0),lambda o:o['filter'].update(before_filters=True),
    lambda o:o['filter'].update(after_mode=0),lambda o:o['filter'].update(no_new_privileges=False),
    lambda o:o['filter'].update(baseline_socket_creation_succeeded=False),
    lambda o:o['filter']['denial_errno'].update(socket=None),lambda o:o['filter']['denial_errno'].update(fork=True),
    lambda o:o['filter']['syscall_numbers'].update(execve=123),lambda o:o['filter'].update(bpf_base64='not-base64'),
    lambda o:o['filter'].update(bpf_bytes=0),lambda o:o['filter'].update(bpf_sha256='a'*64),
])
def test_incomplete_or_forged_kernel_claim_is_refused(alter):
    o=observation();alter(o)
    with pytest.raises(ValueError):m.validate(o,PARENT)


def test_rehashed_different_filter_is_not_the_reviewed_policy():
    o=observation();raw=b'\0'*184
    o['filter'].update(bpf_base64=base64.b64encode(raw).decode(),bpf_bytes=len(raw),bpf_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):m.validate(o,PARENT)


def test_no_optional_executable_mount_program_or_network_arguments(tmp_path):
    args=m.argv(tmp_path/'canary',PARENT)
    assert args.count(m.PROBE)==1 and m.isolation.PROBE not in args
    assert '--unshare-all' in args and '--clearenv' in args and '--cap-drop' in args
    assert '--ro-bind' in args and '/usr' in args and '--new-session' in args
    assert args[args.index('--')+1:args.index('--')+5]==['/usr/bin/python3','-I','-S','-c']
    assert 'seccomp_load' in m.PROBE and 'os.fork()' in m.PROBE
    assert m.POLICY['default_action']=='allow' and not m.POLICY['runtime_integration_enabled']


def test_unavailable_library_creates_private_failure_receipt_no_false_success(tmp_path,monkeypatch):
    original=m.isolation._sha
    monkeypatch.setattr(m.isolation,'_sha',lambda path:'a'*64 if str(path)==m.LIBRARY else original(path))
    result=m.inspect(tmp_path/'probe')
    assert result['status']=='unavailable' and result['observation'] is None
    assert not result['candidate_execution_enabled'] and not result['security_audit_completed']
    assert stat.S_IMODE((tmp_path/'probe').stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in (tmp_path/'probe').iterdir())
    with pytest.raises(ValueError):m.verify(tmp_path/'probe')
    with pytest.raises(ValueError):m.inspect(tmp_path/'probe')


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_BWRAP')!='1',reason='explicit namespace opt-in')
def test_real_fixed_filter_blocks_eight_calls_and_offline_replay_cannot_upgrade_scope(tmp_path):
    result=m.inspect(tmp_path/'probe')
    assert result['status']=='trusted_denylist_probe_observed' and result['process_reaped']
    assert result['summary']['denials_mechanically_checked']==8 and result['observation']['filter']['bpf_bytes']==184
    assert m.verify(tmp_path/'probe')==result
    result['runtime_integration_enabled']=True;result['receipt_sha256']=digest({k:v for k,v in result.items() if k!='receipt_sha256'})
    (tmp_path/'probe/receipt.json').write_text(canonical(result)+'\n')
    with pytest.raises(ValueError):m.verify(tmp_path/'probe')


def test_fixed_policy_cannot_enable_runtime_or_change_denylist(tmp_path):
    policy=deepcopy(m.POLICY);policy['runtime_integration_enabled']=True
    with pytest.raises(ValueError):m.inspect(tmp_path/'probe',policy)
    assert not (tmp_path/'probe').exists()


def test_cli_refuses_missing_pack_without_executing_filter(tmp_path):
    assert m.main(['verify','--directory',str(tmp_path/'missing')])==2
