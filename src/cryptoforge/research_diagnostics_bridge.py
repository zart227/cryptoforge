"""Typed inter-process diagnostics bridge; no metric substitution, provider or fit."""
import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import os
from pathlib import Path
import re
import resource
import signal
import stat
import subprocess
import sys
import tempfile

from cryptoforge import research_local_export as private
from cryptoforge import research_reviewed_main_runtime as reviewed_main
from cryptoforge import semantic_source_collector as files
from cryptoforge import training_diagnostics as predictions
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp

POLICY = {'schema_version': 'research-diagnostics-bridge-policy-v1', 'max_source_bytes': 262144,
    'max_evidence_bytes': 24000, 'max_configurations': 4, 'max_datasets': 32,
    'main_export_wall_seconds': 15, 'main_export_cpu_seconds': 8,
    'main_export_memory_bytes': 536870912, 'main_export_file_bytes': 524288,
    'main_export_max_ledger_bytes': 67108864, 'training_admission_enabled': False}
ROLES = ('baseline', 'filtered', 'stress_baseline', 'stress_filtered')
COUNTS = ('executed_trades', 'positive_trades', 'negative_trades', 'zero_trades',
    'generated_signals', 'rejected_signals', 'open_positions_at_end',
    'known_exit_minimum_violations', 'fee_erased_price_gains')
AMOUNTS = ('net_pnl', 'total_fees', 'final_cash', 'open_cost_basis_at_end')
OPTIONAL = ('profit_factor', 'net_per_executed_trade', 'net_per_generated_signal',
    'maximum_pair_trade_fraction', 'maximum_entry_day_trade_fraction')
METRICS = (*COUNTS, *AMOUNTS, 'drawdown_bound', *OPTIONAL)
LIMITATIONS = ['strategy_only_adapter_not_model_training', 'development_data_not_independent_test',
    'historical_execution_rules_not_certified', 'feature_quality_and_classifier_metrics_unknown',
    'source_registry_is_local_not_external_attestation']
MAIN_FILES = {**{n: 'src/cryptoforge/'+n+'.py' for n in ('training_diagnostics',
    'extension_report_evidence', 'research_attempts', 'training_snapshot', 'execution_controls')},
    'cli': 'scripts/report_training_diagnostics.py'}


def implementation():
    return {'bridge': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'prediction_diagnostics': hashlib.sha256(Path(predictions.__file__).read_bytes()).hexdigest(),
        'private_input': private.implementation()}


_LOADED = implementation()


def _guard(policy):
    if canonical(policy) != canonical(POLICY): raise ValueError('fixed_diagnostics_bridge_policy_required')
    if implementation() != _LOADED: raise ValueError('bridge_source_changed_restart_required')


def _sha(value):
    if type(value) is not str or re.fullmatch(r'[a-f0-9]{64}', value) is None:
        raise ValueError('source_sha256_required')
    return value


def _number(value, *, optional=False):
    if value is None and optional: return None
    if type(value) is not str or len(value) > 128 or re.fullmatch(r'-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?', value) is None:
        raise ValueError('source_decimal_string_required')
    try: parsed = Decimal(value)
    except InvalidOperation: raise ValueError('source_decimal_string_required') from None
    if not parsed.is_finite() or parsed.copy_abs() > Decimal('1e18'): raise ValueError('bounded_source_decimal_required')
    return parsed


def _count(value):
    if type(value) is not int or not 0 <= value <= 10**9: raise ValueError('source_count_required')
    return value


def _time(value):
    parsed = timestamp(value)
    if not 1970 <= parsed.year <= 2100: raise ValueError('bounded_source_timestamp_required')
    return parsed


def _fact(raw, context, metric, unit, numeric):
    if type(raw) is not dict: raise ValueError('plain_source_fact_required')
    exact_fields(raw, {'evidence_id', 'value', 'unit'})
    if raw['unit'] != unit or raw['evidence_id'] != 'ev:'+digest([context, metric, raw['value'], unit]):
        raise ValueError('source_evidence_identity_or_unit_changed')
    numeric(raw['value'])


