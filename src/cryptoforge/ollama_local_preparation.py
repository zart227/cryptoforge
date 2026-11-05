"""Read-only, offline capacity planning for a separate local decision backend.

This does not install, download, launch, authorize inference, or reserve resources.
Policy margins are project choices, not measured Ollama memory requirements.
"""
import argparse
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil

from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.local_semantic_contracts import SUPPORTED_SERVER_VERSION
from cryptoforge.ollama_decision_readiness import local_model, model_digest
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields


def _bytes(value, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or not 0 <= value <= 2**60:
        raise ValueError('nonnegative integer bytes required')
    return value


def validate_profile(profile):
    exact_fields(profile, {'schema_version', 'reviewed_on', 'platform', 'runtime',
                           'model', 'resource_policy', 'sources'})
    if profile['schema_version'] != 'ollama-local-preparation-profile-v1':
        raise ValueError('unsupported preparation profile')
    date.fromisoformat(profile['reviewed_on'])
    if profile['platform'] != {'system': 'Linux', 'machine': 'x86_64', 'execution': 'cpu'}:
        raise ValueError('checked Linux x86_64 CPU preparation profile required')
    runtime, model, policy = profile['runtime'], profile['model'], profile['resource_policy']
    exact_fields(runtime, {'version', 'asset', 'archive_bytes', 'archive_sha256', 'unpacked_bytes'})
    if runtime['version'] != SUPPORTED_SERVER_VERSION or runtime['asset'] != 'ollama-linux-amd64.tar.zst':
        raise ValueError('checked runtime version and asset required')
    model_digest(runtime['archive_sha256'])
    _bytes(runtime['archive_bytes']); _bytes(runtime['unpacked_bytes'], nullable=True)
    if runtime['unpacked_bytes'] == 0:
        raise ValueError('unpacked runtime size must be positive or unknown')
    exact_fields(model, {'tag', 'manifest_sha256', 'manifest_bytes', 'blobs'})
    local_model(model['tag']); model_digest(model['manifest_sha256']); _bytes(model['manifest_bytes'])
    blobs = model['blobs']
    if not isinstance(blobs, list) or not 1 <= len(blobs) <= 64:
        raise ValueError('bounded model blob metadata required')
    seen, model_layers = set(), 0
    for blob in blobs:
        exact_fields(blob, {'mediaType', 'digest', 'size'})
        pin = model_digest(blob['digest'])
        _bytes(blob['size'])
        if pin in seen or blob['mediaType'] not in {
                'application/vnd.docker.container.image.v1+json',
                'application/vnd.ollama.image.model', 'application/vnd.ollama.image.license',
                'application/vnd.ollama.image.params'}:
            raise ValueError('unique checked model blobs required')
        seen.add(pin)
        model_layers += blob['mediaType'] == 'application/vnd.ollama.image.model'
    if model_layers != 1:
        raise ValueError('one explicit CPU leaf model required')
    exact_fields(policy, {'memory_working_bytes', 'memory_headroom_bytes', 'disk_headroom_bytes'})
    if any(_bytes(v) == 0 for v in policy.values()) or not runtime['archive_bytes']:
        raise ValueError('positive project capacity margins required')
    if policy['memory_working_bytes'] < sum(b['size'] for b in blobs
            if b['mediaType'] == 'application/vnd.ollama.image.model'):
        raise ValueError('CPU working memory policy cannot be smaller than model weights')
    # URLs are documentary references, never requested by this module.
    exact_fields(profile['sources'], {'model_manifest', 'release', 'model_card'})
    expected_sources = {
        'model_manifest': 'https://registry.ollama.ai/v2/library/' + model['tag'].replace(':', '/manifests/'),
        'release': 'https://github.com/ollama/ollama/releases/tag/v' + runtime['version'],
        'model_card': 'https://ollama.com/library/' + model['tag']}
    if profile['sources'] != expected_sources:
        raise ValueError('matching official metadata references required')
    return profile


def _meminfo(text):
    result = {}
    for line in text.splitlines():
        key, _, value = line.partition(':')
        if key not in {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'}:
            continue
        parts = value.split()
        if key in result or len(parts) != 2 or parts[1] != 'kB' or not parts[0].isascii() or not parts[0].isdigit():
            raise ValueError('invalid memory observation')
        result[key] = _bytes(int(parts[0]) * 1024)
    return {key: result.get(key) for key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')}


def cgroup_memory(*, membership=Path('/proc/self/cgroup'), root=Path('/sys/fs/cgroup')):
    """Read every v2 ancestor limit; unknown never means unlimited.

    Namespace/mount remapping is not inferred. A hidden or unsupported hierarchy
    is unknown and prevents a positive capacity conclusion.
    """
    unknown = {'status': 'unknown', 'headroom_bytes': None, 'ancestors_checked': 0}
    try:
        lines = membership.read_text().splitlines()
        if len(lines) != 1 or not lines[0].startswith('0::/'):
            return unknown
        relative = PurePosixPath(lines[0][3:])
        if '..' in relative.parts:
            return unknown
        current = root.joinpath(*relative.parts[1:])
        finite, checked = [], 0
        while True:
            if (current == root and not (root/'memory.max').exists()
                    and not (root/'memory.current').exists()):
                # The real kernel root is exempt from memory control. Confirm a
                # root-only interface; a hidden/delegated mount is not unlimited.
                (root/'cpuset.cpus.isolated').read_text()
                if 'memory' not in (root/'cgroup.controllers').read_text().split():
                    return unknown
                checked += 1
                break
            limit = (current / 'memory.max').read_text().strip()
            usage = (current / 'memory.current').read_text().strip()
            if not usage.isascii() or not usage.isdigit():
                return unknown
            used = _bytes(int(usage))
            if limit != 'max':
                if not limit.isascii() or not limit.isdigit():
                    return unknown
                finite.append(max(0, _bytes(int(limit)) - used))
            checked += 1
            if current == root:
                break
            current = current.parent
        return {'status': 'finite' if finite else 'unlimited_observed',
                'headroom_bytes': min(finite) if finite else None, 'ancestors_checked': checked}
    except (OSError, ValueError):
        return unknown


def observe_host(storage_directory):
    directory = Path(storage_directory).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError('existing storage directory required')
    try:
        memory = _meminfo(Path('/proc/meminfo').read_text())
    except (OSError, ValueError):
        memory = {key: None for key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree')}
    return {'system': platform.system(), 'machine': platform.machine(),
            'memory_total_bytes': memory['MemTotal'], 'memory_available_bytes': memory['MemAvailable'],
            'swap_total_bytes': memory['SwapTotal'], 'swap_free_bytes': memory['SwapFree'],
            'disk_free_bytes': shutil.disk_usage(directory).free,
            'storage_directory': str(directory), 'cgroup_memory': cgroup_memory(),
            'ollama_in_path': shutil.which('ollama') is not None,
            'gpu_probe_performed': False}


def assess(profile, host):
    profile = deepcopy(validate_profile(profile)); host = deepcopy(host)
    exact_fields(host, {'system', 'machine', 'memory_total_bytes', 'memory_available_bytes',
        'swap_total_bytes', 'swap_free_bytes', 'disk_free_bytes', 'storage_directory',
        'cgroup_memory', 'ollama_in_path', 'gpu_probe_performed'})
    for key in ('memory_total_bytes', 'memory_available_bytes', 'swap_total_bytes', 'swap_free_bytes', 'disk_free_bytes'):
        _bytes(host[key], nullable=True)
    group = host['cgroup_memory']
    exact_fields(group, {'status', 'headroom_bytes', 'ancestors_checked'})
    if group['status'] not in {'unknown', 'finite', 'unlimited_observed'}:
        raise ValueError('invalid cgroup observation')
    _bytes(group['headroom_bytes'], nullable=True); _bytes(group['ancestors_checked'])
    if ((group['status'] == 'finite') != (group['headroom_bytes'] is not None)
            or (group['status'] != 'unknown' and group['ancestors_checked'] == 0)):
        raise ValueError('inconsistent cgroup observation')
    blocked, unknown = [], []
    if (host['system'], host['machine']) != ('Linux', 'x86_64'):
        blocked.append('unsupported_host_platform')
    policy, runtime, model = profile['resource_policy'], profile['runtime'], profile['model']
    memory_required = policy['memory_working_bytes'] + policy['memory_headroom_bytes']
    memory_available = host['memory_available_bytes']
    if memory_available is None:
        unknown.append('host_available_memory_unknown')
    elif memory_available < memory_required:
        blocked.append('host_available_memory_below_project_policy')
    if group['status'] == 'unknown':
        unknown.append('cgroup_memory_headroom_unknown')
    elif group['status'] == 'finite' and group['headroom_bytes'] < memory_required:
        blocked.append('cgroup_memory_headroom_below_project_policy')
    # Cold installation: no assumed reuse, deduplication, deletion or off-disk extraction.
    model_bytes = model['manifest_bytes'] + sum(b['size'] for b in model['blobs'])
    lower_bound = runtime['archive_bytes'] + model_bytes + policy['disk_headroom_bytes']
    unpacked = runtime['unpacked_bytes']
    disk_required = None if unpacked is None else lower_bound + unpacked
    if unpacked is None:
        unknown.append('runtime_unpacked_size_unverified')
    if host['disk_free_bytes'] is None:
        unknown.append('storage_free_space_unknown')
    elif host['disk_free_bytes'] < (disk_required if disk_required is not None else lower_bound):
        blocked.append('disk_capacity_below_project_policy')
    core = {'schema_version': 'ollama-local-preparation-v1',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'status': 'blocked' if blocked else 'needs_measurement' if unknown else 'preparation_resources_plausible',
        'blockers': blocked, 'unknowns': unknown, 'profile': profile, 'profile_sha256': digest(profile),
        'host_observation': host, 'capacity': {'memory_required_by_policy_bytes': memory_required,
            'cold_model_store_bytes': model_bytes, 'cold_disk_lower_bound_bytes': lower_bound,
            'cold_disk_required_bytes': disk_required},
        'scope': 'cold_isolated_cpu_installation_only', 'existing_installations_reused': False,
        'swap_counted_as_available_memory': False, 'capacity_reserved': False,
        'runtime_download_verified': False, 'installed_model_verified': False,
        'server_isolation_verified': False, 'model_load_verified': False,
        'inference_requests': 0, 'network_requests': 0, 'credentials_read': False,
        'automatic_install_or_start': False, 'live_execution_authorized': False,
        'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return {**core, 'receipt_sha256': digest(core)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--storage-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    with args.profile.open('rb') as stream:
        raw = stream.read(32_001)
    profile = validate_profile(strict_json(raw.decode('utf-8'), max_bytes=32_000))
    # Exclusive output before observation; an existing receipt is never overwritten.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(canonical({'schema_version': 'ollama-local-preparation-started-v1', 'status': 'started'}) + '\n')
        stream.flush()
        result = assess(profile, observe_host(args.storage_directory))
        stream.seek(0); stream.truncate(); stream.write(canonical(result) + '\n')
    print('Local preparation capacity: ' + result['status'] + '; no download, install or inference')
    return 0 if result['status'] == 'preparation_resources_plausible' else 2


if __name__ == '__main__':
    raise SystemExit(main())
