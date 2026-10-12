import sys
from pathlib import Path
from cryptoforge.research_environment import research_environment


def test_missing_repository_keeps_unknown_git_state_and_no_fake_seed(tmp_path):
    result=research_environment(tmp_path)
    assert result['git_commit'] is None
    assert result['working_tree_dirty'] is None
    assert result['fit_seed'] is None and not result['randomness_used_for_fit']
    assert result['python_version']==list(sys.version_info[:3])


def test_receipt_records_revision_without_environment_values(monkeypatch,tmp_path):
    import subprocess
    outputs=iter(('a'*40+'\n',b' M file.py\n'))
    def run(*args,**kwargs):
        return subprocess.CompletedProcess(args[0],0,stdout=next(outputs))
    monkeypatch.setattr(subprocess,'run',run)
    monkeypatch.setenv('FAKE_PRIVATE_TOKEN','never-record-this')
    result=research_environment(tmp_path)
    assert result['git_commit']=='a'*40 and result['working_tree_dirty']
    assert 'never-record-this' not in str(result)
    assert result['source_hashes_are_authoritative']