def _strategy(source):
    exact_fields(source, {'schema_version', 'study_sha256', 'source_ledger_sha256', 'source_protocol_sha256',
        'source_runtime_bundle_sha256', 'implementation_sha256', 'datasets', 'results', 'classifier_metrics',
        'original_feature_quality', 'measured_worker_peak_memory_mb', 'limitations', 'provider_requests',
        'fitting_performed', 'ledger_modified', 'independent_evidence', 'live_promotion_allowed', 'report_sha256'})
    if (source['schema_version'] != 'training-diagnostics-v1' or source['limitations'] != LIMITATIONS
            or any(source[n] is not None for n in ('classifier_metrics', 'original_feature_quality', 'measured_worker_peak_memory_mb'))
            or type(source['provider_requests']) is not int or source['provider_requests'] != 0
            or any(source[n] is not False for n in ('fitting_performed', 'ledger_modified', 'independent_evidence', 'live_promotion_allowed'))):
        raise ValueError('original_development_strategy_contract_required')
    for name in ('study_sha256', 'source_ledger_sha256', 'source_protocol_sha256', 'source_runtime_bundle_sha256', 'report_sha256'):
        _sha(source[name])
    if source['report_sha256'] != digest({k: v for k, v in source.items() if k != 'report_sha256'}):
        raise ValueError('native_strategy_report_changed')
    exact_fields(source['implementation_sha256'], set(MAIN_FILES))
    for value in source['implementation_sha256'].values(): _sha(value)
    datasets = source['datasets']
    if type(datasets) is not list or not 1 <= len(datasets) <= POLICY['max_datasets']:
        raise ValueError('bounded_source_datasets_required')
    pairs = set(); dates = []
    for row in datasets:
        exact_fields(row, {'pair', 'sha256', 'candles', 'start', 'end'})
        if type(row['pair']) is not str or re.fullmatch(r'[A-Z0-9]{1,20}/USDT', row['pair']) is None or row['pair'] in pairs:
            raise ValueError('source_dataset_pair_required')
        pairs.add(row['pair']); _sha(row['sha256']); _count(row['candles'])
        start, end = _time(row['start']), _time(row['end'])
        if start > end: raise ValueError('source_dataset_range_invalid')
        dates += [start.date(), end.date()]
    results = source['results']
    if type(results) is not list or not 1 <= len(results) <= POLICY['max_configurations']:
        raise ValueError('bounded_source_configurations_required')
    seen = set()
    for result in results:
        exact_fields(result, {'configuration_sha256', 'candidate', 'execution_seconds', 'roles'})
        exact_fields(result['candidate'], {'family', 'risk'})
        if (result['candidate']['family'] not in ('support_bounce', 'compression_breakout')
                or result['candidate']['risk'] not in ('fixed', 'atr')
                or result['configuration_sha256'] != digest(result['candidate']) or result['configuration_sha256'] in seen
                or _number(result['execution_seconds']) < 0):
            raise ValueError('source_configuration_invalid')
        seen.add(result['configuration_sha256']); exact_fields(result['roles'], set(ROLES))
        for name, role in result['roles'].items():
            exact_fields(role, {'metrics', 'attribution', 'sample_status', 'historical_execution_qualified'})
            context = [source['study_sha256'], result['configuration_sha256'], name]
            metrics = role['metrics']; exact_fields(metrics, set(METRICS))
            for metric in METRICS:
                unit = 'count' if metric in COUNTS else 'USDT' if metric in AMOUNTS or metric.startswith('net_per') else 'fraction' if metric == 'drawdown_bound' else 'ratio'
                numeric = _count if metric in COUNTS else lambda v, m=metric: _number(v, optional=m in OPTIONAL)
                _fact(metrics[metric], context, metric, unit, numeric)
            values = {key: row['value'] for key, row in metrics.items()}; trades = values['executed_trades']
            if (sum(values[k] for k in ('positive_trades', 'negative_trades', 'zero_trades')) != trades
                    or values['generated_signals'] != trades+values['rejected_signals']+values['open_positions_at_end']
                    or role['sample_status'] != ('no_closed_trades' if trades == 0 else 'development_trades_only')
                    or role['historical_execution_qualified'] is not False
                    or not 0 <= _number(values['drawdown_bound']) <= 1
                    or any(_number(values[k]) < 0 for k in ('total_fees', 'final_cash', 'open_cost_basis_at_end'))):
                raise ValueError('inconsistent_source_role_facts')
            for key in OPTIONAL:
                n = _number(values[key], optional=True)
                if n is not None and ((key == 'profit_factor' and n < 0) or (key.startswith('maximum_') and not 0 <= n <= 1)):
                    raise ValueError('inconsistent_source_optional_ratio')
            exact_fields(role['attribution'], {'by_pair', 'by_entry_day'})
            for axis, rows in role['attribution'].items():
                if rows is None: continue
                if type(rows) is not dict or len(rows) > 128: raise ValueError('bounded_source_attribution_required')
                for group, row in rows.items():
                    if axis == 'by_pair':
                        if group not in pairs: raise ValueError('unknown_source_attribution_pair')
                    else:
                        day = _time(group+'T00:00:00+00:00').date()
                        if day.isoformat() != group or not min(dates) <= day <= max(dates):
                            raise ValueError('source_attribution_day_invalid')
                    exact_fields(row, {'trades', 'positive_trades', 'net_pnl', 'fees'})
                    for metric, fact in row.items():
                        _fact(fact, context, axis+':'+group+':'+metric,
                            'count' if metric in ('trades', 'positive_trades') else 'USDT',
                            _count if metric in ('trades', 'positive_trades') else _number)
                    if row['positive_trades']['value'] > row['trades']['value'] or _number(row['fees']['value']) < 0:
                        raise ValueError('source_attribution_counts_invalid')
                with localcontext() as ctx:
                    ctx.prec = 160
                    if (sum(row['trades']['value'] for row in rows.values()) != trades
                            or abs(sum((_number(r['net_pnl']['value']) for r in rows.values()), Decimal(0))-_number(values['net_pnl'])) > Decimal('1e-18')
                            or abs(sum((_number(r['fees']['value']) for r in rows.values()), Decimal(0))-_number(values['total_fees'])) > Decimal('1e-18')):
                        raise ValueError('source_attribution_does_not_reconcile')


