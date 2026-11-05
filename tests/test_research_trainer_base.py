"""Real local Git/index/dirty-byte snapshots; sources are never imported."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import time

import pytest

from cryptoforge import research_trainer_base as m
from cryptoforge import research_reviewed_main_runtime as reviewed_main


MAIN = reviewed_main.live_main_project()


def git(project, *args):
    result = subprocess.run([m.GIT, '-C', str(project), '-c', 'user.name=Research fixture',
        '-c', 'user.email=fixture@invalid', '-c', 'commit.gpgsign=false', *args],
        env=m.git_environment(), capture_output=True, check=True)
    return result.stdout


@pytest.fixture(scope='module')
def source_project(tmp_path_factory):
    project = tmp_path_factory.mktemp('real-git-trainer-source')
    for name in m.SOURCE_PATHS:
        target = project/name; target.parent.mkdir(parents=True, exist_ok=True); reviewed_main.copy_live_main_path(name, target)
    originals = {name: (project/name).read_bytes() for name in ('src/cryptoforge/bybit_private.py', 'src/cryptoforge/supabase_market.py')}
    for name, raw in originals.items(): (project/name).write_bytes(raw+b'\n# prior fixture revision\n')
    git(project, 'init', '--initial-branch=fixture-main')
    git(project, 'add', '--', *[name for name in m.SOURCE_PATHS if name != 'src/cryptoforge/reference_source_ledger.py'])
    git(project, 'commit', '--quiet', '-m', 'Source-only fixture base')
    for name, raw in originals.items(): (project/name).write_bytes(raw)
    git(project, 'add', '--', 'src/cryptoforge/supabase_market.py')
    (project/'.env').write_text('PRIVATE_TOKEN=should-never-be-copied\n')
    return project


@pytest.fixture(scope='module')
def base_pack(source_project, tmp_path_factory):
    directory = tmp_path_factory.mktemp('trainer-base-pack')/'base'
    report = m.prepare(directory, source_project)
    return directory, report


def test_git_index_and_working_states_bind_actual_trainer_functions(source_project, base_pack):
    directory, report = base_pack
    assert report['source_files'] == 18 and report['functions_bound'] == 7
    assert report['untracked_source_files'] == 1 and report['index_changes'] == 1
    assert report['working_changes'] == 2
    assert m.verify(directory, report['base_sha256']) == report
    assert m.check_current(directory, report['base_sha256'], source_project) == report
    context = json.loads((directory/'context.json').read_text())
    assert context['files']['src/cryptoforge/model_training.py']['working']['sha256'] == m.values.REVIEWED_VALUE_RUNTIME['model_training']
    assert context['files']['src/cryptoforge/bybit_private.py']['working_differs_from_index']
    assert context['files']['src/cryptoforge/supabase_market.py']['index_differs_from_head']
    assert context['files']['src/cryptoforge/reference_source_ledger.py']['head'] is None
    assert all('should-never-be-copied' not in path.read_text() for path in directory.rglob('*') if path.is_file())
    for name in ('existing_virtual_preview_upgraded', 'approved_development_data_bound', 'llm_patch_provenance_verified',
                 'candidate_executed', 'numeric_budget_reserved', 'provider_called', 'fit_performed',
                 'model_prediction_performed', 'training_data_admitted', 'execution_authorized', 'production_apply_authorized'):
        assert report[name] is False


def test_unrelated_work_does_not_invalidate_scoped_source_base(source_project, base_pack):
    directory, report = base_pack
    (source_project/'other-agent-plan.md').write_text('Independent work continues.\n')
    assert m.check_current(directory, report['base_sha256'], source_project) == report


def test_archived_base_remains_valid_but_live_index_change_is_stale(source_project, base_pack):
    directory, report = base_pack
    context = json.loads((directory/'context.json').read_text()); name = 'src/cryptoforge/bybit_private.py'
    original = context['files'][name]['index']
    try:
        git(source_project, 'add', '--', name)
        assert m.verify(directory, report['base_sha256']) == report
        with pytest.raises(ValueError, match='stale_do_not_apply'): m.check_current(directory, report['base_sha256'], source_project)
    finally:
        git(source_project, 'update-index', '--cacheinfo', original['mode'], original['oid'], name)


def test_source_bytes_cannot_change_without_review(source_project):
    path = source_project/'src/cryptoforge/model_training.py'; raw = path.read_bytes()
    try:
        path.write_bytes(raw+b'\n# changed by another worker\n')
        with pytest.raises(ValueError, match='requires_review'): m.capture(source_project)
    finally: path.write_bytes(raw)


@pytest.mark.parametrize('mode,third,path', [
    ('120000', '0', 'src/cryptoforge/model_training.py'),
    ('160000', '0', 'src/cryptoforge/model_training.py'),
    ('100644', '2', 'src/cryptoforge/model_training.py'),
    ('100644', '0', '.env'), ('100644', '0', '../src/cryptoforge/model_training.py'),
])
def test_index_symlinks_conflicts_and_paths_outside_allowlist_refused(mode, third, path):
    raw = f'{mode} '+('a'*40)+f' {third}\t{path}\0'
    with pytest.raises(ValueError): m.parse_entries(raw.encode(), 'sha1', index=True)


def test_git_blob_oid_is_an_independent_standard_object_identity():
    assert m.blob_oid(b'hello\n', 'sha1') == 'ce013625030ba8dba906f756967f9e9ca394464a'
    with pytest.raises(ValueError): m.blob_oid(b'hello\n', 'md5')


@pytest.mark.parametrize('raw', [b'bad', b'100644 a 0\tsrc/cryptoforge/model_training.py\0',
    (('100644 '+'a'*40+' 0\tsrc/cryptoforge/model_training.py\0')*2).encode()])
def test_malformed_duplicate_or_wrong_oid_entries_refused(raw):
    with pytest.raises(ValueError): m.parse_entries(raw, 'sha1', index=True)


def test_git_is_readonly_cleared_and_cannot_run_filters_or_lazy_fetch(monkeypatch, source_project):
    observed = {}
    def run(command, **kwargs):
        observed.update(command=command, **kwargs); return type('Result', (), {'stdout': b'ok', 'returncode': 0})()
    monkeypatch.setattr(m.subprocess, 'run', run)
    assert m._git(source_project, ['rev-parse', 'HEAD'], time.monotonic()+12) == b'ok'
    assert observed['stdin'] == subprocess.DEVNULL and observed['timeout'] <= 3
    assert '--no-lazy-fetch' in observed['command'] and '--no-replace-objects' in observed['command']
    assert 'core.fsmonitor=false' in observed['command'] and 'protocol.allow=never' in observed['command']
    assert observed['env']['GIT_CONFIG_GLOBAL'] == '/dev/null'
    assert '--filters' not in observed['command'] and '--textconv' not in observed['command']


def test_partial_clone_and_promisor_inputs_are_refused(source_project):
    try:
        git(source_project, 'config', 'remote.fixture.promisor', 'true')
        with pytest.raises(ValueError, match='promisor_or_partial_clone'): m.capture(source_project)
    finally: git(source_project, 'config', '--unset', 'remote.fixture.promisor')


def test_capture_deadline_has_no_unbounded_git_fallback(source_project):
    with pytest.raises(ValueError, match='capture_deadline'):
        m._git(source_project, ['rev-parse', 'HEAD'], time.monotonic()-1)


def test_wrong_expected_base_pin_never_accepts_self_asserted_manifest(base_pack):
    directory, report = base_pack
    with pytest.raises(ValueError, match='external_original_base_pin'): m.verify(directory, 'a'*64)


def test_private_modes_and_original_bytes_tampering(base_pack, tmp_path):
    source, report = base_pack; directory = tmp_path/'copy'; shutil.copytree(source, directory)
    for path in (directory, *directory.rglob('*')):
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
    target = directory/'working/src/cryptoforge/model_training.py'; target.write_bytes(target.read_bytes()+b'\n# mutation\n')
    with pytest.raises(ValueError, match='original_source_copy_changed'): m.verify(directory, report['base_sha256'])


def test_rehashed_manifest_cannot_upgrade_original_pin(base_pack, tmp_path):
    source, report = base_pack; directory = tmp_path/'copy'; shutil.copytree(source, directory)
    value = json.loads((directory/'base.json').read_text()); value['production_apply_authorized'] = True
    value['base_sha256'] = m.digest({key: item for key, item in value.items() if key != 'base_sha256'})
    (directory/'base.json').write_text(m.canonical(value)+'\n')
    with pytest.raises(ValueError, match='external_original_base_pin'): m.verify(directory, report['base_sha256'])


def test_new_only_and_fixed_configuration(source_project, base_pack):
    directory, _ = base_pack
    with pytest.raises(ValueError, match='new_trainer_base'): m.prepare(directory, source_project)
    assert json.loads((Path(m.__file__).parents[2]/'config/research-trainer-base-v1.json').read_text()) == m.POLICY


def test_safe_cli_refusal_never_prints_private_path(tmp_path, capsys):
    assert m.main(['verify', '--directory', str(tmp_path/'private-secret-path'), '--expected-base-sha256', 'a'*64]) == 2
    assert 'private-secret-path' not in capsys.readouterr().out
