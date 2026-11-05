"""Bounded development facts for a research advisor; no provider or fitting."""
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from cryptoforge.execution_controls import unique_fields
from cryptoforge.extension_report_evidence import verify_extension_report
from cryptoforge.research_attempts import identity


SCOPE = 'catalog_extensions_fixed_vs_atr_development'
FAMILIES = {'support_bounce', 'compression_breakout'}
ROLES = ('baseline', 'filtered', 'stress_baseline', 'stress_filtered')
MAXIMUM_BYTES = 64*1024*1024
MAXIMUM_OUTPUT_BYTES = 256*1024
COUNT_FIELDS = ('executed_trades', 'positive_trades', 'negative_trades', 'zero_trades',
    'generated_signals', 'rejected_signals', 'open_positions_at_end',
    'known_exit_minimum_violations', 'fee_erased_price_gains')
AMOUNT_FIELDS = ('net_pnl', 'total_fees', 'final_cash', 'open_cost_basis_at_end')
OPTIONAL_FIELDS = ('profit_factor', 'net_per_executed_trade', 'net_per_generated_signal',
    'maximum_pair_trade_fraction', 'maximum_entry_day_trade_fraction')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require_sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('explicit lowercase source SHA256 required')
    return value


def parse(raw):
    value = json.loads(raw, object_pairs_hook=unique_fields,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite development JSON')))
    canonical(value)
    if not isinstance(value, dict):
        raise ValueError('development evidence object required')
    return value


def stamp(value):
    if type(value) is not str:
        raise ValueError('aware source timestamp required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('aware source timestamp required')
    return parsed.astimezone(UTC)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 128:
        raise ValueError('bounded numeric development fact required')
    parsed = Decimal(str(value))
    if not parsed.is_finite() or abs(parsed) > Decimal('1e18'):
        raise ValueError('finite bounded development fact required')
    return parsed


def count(value):
    if type(value) is not int or not 0 <= value <= 10**9:
        raise ValueError('bounded nonnegative source count required')
    return value


def pair(value):
    if type(value) is not str or re.fullmatch('[A-Z0-9]{1,20}/USDT', value) is None:
        raise ValueError('canonical pair identifier required')
    return value


def ledger_bytes(path):
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise ValueError('regular research ledger required')
    if any(os.path.lexists(str(path)+suffix) for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('quiescent research ledger without SQLite sidecars required')
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAXIMUM_BYTES:
            raise ValueError('bounded original research ledger required')
        raw = stream.read(MAXIMUM_BYTES+1)
    if (len(raw) != before.st_size or (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino)
            or raw[:16] != b'SQLite format 3\0' or raw[18:20] != b'\x01\x01'):
        raise ValueError('research ledger changed during diagnostics')
    return raw, (before.st_dev, before.st_ino)


def implementation_hashes():
    names = ('training_diagnostics', 'extension_report_evidence', 'research_attempts',
        'training_snapshot', 'execution_controls')
    result = {name: sha(Path(importlib.import_module('cryptoforge.'+name).__file__).read_bytes()) for name in names}
    result['cli'] = sha((Path(__file__).resolve().parents[2]/'scripts/report_training_diagnostics.py').read_bytes())
    return result


def role_facts(role, *, context, capital, pairs, earliest, latest):
    counts = {key: count(role[key]) for key in COUNT_FIELDS}
    amounts = {key: number(role[key]) for key in AMOUNT_FIELDS}
    trades = counts['executed_trades']
    if (sum(counts[key] for key in ('positive_trades', 'negative_trades', 'zero_trades')) != trades
            or counts['generated_signals'] != trades+counts['rejected_signals']+counts['open_positions_at_end']
            or min(amounts[key] for key in ('total_fees', 'final_cash', 'open_cost_basis_at_end')) < 0
            or abs(amounts['final_cash']+amounts['open_cost_basis_at_end']-capital-amounts['net_pnl']) > Decimal('1e-18')
            or role['independent_evidence'] is not False):
        raise ValueError('inconsistent original shared-wallet facts')
    drawdown = number(role['drawdown_bound'])
    if not 0 <= drawdown <= 1:
        raise ValueError('fractional original drawdown required')
    def fact(key, value, unit):
        value = str(value) if isinstance(value, Decimal) else value
        return dict(evidence_id='ev:'+sha(canonical([context, key, value, unit])), value=value, unit=unit)
    metrics = {key: fact(key, value, 'count') for key, value in counts.items()}
    metrics.update({key: fact(key, value, 'USDT') for key, value in amounts.items()})
    metrics['drawdown_bound'] = fact('drawdown_bound', drawdown, 'fraction')
    for key in OPTIONAL_FIELDS:
        value = role.get(key)
        value = number(value) if value is not None else None
        if value is not None and ((key == 'profit_factor' and value < 0)
                or (key.startswith('maximum_') and not 0 <= value <= 1)):
            raise ValueError('invalid optional development ratio')
        metrics[key] = fact(key, value, 'USDT' if key.startswith('net_per') else 'ratio')
    groups = {}
    for axis in ('by_pair', 'by_entry_day'):
        raw = role.get(axis)
        if raw is None:
            groups[axis] = None
            continue
        if not isinstance(raw, dict) or len(raw) > 128:
            raise ValueError('bounded original attribution required')
        rows = {}
        for name, row in sorted(raw.items()):
            if axis == 'by_pair':
                if pair(name) not in pairs:
                    raise ValueError('foreign attribution pair')
            else:
                day = stamp(name+'T00:00:00+00:00').date()
                if day.isoformat() != name or not earliest.date() <= day <= latest.date():
                    raise ValueError('attribution outside original development dates')
            positive, total = count(row['positive_trades']), count(row['trades'])
            pnl, fees = number(row['net_pnl']), number(row['fees'])
            if positive > total or fees < 0:
                raise ValueError('inconsistent attribution sample')
            rows[name] = {key: fact(axis+':'+name+':'+key, value, unit) for key, value, unit in (
                ('trades', total, 'count'), ('positive_trades', positive, 'count'),
                ('net_pnl', pnl, 'USDT'), ('fees', fees, 'USDT'))}
        if (sum(row['trades']['value'] for row in rows.values()) != trades
                or abs(sum((number(row['net_pnl']['value']) for row in rows.values()), Decimal(0))-amounts['net_pnl']) > Decimal('1e-18')
                or abs(sum((number(row['fees']['value']) for row in rows.values()), Decimal(0))-amounts['total_fees']) > Decimal('1e-18')):
            raise ValueError('attribution does not reconcile to shared wallet')
        groups[axis] = rows
    return dict(metrics=metrics, attribution=groups,
        sample_status='no_closed_trades' if not trades else 'development_trades_only',
        historical_execution_qualified=False)


def build_training_diagnostics(ledger_path, *, study_sha256, clock=None):
    """Read only an explicitly selected, completed development extension study."""
    require_sha(study_sha256)
    now = clock() if clock else datetime.now(UTC)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware diagnostics clock required')
    location = Path(ledger_path).absolute()
    if location.is_symlink():
        raise ValueError('ledger symlink is outside diagnostics contract')
    path = location.resolve()
    before, lineage = ledger_bytes(path)
    implementations = implementation_hashes()
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        row = db.execute('SELECT payload,observed_at FROM studies WHERE id=?', (study_sha256,)).fetchone()
        if row is None:
            raise ValueError('original selected study registration required')
        manifest = parse(row[0])
        if (identity(manifest) != study_sha256 or manifest['scope'] != SCOPE
                or manifest['input_policy'] != 'tail5000_first3500_development'
                or manifest['independent_evidence'] is not False or manifest['live_promotion_allowed'] is not False
                or manifest['historical_execution_rules_certified'] is not False
                or stamp(row[1]) > now):
            raise ValueError('only originally registered development scope may expose results')
        grid = manifest['grid']
        if (not isinstance(grid, list) or not 1 <= len(grid) <= 16
                or len({identity(item) for item in grid}) != len(grid)
                or any(set(item) != {'family', 'risk'} or item['family'] not in FAMILIES
                    or item['risk'] not in {'fixed', 'atr'} for item in grid)):
            raise ValueError('supported original extension catalog required')
        datasets = manifest['datasets']
        if not isinstance(datasets, list) or not datasets or len(datasets) > 32:
            raise ValueError('bounded original dataset metadata required')
        dataset_facts = []
        for item in datasets:
            start, end = stamp(item['start']), stamp(item['end'])
            if not start <= end <= stamp(row[1]):
                raise ValueError('dataset was not available at original study registration')
            dataset_facts.append(dict(pair=pair(item['pair']), sha256=require_sha(item['sha256']),
                candles=count(item['candles']), start=start.isoformat(), end=end.isoformat()))
        pairs = {item['pair'] for item in dataset_facts}
        if len(pairs) != len(dataset_facts) or set(manifest['pairs']) != pairs:
            raise ValueError('dataset pair identity mismatch')
        # Do not query reward-bearing attempts until the selected metadata has
        # passed the development-only contract. Other studies remain unread.
        attempts = db.execute('SELECT status,payload FROM attempts WHERE study=? ORDER BY configuration',
            (study_sha256,)).fetchall()
        if len(attempts) != len(grid) or any(status != 'completed' for status, _ in attempts):
            raise ValueError('complete original development grid required')
        results = [parse(raw) for _, raw in attempts]
        for result in results:
            if (result['scope'] != 'development_strategy_extension_comparison_not_ML_filter'
                    or result['independent_evidence'] is not False or result['live_promotion_allowed'] is not False
                    or result['model_fitting_performed'] is not False
                    or stamp(result['execution_finished_at']) > now):
                raise ValueError('development-only original result required')
        db.rollback()
    finally:
        db.close()
    report = dict(study_sha256=study_sha256, manifest=manifest, results=results,
        completed_configurations=len(results))
    verify_extension_report(report, path)
    projected = []
    for result in sorted(results, key=lambda row: identity(row['candidate'])):
        capital = number(result['initial_capital'])
        if capital <= 0 or set(result['roles']) != set(ROLES):
            raise ValueError('original positive capital and complete control roles required')
        candidate_sha = identity(result['candidate'])
        context = [study_sha256, candidate_sha]
        projected.append(dict(configuration_sha256=candidate_sha, candidate=result['candidate'],
            execution_seconds=str(Decimal(str((stamp(result['execution_finished_at'])-stamp(result['execution_started_at'])).total_seconds()))),
            roles={name: role_facts(result['roles'][name], context=context+[name], capital=capital,
                pairs=pairs, earliest=min(stamp(item['start']) for item in dataset_facts),
                latest=max(stamp(item['end']) for item in dataset_facts)) for name in ROLES}))
    after, final_lineage = ledger_bytes(path)
    if (before != after or lineage != final_lineage or location.resolve() != path
            or location.is_symlink() or implementation_hashes() != implementations):
        raise ValueError('original diagnostics input or implementation changed')
    output = dict(schema_version='training-diagnostics-v1', study_sha256=study_sha256,
        source_ledger_sha256=sha(before), source_protocol_sha256=require_sha(manifest['protocol_sha256']),
        source_runtime_bundle_sha256=require_sha(manifest['runtime_source_bundle']['sha256']),
        implementation_sha256=implementations, datasets=dataset_facts, results=projected,
        classifier_metrics=None, original_feature_quality=None, measured_worker_peak_memory_mb=None,
        limitations=['strategy_only_adapter_not_model_training', 'development_data_not_independent_test',
            'historical_execution_rules_not_certified', 'feature_quality_and_classifier_metrics_unknown',
            'source_registry_is_local_not_external_attestation'],
        provider_requests=0, fitting_performed=False, ledger_modified=False,
        independent_evidence=False, live_promotion_allowed=False)
    output['report_sha256'] = sha(canonical(output))
    if len(canonical(output)) > MAXIMUM_OUTPUT_BYTES:
        raise ValueError('development diagnostics exceed bounded advisor payload')
    return output