def prepare(source, selection, policy=POLICY):
    _guard(policy)
    if type(source) is not dict or len(canonical(source).encode()) > POLICY['max_source_bytes']:
        raise ValueError('bounded_diagnostics_source_required')
    if type(selection) is not dict: raise ValueError('explicit_diagnostics_selection_required')
    kind = selection.get('kind')
    fields = {'schema_version', 'kind', 'configuration_sha256' if kind == 'strategy_outcomes' else 'evidence_group'}
    exact_fields(selection, fields)
    if selection['schema_version'] != 'research-diagnostics-selection-v1': raise ValueError('fixed_selection_version_required')
    facts = []
    if kind == 'strategy_outcomes':
        _strategy(source); _sha(selection['configuration_sha256'])
        chosen = [r for r in source['results'] if r['configuration_sha256'] == selection['configuration_sha256']]
        if len(chosen) != 1: raise ValueError('explicit_registered_configuration_required')
        for role in ROLES:
            for metric in METRICS:
                row = chosen[0]['roles'][role]['metrics'][metric]
                facts.append({'evidence_id': row['evidence_id'], 'source_evidence_id': row['evidence_id'],
                    'group': role, 'metric': metric, 'value': row['value'], 'unit': row['unit']})
        context = {'study_sha256': source['study_sha256'], 'declared_source_ledger_sha256': source['source_ledger_sha256'],
            'native_report_sha256': source['report_sha256'], 'candidate': deepcopy(chosen[0]['candidate']),
            'configuration_count': len(source['results']), 'datasets': deepcopy(source['datasets']),
            'excluded_axes': ['by_pair', 'by_entry_day'], 'excluded_configuration_count': len(source['results'])-1}
        route = 'strategy_research_review_only'
    elif kind == 'classifier_predictions':
        predictions.validate_diagnostics(source)
        group = selection['evidence_group']
        if type(group) is not str or group not in source['evidence']: raise ValueError('explicit_prediction_group_required')
        for metric, value in sorted(source['evidence'][group].items()):
            facts.append({'evidence_id': 'pred:'+digest([digest(source), group, metric]), 'source_evidence_id': group,
                'group': group, 'metric': metric, 'value': value, 'unit': 'count' if metric == 'count' else 'loss' if metric == 'log_loss' else 'ratio'})
        context = {key: deepcopy(source[key]) for key in ('partition', 'decision_threshold', 'dataset_sha256',
            'source_sha256', 'observations_sha256', 'development_end')}
        context['excluded_evidence_group_count'] = len(source['evidence'])-1
        route = 'legacy_prediction_advisor'
    else: raise ValueError('supported_diagnostics_kind_required')
    core = {'schema_version': 'research-diagnostics-evidence-v1', 'kind': kind,
        'native_contract': source['schema_version'], 'source_sha256': digest(source), 'selection_sha256': digest(selection),
        'context': context, 'facts': facts, 'consumer_route': route,
        'legacy_parameter_advisor_compatible': kind == 'classifier_predictions',
        'missing_values_preserved': True, 'economic_metrics_are_classifier_metrics': False,
        'upstream_lineage_verified': False, 'source_ledger_rebuilt': False,
        'development_split_approved': False, 'training_data_admitted': False,
        'provider_called': False, 'training_executed': False, 'production_compatible': False,
        'policy_sha256': digest(policy), 'implementation': deepcopy(_LOADED)}
    result = {**core, 'evidence_sha256': digest(core)}
    if len(canonical(result).encode()) > POLICY['max_evidence_bytes']:
        raise ValueError('evidence_byte_limit_no_truncation')
    return result


