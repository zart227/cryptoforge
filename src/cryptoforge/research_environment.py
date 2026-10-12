"""Sanitized deterministic numerical environment receipt; no environment values."""
import platform,subprocess,sys


def research_environment(repository):
    commit=None;dirty=None
    try:
        commit=subprocess.run(['git','-C',str(repository),'rev-parse','HEAD'],
            check=True,capture_output=True,text=True,timeout=3).stdout.strip()
        dirty=bool(subprocess.run(['git','-C',str(repository),'status','--porcelain',
            '--untracked-files=normal'],check=True,capture_output=True,timeout=3).stdout)
    except (OSError,subprocess.SubprocessError):pass
    return {'python_version':list(sys.version_info[:3]),
        'python_implementation':platform.python_implementation(),'machine':platform.machine(),
        'numeric_dependencies':'python_standard_library_only',
        'randomness_used_for_fit':False,'fit_seed':None,'git_commit':commit,
        'working_tree_dirty':dirty,'source_hashes_are_authoritative':True}
