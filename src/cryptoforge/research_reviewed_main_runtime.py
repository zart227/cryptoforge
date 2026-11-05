"""Variant B: frozen reviewed supabase_executor bytes inside this branch."""
import hashlib
import json
import os
from pathlib import Path
import shutil

from cryptoforge.training_diagnostics import canonical


_BRANCH_ROOT = Path(__file__).resolve().parents[2]
_CONFIG = _BRANCH_ROOT / 'config/reviewed-main-runtime-v1.json'
_POLICY = json.loads(_CONFIG.read_text(encoding='utf-8'))
FROZEN_EXECUTOR = _BRANCH_ROOT / _POLICY['frozen_supabase_executor_path']
LIVE_MAIN = Path(_POLICY['live_main_project'])
SCRIPT_SOURCES = frozenset({'capture_reference_sources.py', 'audit_local_source_provenance.py'})
VALUE_MODULES = ('cryptoforge', 'bybit_private', 'candle_contract', 'market_data', 'model_training',
    'night_research', 'night_research_cli', 'order_observer', 'supabase_executor', 'supabase_market', 'target_contracts')
_MERGED_ROOT = _BRANCH_ROOT / '.local/reviewed-main-runtime-merged'
_MERGED_SRC = _MERGED_ROOT / 'src'
_MERGED_STAMP = _MERGED_ROOT / 'stamp.json'


def _guard():
    if canonical(_POLICY) != canonical(json.loads(_CONFIG.read_text(encoding='utf-8'))):
        raise ValueError('fixed_reviewed_main_runtime_policy_required')
    if _POLICY['pin_variant'] != 'B':
        raise ValueError('reviewed_main_runtime_variant_b_required')
    if FROZEN_EXECUTOR.is_symlink() or not FROZEN_EXECUTOR.is_file() or not 0 < FROZEN_EXECUTOR.stat().st_size <= 512000:
        raise ValueError('bounded_frozen_supabase_executor_required')
    digest = hashlib.sha256(FROZEN_EXECUTOR.read_bytes()).hexdigest()
    if digest != _POLICY['frozen_supabase_executor_sha256']:
        raise ValueError('frozen_supabase_executor_pin_mismatch')


def _merged_src():
    _guard()
    stamp = {'schema_version': 'reviewed-main-runtime-merged-v1',
        'frozen_supabase_executor_sha256': _POLICY['frozen_supabase_executor_sha256']}
    if _MERGED_STAMP.is_file() and json.loads(_MERGED_STAMP.read_text(encoding='utf-8')) == stamp:
        return _MERGED_SRC
    if _MERGED_ROOT.exists():
        shutil.rmtree(_MERGED_ROOT)
    package = _MERGED_SRC / 'cryptoforge'
    package.mkdir(parents=True)
    shutil.copy2(FROZEN_EXECUTOR, package / 'supabase_executor.py')
    for name in VALUE_MODULES:
        if name == 'supabase_executor':
            continue
        relative = '__init__.py' if name == 'cryptoforge' else name + '.py'
        live = LIVE_MAIN / 'src/cryptoforge' / relative
        if live.is_symlink() or not live.is_file():
            raise ValueError('live_main_value_runtime_source_required')
        (package / relative).symlink_to(live.resolve())
    _MERGED_STAMP.write_text(json.dumps(stamp, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return _MERGED_SRC


def implementation():
    _guard()
    merged = _merged_src()
    return {'policy_sha256': hashlib.sha256(canonical(_POLICY).encode()).hexdigest(),
        'frozen_supabase_executor_sha256': _POLICY['frozen_supabase_executor_sha256'],
        'merged_src': str(merged)}


_LOADED = implementation()


def policy():
    _guard()
    return dict(_POLICY)


def live_main_project():
    _guard()
    return LIVE_MAIN


def reviewed_source_bytes(project, filename):
    _guard()
    if filename == 'supabase_executor.py':
        return FROZEN_EXECUTOR.read_bytes()
    root = Path(project)
    relative = Path('scripts' if filename in SCRIPT_SOURCES else 'src/cryptoforge') / filename
    path = root / relative
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 512000:
        raise ValueError('bounded_regular_reviewed_source_required')
    return path.read_bytes()


def reviewed_value_module_bytes(project, module_name):
    _guard()
    if module_name == 'supabase_executor':
        return FROZEN_EXECUTOR.read_bytes()
    path = Path(project) / 'src/cryptoforge' / ('__init__.py' if module_name == 'cryptoforge' else module_name + '.py')
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 512000:
        raise ValueError('bounded_value_runtime_source_required')
    return path.read_bytes()


def worker_pythonpath(project):
    _guard()
    project = Path(project)
    executor = project / 'src/cryptoforge/supabase_executor.py'
    if executor.is_file() and not executor.is_symlink() and 0 < executor.stat().st_size <= 512000:
        if hashlib.sha256(executor.read_bytes()).hexdigest() == _POLICY['frozen_supabase_executor_sha256']:
            return str(project / 'src')
    return str(_merged_src())


def copy_live_main_path(source_relative, destination):
    _guard()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if Path(source_relative).as_posix().endswith('supabase_executor.py'):
        shutil.copy2(FROZEN_EXECUTOR, destination)
        return
    shutil.copy2(LIVE_MAIN / source_relative, destination)
