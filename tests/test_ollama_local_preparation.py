from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess

import pytest

from cryptoforge import ollama_local_preparation as prep
from cryptoforge.training_diagnostics import digest


GIB = 1024**3


@pytest.fixture
def profile():
    return json.loads((Path(__file__).resolve().parents[1] / 'config/ollama-local-preparation-v1.json').read_text())


@pytest.fixture
def host(tmp_path):
    return {'system': 'Linux', 'machine': 'x86_64', 'memory_total_bytes': 8*GIB,
        'memory_available_bytes': 4*GIB, 'swap_total_bytes': 20*GIB, 'swap_free_bytes': 10*GIB,
        'disk_free_bytes': 12*GIB, 'storage_directory': str(tmp_path),
        'cgroup_memory': {'status': 'unlimited_observed', 'headroom_bytes': None, 'ancestors_checked': 1},
        'ollama_in_path': False, 'gpu_probe_performed': False}


def test_actual_profile_is_pinned_leaf_not_cross_platform_alias(profile, host):
    result = prep.assess(profile, host)
    assert profile['model']['tag'] == 'tev1:0.8b-q8_0'
    assert profile['model']['manifest_sha256'] == 'sha256:abc31fdb0bf52506cc47091145ac19c4cfb509b73a6841789324f9e32200c099'
    assert result['capacity']['cold_model_store_bytes'] == 833_607_645
    assert result['capacity']['cold_disk_lower_bound_bytes'] == 4_419_775_897
    assert result['capacity']['cold_disk_required_bytes'] is None
    assert result['status'] == 'needs_measurement'
    assert result['unknowns'] == ['runtime_unpacked_size_unverified']
    assert result['receipt_sha256'] == digest({k:v for k,v in result.items() if k != 'receipt_sha256'})


def test_low_memory_and_disk_not_rescued_by_swap(profile, host):
    host.update(memory_available_bytes=850_000_000, disk_free_bytes=4_030_000_000, swap_free_bytes=100*GIB)
    result = prep.assess(profile, host)
    assert result['status'] == 'blocked'
    assert result['blockers'] == ['host_available_memory_below_project_policy', 'disk_capacity_below_project_policy']
    assert not result['swap_counted_as_available_memory']
    assert result['unknowns'] == ['runtime_unpacked_size_unverified']


def test_known_unpacked_size_and_exact_boundary_do_not_authorize_execution(profile, host):
    profile['runtime']['unpacked_bytes'] = 3*GIB
    host['memory_available_bytes'] = 3*GIB
    host['disk_free_bytes'] = prep.assess(profile, host)['capacity']['cold_disk_required_bytes']
    result = prep.assess(profile, host)
    assert result['status'] == 'preparation_resources_plausible'
    assert result['blockers'] == result['unknowns'] == []
    for key in ('capacity_reserved', 'live_execution_authorized', 'server_isolation_verified',
                'runtime_download_verified', 'installed_model_verified', 'model_load_verified'):
        assert result[key] is False
    host['disk_free_bytes'] -= 1
    assert prep.assess(profile, host)['blockers'] == ['disk_capacity_below_project_policy']


@pytest.mark.parametrize('group,blockers,unknown', [
    ({'status':'finite','headroom_bytes':GIB,'ancestors_checked':3}, ['cgroup_memory_headroom_below_project_policy'], False),
    ({'status':'finite','headroom_bytes':3*GIB,'ancestors_checked':3}, [], False),
    ({'status':'unknown','headroom_bytes':None,'ancestors_checked':0}, [], True)])
def test_cgroup_headroom_cannot_be_ignored(profile, host, group, blockers, unknown):
    host['cgroup_memory'] = group
    result = prep.assess(profile, host)
    assert result['blockers'] == blockers
    assert ('cgroup_memory_headroom_unknown' in result['unknowns']) == unknown


def test_missing_observations_remain_unknown(profile, host):
    host.update(memory_available_bytes=None, disk_free_bytes=None)
    result = prep.assess(profile, host)
    assert result['status'] == 'needs_measurement'
    assert set(result['unknowns']) == {'host_available_memory_unknown', 'storage_free_space_unknown',
                                      'runtime_unpacked_size_unverified'}


@pytest.mark.parametrize('change', ['cloud', 'version', 'platform', 'duplicate_blob', 'negative_size',
                                 'bool_size', 'bad_digest', 'source', 'extra_command', 'zero_margin',
                                 'zero_unpacked', 'memory_below_weights'])
def test_invalid_profiles_cannot_produce_capacity_receipt(profile, host, change):
    if change == 'cloud': profile['model']['tag'] = 'clef:cloud'
    elif change == 'version': profile['runtime']['version'] = '0.40.6'
    elif change == 'platform': profile['platform']['execution'] = 'mlx'
    elif change == 'duplicate_blob': profile['model']['blobs'].append(profile['model']['blobs'][0])
    elif change == 'negative_size': profile['model']['blobs'][0]['size'] = -1
    elif change == 'bool_size': profile['runtime']['archive_bytes'] = True
    elif change == 'bad_digest': profile['model']['manifest_sha256'] = 'abc31fdb0bf5'
    elif change == 'source': profile['sources']['model_card'] = 'https://example.org/model'
    elif change == 'extra_command': profile['command'] = ['untrusted']
    elif change == 'zero_unpacked': profile['runtime']['unpacked_bytes'] = 0
    elif change == 'memory_below_weights': profile['resource_policy']['memory_working_bytes'] = 1
    else: profile['resource_policy']['disk_headroom_bytes'] = 0
    with pytest.raises(ValueError): prep.assess(profile, host)