def stage_pack(directory, source, selection, policy=POLICY):
    result = prepare(source, selection, policy)
    directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_bridge_directory_required')
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', policy), ('source.json', source), ('selection.json', selection), ('evidence.json', result)):
        files._write(directory, name, value)
    files._sync(directory); files._sync(directory.parent)
    return result


def _read(directory, name, maximum):
    return files.strict_json(private._private_read(directory, name, maximum).decode(), max_bytes=maximum)


def read_pack(directory):
    directory = private._safe_directory(directory, private=True)
    source = _read(directory, 'source.json', POLICY['max_source_bytes'])
    result = prepare(source, _read(directory, 'selection.json', 4000), _read(directory, 'policy.json', 4000))
    if canonical(result) != canonical(_read(directory, 'evidence.json', 28000)):
        raise ValueError('bridge_evidence_or_implementation_changed')
    return result


def legacy_advisor_input(directory):
    evidence = read_pack(directory)
    if not evidence['legacy_parameter_advisor_compatible']:
        raise ValueError('strategy_facts_cannot_be_used_as_classifier_diagnostics')
    # Return the original native v2 report, not a fabricated metric conversion.
    source = _read(directory, 'source.json', POLICY['max_source_bytes'])
    if digest(source) != evidence['source_sha256']:
        raise ValueError('native_prediction_source_changed_during_read')
    predictions.validate_diagnostics(source)
    return source


def main_profile(project):
    project = private._safe_directory(project)
    result = {}
    for name, relative in MAIN_FILES.items():
        path = project/relative; private._safe_directory(path.parent)
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 512000:
            raise ValueError('regular_bounded_main_source_required')
        result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if result['training_diagnostics'] == _LOADED['prediction_diagnostics']:
        raise ValueError('strategy_producer_profile_required')
    return result


