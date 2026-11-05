"""Exact installed runtime closure does not qualify arbitrary candidate execution."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

import pytest
from cryptoforge import research_runtime_mounts as m
from cryptoforge.training_diagnostics import canonical,digest
from test_research_seccomp_probe import observation,PARENT


@pytest.fixture(scope='module')
def runtime_profile():return m.inventory()


def test_real_bounded_runtime_inventory_contains_only_fixed_mapping(runtime_profile):
    p=runtime_profile
    assert p['file_count']==len(p['files']) and p['file_count']<=2048 and p['total_bytes']<=134217728
    assert p['total_bytes']==sum(r['bytes'] for r in p['files'])
    assert len({r['path'] for r in p['files']})==p['file_count']
    assert len(p['bindings'])==10 and p['stdlib_symlinks']==m.LINKS
    assert p['inventory_sha256']==digest({k:v for k,v in p.items() if k!='inventory_sha256'})
    assert not p['stdlib_security_reviewed']
    assert json.loads((Path(m.__file__).parents[2]/'config/research-runtime-mounts-v1.json').read_text())==m.POLICY


def test_minimal_runtime_argv_mounts_fixed_files_and_stdlib_without_whole_usr(runtime_profile,tmp_path):
    args=m.argv(tmp_path/'canary',PARENT,runtime_profile)
    mounts=[args[i+1:i+3] for i,a in enumerate(args) if a=='--ro-bind']
    assert len(mounts)==11 and ['/usr','/usr'] not in mounts
    assert [str(m.STDLIB),str(m.STDLIB)] in mounts
    assert args.count(m.PROBE)==1 and args[args.index('--')+1:args.index('--')+5]==['/usr/bin/python3','-I','-S','-c']
    assert '--unshare-all' in args and '--clearenv' in args and '--cap-drop' in args and '--remount-ro' in args


def test_arbitrary_mount_mapping_cannot_be_passed_as_inventory(runtime_profile,tmp_path):
    p=deepcopy(runtime_profile);p['bindings'].append({'source':'/home','destination':'/extra','kind':'directory'})
    with pytest.raises(ValueError,match='fixed_runtime_mapping'):m.argv(tmp_path/'canary',PARENT,p)


@pytest.mark.parametrize('check',sorted(m.MOUNT_CHECKS))
def test_every_fixed_mount_visibility_check_is_required(check):
    observed=observation();observed['mount_checks']={k:True for k in m.MOUNT_CHECKS}
    summary=m.validate(observed,PARENT)
    assert summary['fixed_probe_mount_inventory_verified'] and not summary['candidate_runtime_mount_audited']
    observed['mount_checks'][check]=False
    with pytest.raises(ValueError):m.validate(observed,PARENT)


def test_exported_seccomp_proof_is_still_required():
    observed=observation();observed['mount_checks']={k:True for k in m.MOUNT_CHECKS}
    observed['filter']['denial_errno']['socket']=0
    with pytest.raises(ValueError):m.validate(observed,PARENT)


def test_runtime_file_reader_refuses_symlinks_special_files_and_oversize(tmp_path):
    p=tmp_path/'file';p.write_bytes(b'abc');assert m._hash_file(p)=={'bytes':3,'sha256':hashlib.sha256(b'abc').hexdigest()}
    link=tmp_path/'link';link.symlink_to(p)
    with pytest.raises((OSError,ValueError)):m._hash_file(link)
    p.write_bytes(b'')
    with p.open('r+b') as stream:stream.truncate(m.POLICY['maximum_file_bytes']+1)
    with pytest.raises(ValueError):m._hash_file(p)


def test_runtime_policy_cannot_expand_namespace_or_enable_candidate():
    policy=deepcopy(m.POLICY);policy['candidate_execution_enabled']=True
    with pytest.raises(ValueError):m._guard(policy)


def test_missing_inventory_qualification_preserves_private_failed_receipt(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'inventory',lambda:(_ for _ in ()).throw(ValueError('unsupported runtime')))
    result=m.inspect(tmp_path/'probe')
    assert result['status']=='unavailable' and result['observation'] is None and not result['candidate_execution_enabled']
    assert stat.S_IMODE((tmp_path/'probe').stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in (tmp_path/'probe').iterdir())
    with pytest.raises(ValueError):m.verify(tmp_path/'probe')
    with pytest.raises(ValueError):m.inspect(tmp_path/'probe')


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_BWRAP')!='1',reason='explicit fixed namespace opt-in')
def test_real_minimal_mounts_seccomp_and_original_inventory_replay(tmp_path):
    p=tmp_path/'probe';result=m.inspect(p)
    assert result['status']=='trusted_runtime_mount_probe_observed' and result['process_reaped']
    assert all(result['summary']['mount_checks'].values()) and result['summary']['seccomp']['denials_mechanically_checked']==8
    assert m.verify(p)==result
    original_receipt=(p/'receipt.json').read_bytes()
    forged=deepcopy(result);forged['summary']['candidate_runtime_mount_audited']=True
    forged['receipt_sha256']=digest({k:v for k,v in forged.items() if k!='receipt_sha256'})
    (p/'receipt.json').write_text(canonical(forged)+'\n')
    with pytest.raises(ValueError):m.verify(p)
    (p/'receipt.json').write_bytes(original_receipt)
    saved=json.loads((p/'runtime-inventory.json').read_text());saved['files'][0]['sha256']='a'*64
    saved['inventory_sha256']=digest({k:v for k,v in saved.items() if k!='inventory_sha256'})
    (p/'runtime-inventory.json').write_text(canonical(saved)+'\n')
    with pytest.raises(ValueError,match='original_runtime_inventory_changed'):m.verify(p)


def test_cli_verify_missing_pack_does_not_launch_process(tmp_path,monkeypatch):
    monkeypatch.setattr(m.subprocess,'Popen',lambda *_a,**_k:pytest.fail('read-only verify cannot run process'))
    assert m.main(['verify','--directory',str(tmp_path/'missing')])==2


def test_runtime_inventory_cannot_block_on_a_special_fifo(tmp_path):
    path=tmp_path/'fifo';os.mkfifo(path,0o600)
    with pytest.raises(ValueError):m._hash_file(path)


def test_runtime_reader_handles_regular_to_fifo_replacement_without_blocking(tmp_path,monkeypatch):
    path=tmp_path/'runtime';path.write_bytes(b'original');original=m.os.open
    def replace_before_open(p,flags,*a,**k):
        if Path(p)==path:
            path.unlink();os.mkfifo(path,0o600)
            assert flags&os.O_NONBLOCK
        return original(p,flags,*a,**k)
    monkeypatch.setattr(m.os,'open',replace_before_open)
    with pytest.raises(ValueError):m._hash_file(path)