def test_unsupported_host_is_blocked_and_inputs_preserved(profile, host):
    host.update(system='Darwin', machine='arm64')
    before = deepcopy((profile, host))
    assert prep.assess(profile, host)['blockers'] == ['unsupported_host_platform']
    assert before == (profile, host)


def test_memavailable_not_memfree_or_swap():
    observed = prep._meminfo('MemTotal: 8000 kB\nMemFree: 1 kB\nMemAvailable: 5000 kB\nSwapFree: 999999 kB')
    assert observed['MemAvailable'] == 5000*1024
    assert observed['SwapTotal'] is None
    with pytest.raises(ValueError): prep._meminfo('MemAvailable: -1 kB')
    with pytest.raises(ValueError): prep._meminfo('MemAvailable: 1 kB\nMemAvailable: 2 kB')


def test_all_cgroup_ancestors_checked_and_missing_is_unknown(tmp_path):
    membership, root = tmp_path/'membership', tmp_path/'cgroup'
    leaf = root/'user.slice'/'process.scope'
    leaf.mkdir(parents=True)
    membership.write_text('0::/user.slice/process.scope\n')
    for path, limit, current in [(root, 'max', '100'), (root/'user.slice', str(3*GIB), str(GIB)),
                                 (leaf, str(4*GIB), str(GIB))]:
        (path/'memory.max').write_text(limit); (path/'memory.current').write_text(current)
    assert prep.cgroup_memory(membership=membership, root=root) == {
        'status':'finite', 'headroom_bytes':2*GIB, 'ancestors_checked':3}
    (root/'memory.max').unlink()
    assert prep.cgroup_memory(membership=membership, root=root)['status'] == 'unknown'
    membership.write_text('0::/../outside\n')
    assert prep.cgroup_memory(membership=membership, root=root)['status'] == 'unknown'


def test_cgroup_exhaustion_clamps_to_zero(tmp_path):
    membership = tmp_path/'membership'; membership.write_text('0::/\n')
    (tmp_path/'memory.max').write_text('10'); (tmp_path/'memory.current').write_text('11')
    assert prep.cgroup_memory(membership=membership, root=tmp_path)['headroom_bytes'] == 0


def test_real_root_exemption_requires_root_only_kernel_interface(tmp_path):
    root, membership = tmp_path/'cgroup', tmp_path/'membership'
    leaf = root/'limited'; leaf.mkdir(parents=True)
    membership.write_text('0::/limited\n')
    (leaf/'memory.max').write_text(str(3*GIB)); (leaf/'memory.current').write_text(str(GIB))
    (root/'cgroup.controllers').write_text('cpu memory cpuset')
    assert prep.cgroup_memory(membership=membership, root=root)['status'] == 'unknown'
    (root/'cpuset.cpus.isolated').write_text('')
    assert prep.cgroup_memory(membership=membership, root=root) == {
        'status':'finite', 'headroom_bytes':2*GIB, 'ancestors_checked':2}
    (leaf/'memory.max').write_text('max')
    assert prep.cgroup_memory(membership=membership, root=root) == {
        'status':'unlimited_observed', 'headroom_bytes':None, 'ancestors_checked':2}


def test_cli_is_offline_private_and_preserves_existing_receipt(profile, host, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('network or process execution refused')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(prep, 'observe_host', lambda path: deepcopy(host))
    config, output = tmp_path/'profile.json', tmp_path/'capacity.json'
    config.write_text(json.dumps(profile))
    argv = ['--profile', str(config), '--storage-directory', str(tmp_path), '--output', str(output)]
    assert prep.main(argv) == 2
    data = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    receipt = json.loads(data)
    assert receipt['network_requests'] == receipt['inference_requests'] == 0
    assert not receipt['credentials_read'] and not receipt['automatic_install_or_start']
    monkeypatch.setattr(prep, 'observe_host', forbidden)
    with pytest.raises(FileExistsError): prep.main(argv)
    assert output.read_bytes() == data


def test_real_probe_is_read_only_and_never_executes(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('execution refused')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    result = prep.observe_host(tmp_path)
    assert result['storage_directory'] == str(tmp_path)
    assert result['disk_free_bytes'] >= 0
    assert not result['gpu_probe_performed']
    assert list(tmp_path.iterdir()) == []


def test_invalid_profile_does_not_create_output(profile, tmp_path):
    profile['runtime']['archive_sha256'] = 'unverified'
    config, output = tmp_path/'profile.json', tmp_path/'result.json'
    config.write_text(json.dumps(profile))
    with pytest.raises(ValueError):
        prep.main(['--profile', str(config), '--storage-directory', str(tmp_path), '--output', str(output)])
    assert not output.exists()