def _ledger_hash(path):
    path = Path(path).absolute(); private._safe_directory(path.parent)
    if any(os.path.lexists(str(path)+s) for s in ('-wal', '-shm', '-journal')):
        raise ValueError('quiescent_original_ledger_required')
    raw = private._private_read(path.parent, path.name, POLICY['main_export_max_ledger_bytes'])
    if raw[:16] != b'SQLite format 3\0' or raw[18:20] != b'\x01\x01':
        raise ValueError('original_sqlite_rollback_ledger_required')
    return hashlib.sha256(raw).hexdigest()


def _export_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (POLICY['main_export_cpu_seconds'], POLICY['main_export_cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_AS, (POLICY['main_export_memory_bytes'], POLICY['main_export_memory_bytes']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (POLICY['main_export_file_bytes'], POLICY['main_export_file_bytes']))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def _rebuild_main(project, ledger, study, directory):
    # Trusted main exporter, separate interpreter/import path. Never executes a
    # command from a report or model. These limits are not a generic sandbox.
    output = directory/'rebuilt.json'; log = directory/'worker.log'
    argv = [sys.executable, '-B', str(project/MAIN_FILES['cli']), '--ledger', str(ledger),
        '--study-sha256', study, '--output', str(output)]
    env = {'PATH': '/usr/bin:/bin', 'PYTHONPATH': reviewed_main.worker_pythonpath(project), 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONHASHSEED': '0', 'LANG': 'C.UTF-8', 'TZ': 'UTC'}
    proc = None
    with os.fdopen(os.open(log, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        try:
            proc = subprocess.Popen(argv, cwd=project, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=stream, start_new_session=True, preexec_fn=_export_limits)
            if proc.wait(timeout=POLICY['main_export_wall_seconds']) != 0:
                raise ValueError('main_source_rebuild_refused')
            return _read(directory, 'rebuilt.json', POLICY['max_source_bytes'])
        finally:
            if proc is not None:
                try: os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                proc.wait()


def bind_main_source(directory, project, ledger):
    _guard(POLICY); evidence = read_pack(directory)
    if evidence['kind'] != 'strategy_outcomes': raise ValueError('main_strategy_binding_only')
    directory = private._safe_directory(directory, private=True)
    if (directory/'main-binding.json').exists() or (directory/'main-binding.json').is_symlink():
        raise ValueError('new_main_binding_required_no_implicit_retry')
    project = private._safe_directory(project); ledger = Path(ledger).absolute()
    source = _read(directory, 'source.json', POLICY['max_source_bytes'])
    if digest(source) != evidence['source_sha256']:
        raise ValueError('strategy_source_changed_during_read')
    profile = main_profile(project); before = _ledger_hash(ledger)
    if profile != source['implementation_sha256'] or before != source['source_ledger_sha256']:
        raise ValueError('main_source_or_ledger_binding_changed')
    # Persist started before launching: interrupted/failed bindings cannot silently retry.
    started = {'schema_version': 'research-main-diagnostics-binding-v1', 'status': 'started',
        'evidence_sha256': evidence['evidence_sha256'], 'source_sha256': digest(source),
        'producer_profile': profile, 'source_ledger_sha256': before, 'source_rebuilt': False,
        'live_connection_rechecked': False, 'training_data_admitted': False}
    files._write(directory, 'main-binding.json', started); files._sync(directory)
    status = 'completed'
    try:
        with tempfile.TemporaryDirectory(prefix='main-diagnostics-', dir=directory.parent) as tmp:
            rebuilt = _rebuild_main(project, ledger, source['study_sha256'], Path(tmp))
            if canonical(rebuilt) != canonical(source): raise ValueError('main_rebuilt_source_mismatch')
        if main_profile(project) != profile or _ledger_hash(ledger) != before:
            raise ValueError('main_source_changed_during_rebuild')
    except BaseException as error:
        status = 'cancelled' if isinstance(error, KeyboardInterrupt) else 'timed_out' if isinstance(error, subprocess.TimeoutExpired) else 'failed'
        raise ValueError('main_binding_failed_no_automatic_retry') from None
    finally:
        receipt = {**started, 'status': status, 'source_rebuilt': status == 'completed',
            'source_ledger_unchanged': status == 'completed', 'trusted_export_worker_not_generic_sandbox': True,
            'interpreter_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            'implementation': deepcopy(_LOADED), 'local_binding_not_external_authentication': True}
        receipt['binding_sha256'] = digest(receipt)
        # Existing started receipt belongs to this invocation only; replace atomically.
        fd, tmp = tempfile.mkstemp(prefix='.binding-', dir=directory)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as stream: stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp, directory/'main-binding.json'); files._sync(directory)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    return receipt


def read_main_binding(directory, project, ledger):
    evidence = read_pack(directory)
    if evidence['kind'] != 'strategy_outcomes': raise ValueError('main_strategy_binding_only')
    receipt = _read(directory, 'main-binding.json', 12000)
    source = _read(directory, 'source.json', POLICY['max_source_bytes'])
    if digest(source) != evidence['source_sha256']:
        raise ValueError('strategy_source_changed_during_read')
    core = {k: v for k, v in receipt.items() if k != 'binding_sha256'}
    expected = {'schema_version', 'status', 'evidence_sha256', 'source_sha256', 'producer_profile',
        'source_ledger_sha256', 'source_rebuilt', 'live_connection_rechecked', 'training_data_admitted',
        'source_ledger_unchanged', 'trusted_export_worker_not_generic_sandbox', 'interpreter_sha256',
        'implementation', 'local_binding_not_external_authentication', 'binding_sha256'}
    exact_fields(receipt, expected)
    if (receipt['schema_version'] != 'research-main-diagnostics-binding-v1' or receipt['status'] != 'completed'
            or receipt['binding_sha256'] != digest(core) or receipt['evidence_sha256'] != evidence['evidence_sha256']
            or receipt['source_sha256'] != evidence['source_sha256'] or receipt['source_rebuilt'] is not True
            or receipt['source_ledger_unchanged'] is not True or receipt['live_connection_rechecked'] is not False
            or receipt['training_data_admitted'] is not False or receipt['trusted_export_worker_not_generic_sandbox'] is not True
            or receipt['local_binding_not_external_authentication'] is not True
            or receipt['implementation'] != _LOADED or receipt['producer_profile'] != source['implementation_sha256']
            or receipt['producer_profile'] != main_profile(project)
            or receipt['source_ledger_sha256'] != source['source_ledger_sha256']
            or receipt['source_ledger_sha256'] != _ledger_hash(ledger)
            or receipt['interpreter_sha256'] != hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()):
        raise ValueError('completed_unchanged_main_binding_required')
    return {'receipt': receipt, 'source_rebuilt_in_this_verification': False, 'training_data_admitted': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify', 'legacy-input', 'bind-main', 'verify-main'):
        cmd = sub.add_parser(name); cmd.add_argument('--directory', type=Path, required=True)
        if name == 'prepare':
            for flag in ('source', 'selection', 'policy'): cmd.add_argument('--'+flag, type=Path, required=True)
        if name in ('bind-main', 'verify-main'):
            cmd.add_argument('--project', type=Path, required=True); cmd.add_argument('--ledger', type=Path, required=True)
    args = parser.parse_args(argv)
    def read(path, maximum): return files._json(path.parent, path.name, maximum)
    try:
        if args.command == 'prepare': stage_pack(args.directory, read(args.source, POLICY['max_source_bytes']), read(args.selection, 4000), read(args.policy, 4000))
        elif args.command == 'verify': read_pack(args.directory)
        elif args.command == 'legacy-input': legacy_advisor_input(args.directory)
        elif args.command == 'bind-main': bind_main_source(args.directory, args.project, args.ledger)
        else: read_main_binding(args.directory, args.project, args.ledger)
    except Exception:
        print('Diagnostics bridge refused; no provider, fit or metric substitution')
        return 2
    print('Diagnostics bridge verified; no provider, fit or production change')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
