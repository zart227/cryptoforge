"""Default-deny BPF semantics, exact policy/namespace proof and offline verification."""
import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
import struct

import pytest
from cryptoforge import research_syscall_allowlist as m
from cryptoforge.research_training_diagnostics import canonical, digest
from test_research_seccomp_probe import observation as old_observation, PARENT


BPF_BASE64 = 'IAAAAAQAAAAVAAAcPgAAwCAAAAAAAAAANQAAAQAAAEAVAAAZ/////xUAFwAAAAAAFQAWAAEAAAAVABUAAwAAABUAFAAFAAAAFQATAAgAAAAVABIACQAAABUAEQAKAAAAFQAQAAsAAAAVAA8ADAAAABUADgANAAAAFQANAA4AAAAVAAwADwAAABUACwAcAAAAFQAKADwAAAAVAAkASAAAABUACABZAAAAFQAHAMoAAAAVAAYA2QAAABUABQDkAAAAFQAEAOcAAAAVAAMAAQEAABUAAgAGAQAAFQABAD4BAAAGAAAAAQAFAAYAAAAAAP9/BgAAAAAAAAA='


def observation():
    result = old_observation(); result['mount_checks'] = {k: True for k in m.mounts.MOUNT_CHECKS}
    result['filter'].update(syscall_numbers=m.DENY_NUMBERS, allowed_syscall_numbers=m.ALLOW_NUMBERS,
        default_action='errno_EPERM', baseline_getppid_succeeded=True,
        denial_errno={k: 1 for k in m.TESTED}, bpf_bytes=248, bpf_sha256=m.BPF_SHA, bpf_base64=BPF_BASE64)
    return deepcopy(result)


def test_fixed_policy_has_only_reviewed23_syscalls_and_statically_checked_default_deny():
    result = m.validate(observation(), PARENT)
    assert result['allowed_syscalls_compiled'] == 23 and result['denials_mechanically_checked'] == 9
    assert result['unlisted_harmless_getppid_denied'] and not result['candidate_runtime_qualified']
    proof = result['offline_bpf_semantics']
    assert proof['instruction_count'] == 31 and proof['cases_checked'] == 275
    assert proof['all_uint32_number_classes_checked'] and not proof['seccomp_filter_loaded_by_verifier']
    assert not set(m.ALLOWED).intersection(m.seccomp.DENY+['getppid'])
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-syscall-allowlist-v1.json').read_text()) == m.POLICY


@pytest.mark.parametrize('check', sorted(m.mounts.MOUNT_CHECKS))
def test_every_reduced_mount_check_remains_required(check):
    value = observation(); value['mount_checks'][check] = False
    with pytest.raises(ValueError): m.validate(value, PARENT)


@pytest.mark.parametrize('change', [
    lambda v: v['filter'].update(default_action='allow'),
    lambda v: v['filter']['allowed_syscall_numbers'].update(socket=41),
    lambda v: v['filter']['allowed_syscall_numbers'].update(read=True),
    lambda v: v['filter']['denial_errno'].update(getppid=0),
    lambda v: v['filter']['denial_errno'].update(socket=True),
    lambda v: v['filter'].update(baseline_getppid_succeeded=False),
    lambda v: v['filter'].update(after_filters=2),
    lambda v: v['filter'].update(after_mode=True),
    lambda v: v['filter'].update(bpf_bytes=184),
    lambda v: v['filter'].update(bpf_base64='AAAA'),
    lambda v: v['checks'].update(no_new_privileges=False),
    lambda v: v['namespaces'].update(net=PARENT['net']),
])
def test_unchecked_filter_abi_or_namespace_changes_refused(change):
    value = observation(); change(value)
    with pytest.raises(ValueError): m.validate(value, PARENT)


@pytest.mark.parametrize('index,k', [(28, 0x7fff0000), (29, 0x00050001), (30, 0x7fff0000), (5, 2)])
def test_independent_bpf_interpreter_detects_changed_allow_default_or_arch_action(index, k):
    instructions = list(struct.iter_unpack('<HBBI', base64.b64decode(BPF_BASE64)))
    code, yes, no, _ = instructions[index]; instructions[index] = (code, yes, no, k)
    raw = b''.join(struct.pack('<HBBI', *row) for row in instructions)
    with pytest.raises(ValueError, match='bpf_differs'): m.bpf_semantics(raw)


@pytest.mark.parametrize('change', ['short', 'opcode', 'out_of_bounds'])
def test_static_bpf_verifier_rejects_unsupported_program_shapes(change):
    raw = base64.b64decode(BPF_BASE64)
    if change == 'short': raw = raw[:-8]
    else:
        rows = list(struct.iter_unpack('<HBBI', raw))
        rows[5] = (0x07, 0, 0, 0) if change == 'opcode' else (0x15, 255, 0, 0)
        raw = b''.join(struct.pack('<HBBI', *row) for row in rows)
    with pytest.raises(ValueError): m.bpf_semantics(raw)


def test_fixed_namespace_command_contains_no_whole_usr_or_candidate_flags(tmp_path):
    profile = m.inventory(); args = m.argv(tmp_path/'canary', PARENT, profile)
    bindings = [args[i+1:i+3] for i, a in enumerate(args) if a == '--ro-bind']
    assert len(bindings) == 11 and ['/usr', '/usr'] not in bindings
    assert m.PROBE in args and m.mounts.PROBE not in args
    assert 'lib.seccomp_init(0x00050001)' in m.PROBE
    assert 'lib.seccomp_rule_add_array(context,0x7fff0000' in m.PROBE
    profile['bindings'].append({'source': '/home', 'destination': '/extra', 'kind': 'directory'})
    with pytest.raises(ValueError, match='fixed_runtime_mapping'): m.argv(tmp_path/'canary', PARENT, profile)


def test_scope_policy_cannot_enable_candidates():
    policy = deepcopy(m.POLICY); policy['candidate_execution_enabled'] = True
    with pytest.raises(ValueError, match='fixed_syscall_allowlist'): m._guard(policy)


def test_failed_inventory_retains_private_receipt_and_never_claims_installed_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'inventory', lambda: (_ for _ in ()).throw(ValueError('unreviewed runtime')))
    result = m.inspect(tmp_path/'probe')
    assert result['status'] == 'unavailable' and result['observation'] is None
    assert stat.S_IMODE((tmp_path/'probe').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in (tmp_path/'probe').iterdir())
    with pytest.raises(ValueError): m.verify(tmp_path/'probe')


@pytest.mark.skipif(os.environ.get('CRYPTOFORGE_TEST_BWRAP') != '1', reason='explicit fixed namespace opt-in')
def test_real_default_deny_child_filter_parent_unchanged_and_verify_never_installs_filter(tmp_path, monkeypatch):
    def filters():
        return [line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('Seccomp')]
    before = filters(); result = m.inspect(tmp_path/'probe')
    assert result['status'] == 'trusted_syscall_allowlist_probe_observed' and result['process_reaped']
    assert result['summary']['offline_bpf_semantics']['cases_checked'] == 275
    assert filters() == before
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('offline verify cannot launch child'))
    assert m.verify(tmp_path/'probe') == result and filters() == before
    forged = deepcopy(result); forged['summary']['candidate_runtime_qualified'] = True
    forged['receipt_sha256'] = digest({k: v for k, v in forged.items() if k != 'receipt_sha256'})
    (tmp_path/'probe/receipt.json').write_text(canonical(forged))
    with pytest.raises(ValueError): m.verify(tmp_path/'probe')


def test_missing_cli_pack_does_not_launch_any_process(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('no child for missing pack'))
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out
