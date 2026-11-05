"""Pinned read-only Git/index/working-source base for future trainer research."""
import argparse
import ast
import hashlib
from pathlib import Path
import re
import subprocess
import time

from cryptoforge import research_value_audit as values
from cryptoforge.training_diagnostics import canonical, digest, exact_fields


GIT = '/usr/bin/git'
SOURCE_PATHS = sorted({
    'src/cryptoforge/'+('__init__.py' if name == 'cryptoforge' else name+'.py')
    for name in values.REVIEWED_VALUE_RUNTIME
} | {('scripts/' if name in ('capture_reference_sources.py', 'audit_local_source_provenance.py')
      else 'src/cryptoforge/')+name for name in values.revisions.POLICY['reviewed_sources']})
FUNCTIONS = {
    'src/cryptoforge/model_training.py': ['extract_features', 'ema_decimal', 'build_examples', 'ModelTrainingRunner._load_examples'],
    'src/cryptoforge/supabase_executor.py': ['rsi', 'SupabaseLiveExecutor._model_input_features'],
    'src/cryptoforge/candle_contract.py': ['closed_snapshot'],
}
POLICY = {'schema_version': 'research-trainer-base-policy-v1', 'source_paths': SOURCE_PATHS,
    'functions': FUNCTIONS, 'maximum_file_bytes': 512000, 'maximum_total_copy_bytes': 8388608,
    'capture_wall_seconds': 12, 'git_command_seconds': 3, 'git_version': 'git version 2.53.0',
    'patch_generation_enabled': False, 'candidate_execution_enabled': False, 'production_apply_enabled': False}


def implementation():
    return {'base': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'reviewed_sources': values.implementation(),
        'python_ast': hashlib.sha256(Path(ast.__file__).read_bytes()).hexdigest()}


_LOADED = implementation()
_POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('trainer_base_source_or_policy_changed')


def git_environment():
    return {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
        'GIT_NO_LAZY_FETCH': '1', 'GIT_TERMINAL_PROMPT': '0'}


def _git(project, args, deadline, *, maximum=64000, optional=False):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise ValueError('trainer_base_capture_deadline')
    command = [GIT, '--no-pager', '--no-optional-locks', '--no-replace-objects', '--no-lazy-fetch',
        '--literal-pathspecs', '-C', str(project), '-c', 'core.fsmonitor=false', '-c', 'core.untrackedCache=false',
        '-c', 'protocol.allow=never', *args]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=min(POLICY['git_command_seconds'], remaining), env=git_environment(), check=False)
    if len(result.stdout) > maximum or result.returncode not in ((0, 1) if optional else (0,)):
        raise ValueError('bounded_readonly_git_command_refused')
    return result.stdout


def _oid(value, object_format):
    if type(value) is not str or re.fullmatch('[a-f0-9]{'+('40' if object_format == 'sha1' else '64')+'}', value) is None:
        raise ValueError('git_object_identity_required')
    return value


def blob_oid(raw, object_format):
    if object_format not in ('sha1', 'sha256'):
        raise ValueError('supported_git_object_format_required')
    return hashlib.new(object_format, b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def parse_entries(raw, object_format, *, index):
    result = {}
    for record in raw.split(b'\0'):
        if not record:
            continue
        try:
            header, path = record.split(b'\t', 1); mode, value, third = header.decode('ascii').split(' ')
            path = path.decode('utf-8')
        except (ValueError, UnicodeError):
            raise ValueError('closed_git_source_entry_required') from None
        if path not in SOURCE_PATHS or path in result or mode not in ('100644', '100755'):
            raise ValueError('exact_regular_source_allowlist_required')
        if index:
            oid, stage = value, third
            if stage != '0':
                raise ValueError('unmerged_source_index_refused')
        else:
            kind, oid = value, third
            if kind != 'blob':
                raise ValueError('source_blob_required')
        result[path] = {'mode': mode, 'oid': _oid(oid, object_format)}
    return result


def _functions(copies):
    result = {}
    for path, names in FUNCTIONS.items():
        raw = copies['working/'+path]; source = raw.decode('utf-8'); lines = source.splitlines(keepends=True)
        module = ast.parse(source)
        for name in names:
            body = module.body
            for part in name.split('.'):
                found = [node for node in body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == part]
                if len(found) != 1:
                    raise ValueError('unique_original_trainer_function_required')
                node = found[0]; body = node.body
            span = ''.join(lines[node.lineno-1:node.end_lineno]).encode()
            result[path+':'+name] = {'start_line': node.lineno, 'end_line': node.end_lineno,
                'exact_source_sha256': hashlib.sha256(span).hexdigest(),
                'ast_sha256': hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()}
    return result


def capture(project):
    _guard(); project = values.private._safe_directory(project)
    # The existing reviewed profile rejects unreviewed trainer/source changes.
    profile = values.main_profile(project); deadline = time.monotonic()+POLICY['capture_wall_seconds']
    if _git(project, ['--version'], deadline).decode().strip() != POLICY['git_version']:
        raise ValueError('reviewed_git_version_required')
    git_sha = hashlib.sha256(Path(GIT).read_bytes()).hexdigest()
    root = _git(project, ['rev-parse', '--show-toplevel'], deadline).decode().strip()
    if Path(root) != project:
        raise ValueError('exact_git_worktree_root_required')
    if _git(project, ['config', '--local', '--get-regexp', r'^extensions\.partialclone$|^remote\..*\.promisor$'],
            deadline, optional=True).strip():
        raise ValueError('promisor_or_partial_clone_source_refused')
    object_format = _git(project, ['rev-parse', '--show-object-format'], deadline).decode().strip()
    if object_format not in ('sha1', 'sha256'):
        raise ValueError('supported_git_object_format_required')
    head = _oid(_git(project, ['rev-parse', 'HEAD'], deadline).decode().strip(), object_format)
    branch = _git(project, ['symbolic-ref', '--quiet', '--short', 'HEAD'], deadline, optional=True).decode().strip()
    if branch and (len(branch) > 160 or re.fullmatch('[A-Za-z0-9_./+-]+', branch) is None):
        raise ValueError('bounded_git_branch_required')
    head_entries = parse_entries(_git(project, ['ls-tree', '-rz', 'HEAD', '--', *SOURCE_PATHS], deadline), object_format, index=False)
    index_entries = parse_entries(_git(project, ['ls-files', '--stage', '-z', '--', *SOURCE_PATHS], deadline), object_format, index=True)
    copies = {}; files = {}; cache = {}
    for path in SOURCE_PATHS:
        original = project/path
        values.private._safe_directory(original.parent)
        if original.is_symlink() or not original.is_file() or not 0 < original.stat().st_size <= POLICY['maximum_file_bytes']:
            raise ValueError('bounded_original_working_source_required')
        working = original.read_bytes(); copies['working/'+path] = working
        versions = {'working': {'sha256': hashlib.sha256(working).hexdigest(), 'bytes': len(working),
            'git_blob_oid': blob_oid(working, object_format)}}
        for name, entries in (('head', head_entries), ('index', index_entries)):
            entry = entries.get(path)
            if entry is None:
                versions[name] = None; continue
            oid = entry['oid']
            if oid not in cache:
                size = _git(project, ['cat-file', '-s', oid], deadline).decode().strip()
                if re.fullmatch('[0-9]+', size) is None or not 0 < int(size) <= POLICY['maximum_file_bytes']:
                    raise ValueError('bounded_original_git_blob_required')
                raw = _git(project, ['cat-file', 'blob', oid], deadline, maximum=POLICY['maximum_file_bytes'])
                if len(raw) != int(size) or blob_oid(raw, object_format) != oid:
                    raise ValueError('original_git_blob_identity_mismatch')
                cache[oid] = raw
            raw = cache[oid]; copies[name+'/'+path] = raw
            versions[name] = {**entry, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        versions['tracked_in_index'] = versions['index'] is not None
        versions['index_differs_from_head'] = versions['index'] != versions['head']
        versions['working_differs_from_index'] = versions['index'] is None or versions['working']['git_blob_oid'] != versions['index']['oid']
        files[path] = versions
    if sum(len(raw) for raw in copies.values()) > POLICY['maximum_total_copy_bytes']:
        raise ValueError('trainer_base_total_copy_limit')
    if values.main_profile(project) != profile or hashlib.sha256(Path(GIT).read_bytes()).hexdigest() != git_sha:
        raise ValueError('original_trainer_or_git_changed_during_capture')
    context = {'project': str(project), 'git_head': head, 'git_branch': branch or None, 'git_object_format': object_format,
        'git_binary_sha256': git_sha, 'git_version': POLICY['git_version'], 'reviewed_profile': profile,
        'files': files, 'functions': _functions(copies),
        'copy_sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in sorted(copies.items())},
        'copy_bytes': sum(len(raw) for raw in copies.values()), 'source_scope_only': True,
        'whole_worktree_attested': False, 'installed_process_image_attested': False,
        'git_membership_checked_at_capture': True, 'offline_git_commit_tree_proof': False,
        'commit_signature_verified': False, 'remote_origin_or_credentials_copied': False}
    _guard()
    return context, copies


def _report(context):
    core = {'schema_version': 'research-trainer-base-v1', 'context_sha256': digest(context),
        'policy_sha256': digest(POLICY), 'implementation': _LOADED,
        'source_files': len(context['files']), 'copied_versions': len(context['copy_sha256']),
        'copy_bytes': context['copy_bytes'], 'functions_bound': len(context['functions']),
        'untracked_source_files': sum(not record['tracked_in_index'] for record in context['files'].values()),
        'index_changes': sum(record['index_differs_from_head'] for record in context['files'].values()),
        'working_changes': sum(record['working_differs_from_index'] for record in context['files'].values()),
        'working_trainer_source_base_bound': True, 'existing_virtual_preview_upgraded': False,
        'approved_development_data_bound': False, 'llm_patch_provenance_verified': False,
        'candidate_executed': False, 'numeric_budget_reserved': False, 'provider_called': False,
        'fit_performed': False, 'model_prediction_performed': False, 'training_data_admitted': False,
        'execution_authorized': False, 'production_apply_authorized': False}
    return {**core, 'base_sha256': digest(core)}


def prepare(directory, project):
    directory = Path(directory).absolute(); values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink():
        raise ValueError('new_trainer_base_directory_required')
    context, copies = capture(project)
    if capture(project) != (context, copies):
        raise ValueError('git_index_or_working_source_changed_during_snapshot')
    report = _report(context); directory.mkdir(mode=0o700)
    for name, raw in sorted(copies.items()):
        target = directory/name; target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # mkdir(parents=True) uses the umask for intermediate directories.
        parent = target.parent
        while parent != directory:
            parent.chmod(0o700); parent = parent.parent
        values.files._write(target.parent, target.name, raw)
    for name, value in (('policy.json', POLICY), ('context.json', context), ('base.json', report)):
        values.files._write(directory, name, value)
    for path in sorted((path for path in directory.rglob('*') if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
        values.files._sync(path)
    values.files._sync(directory); values.files._sync(directory.parent)
    return report


def verify(directory, expected_base_sha256):
    _guard(); values.temporal._sha(expected_base_sha256)
    directory = values.private._safe_directory(directory, private=True)
    policy = values.temporal._read(directory, 'policy.json', 32000)
    context = values.temporal._read(directory, 'context.json', 64000)
    saved = values.temporal._read(directory, 'base.json', 64000)
    exact_fields(context, {'project', 'git_head', 'git_branch', 'git_object_format', 'git_binary_sha256', 'git_version',
        'reviewed_profile', 'files', 'functions', 'copy_sha256', 'copy_bytes', 'source_scope_only',
        'whole_worktree_attested', 'installed_process_image_attested', 'git_membership_checked_at_capture',
        'offline_git_commit_tree_proof', 'commit_signature_verified', 'remote_origin_or_credentials_copied'})
    if (context['reviewed_profile'] != {'source': values.revisions.POLICY['reviewed_sources'], 'values': values.REVIEWED_VALUE_RUNTIME}
            or context['source_scope_only'] is not True or context['git_membership_checked_at_capture'] is not True
            or any(context[name] is not False for name in ('whole_worktree_attested', 'installed_process_image_attested',
                'offline_git_commit_tree_proof', 'commit_signature_verified', 'remote_origin_or_credentials_copied'))
            or context['git_version'] != POLICY['git_version']):
        raise ValueError('reviewed_source_scope_and_git_context_required')
    _oid(context['git_head'], context['git_object_format'])
    if policy != POLICY or saved.get('base_sha256') != expected_base_sha256:
        raise ValueError('external_original_base_pin_required')
    copies = {}
    if type(context.get('copy_sha256')) is not dict or not 18 <= len(context['copy_sha256']) <= 54:
        raise ValueError('bounded_original_source_copies_required')
    for name, checksum in context['copy_sha256'].items():
        pieces = name.split('/', 1)
        if len(pieces) != 2 or pieces[0] not in ('working', 'head', 'index') or pieces[1] not in SOURCE_PATHS:
            raise ValueError('exact_original_copy_allowlist_required')
        path = directory/name
        values.private._safe_directory(path.parent, private=True)
        raw = values.private._private_read(path.parent, path.name, POLICY['maximum_file_bytes'])
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError('original_source_copy_changed')
        copies[name] = raw
    if sum(len(raw) for raw in copies.values()) != context['copy_bytes'] or context['copy_bytes'] > POLICY['maximum_total_copy_bytes']:
        raise ValueError('trainer_base_copy_accounting_changed')
    if set(context['files']) != set(SOURCE_PATHS) or context['functions'] != _functions(copies):
        raise ValueError('original_trainer_function_binding_changed')
    for path, versions in context['files'].items():
        exact_fields(versions, {'working', 'head', 'index', 'tracked_in_index', 'index_differs_from_head', 'working_differs_from_index'})
        working = copies['working/'+path]
        if versions['working'] != {'sha256': hashlib.sha256(working).hexdigest(), 'bytes': len(working),
                'git_blob_oid': blob_oid(working, context['git_object_format'])}:
            raise ValueError('original_working_bytes_changed')
        for name in ('head', 'index'):
            record = versions[name]; raw = copies.get(name+'/'+path)
            if record is None:
                if raw is not None: raise ValueError('untracked_source_not_a_git_blob')
            elif raw is None or record != {'mode': record['mode'], 'oid': blob_oid(raw, context['git_object_format']),
                    'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)} or record['mode'] not in ('100644', '100755'):
                raise ValueError('original_git_copy_identity_changed')
        if (versions['tracked_in_index'] is not (versions['index'] is not None)
                or versions['index_differs_from_head'] is not (versions['index'] != versions['head'])
                or versions['working_differs_from_index'] is not (versions['index'] is None
                    or versions['working']['git_blob_oid'] != versions['index']['oid'])):
            raise ValueError('original_dirty_source_state_changed')
    expected = {('src/cryptoforge/'+('__init__.py' if name == 'cryptoforge' else name+'.py')): checksum
                for name, checksum in values.REVIEWED_VALUE_RUNTIME.items()}
    expected.update({('scripts/' if name in ('capture_reference_sources.py', 'audit_local_source_provenance.py')
        else 'src/cryptoforge/')+name: checksum for name, checksum in values.revisions.POLICY['reviewed_sources'].items()})
    if any(hashlib.sha256(copies['working/'+path]).hexdigest() != checksum for path, checksum in expected.items()):
        raise ValueError('reviewed_working_source_hashes_required')
    rebuilt = _report(context)
    if canonical(rebuilt) != canonical(saved) or rebuilt['base_sha256'] != expected_base_sha256:
        raise ValueError('trainer_base_manifest_or_implementation_changed')
    return rebuilt


def check_current(directory, expected_base_sha256, project):
    report = verify(directory, expected_base_sha256)
    context = values.temporal._read(Path(directory), 'context.json', 64000)
    if capture(project)[0] != context:
        raise ValueError('original_main_base_is_stale_do_not_apply')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify', 'check-current'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name != 'verify': command.add_argument('--project', type=Path, required=True)
        if name != 'prepare': command.add_argument('--expected-base-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare': report = prepare(args.directory, args.project)
        elif args.command == 'verify': report = verify(args.directory, args.expected_base_sha256)
        else: report = check_current(args.directory, args.expected_base_sha256, args.project)
    except Exception:
        print('Trainer source base refused; patch execution disabled'); return 2
    print('Trainer source base verified: '+report['base_sha256']+'; patch execution disabled'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
