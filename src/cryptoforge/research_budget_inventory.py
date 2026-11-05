"""Read-only inventory of explicitly pinned local research journals; no totals by guess."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re
import sqlite3

from cryptoforge import research_phase as phase, research_attempts as attempts
from cryptoforge import research_resource_budget as resources, semantic_request_journal as semantic
from cryptoforge import research_data_protocol as temporal, research_local_export as private
from cryptoforge import semantic_source_collector as files
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


POLICY = {'schema_version': 'research-budget-inventory-policy-v1', 'maximum_ledgers': 16,
    'maximum_database_bytes': 16777216, 'maximum_table_rows': 2000, 'maximum_report_bytes': 2097152,
    'scope': 'explicit_visible_local_journals_only', 'new_actions_enabled': False,
    'global_spend_enforcement_verified': False}
ATTEMPT_TABLES = {'studies', 'configurations', 'attempts', 'budgets', 'protocol_versions'}
TABLES = {'api': {'request_policy', 'advisor_requests'}, 'attempts': ATTEMPT_TABLES,
    'semantic_fixture': {'semantic_policy', 'semantic_requests'}, 'common_v5': phase.TABLES}
STATES = {'reserved', 'completed', 'failed', 'cancelled', 'timed_out'}


def implementation():
    return {'inventory': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'phase': phase.implementation(),
        'attempts': hashlib.sha256(Path(attempts.__file__).read_bytes()).hexdigest(),
        'semantic_fixture': hashlib.sha256(Path(semantic.__file__).read_bytes()).hexdigest()}


_LOADED = implementation()
_POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('budget_inventory_source_or_policy_changed')


def _pinned(ref):
    path = Path(ref['path'])
    if type(ref['path']) is not str or not path.is_absolute() or str(path.resolve()) != ref['path']:
        raise ValueError('canonical_original_journal_path_required')
    private._safe_directory(path.parent)
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(path)+suffix).exists(): raise ValueError('inactive_delete_mode_journal_required')
    raw = private._private_read(path.parent, path.name, POLICY['maximum_database_bytes'])
    temporal._sha(ref['sha256'])
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('original_budget_journal_checksum_changed')
    return path


def _connect(ref):
    path = _pinned(ref); db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=2)
    try:
        db.execute('PRAGMA query_only=ON'); db.execute('PRAGMA trusted_schema=OFF'); db.execute('BEGIN')
        if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
            raise ValueError('inactive_delete_mode_journal_required')
        objects = set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
        if objects != {('table', name) for name in TABLES[ref['kind']]}:
            raise ValueError('closed_budget_journal_schema_required')
        for table in TABLES[ref['kind']]:
            if db.execute('SELECT count(*) FROM '+table).fetchone()[0] > POLICY['maximum_table_rows']:
                raise ValueError('budget_inventory_row_limit')
        return db
    except BaseException:
        db.close(); raise


def _payload(raw, checksum):
    value = strict_json(raw, max_bytes=2_000_000)
    if digest(value) != checksum: raise ValueError('original_budget_payload_checksum_changed')
    return value


def _api(db, day):
    policy = db.execute('SELECT id,maximum FROM request_policy').fetchall()
    if len(policy) != 1 or policy[0][0] != 1 or type(policy[0][1]) is not int or not 1 <= policy[0][1] <= 20:
        raise ValueError('original_api_quota_policy_required')
    states = Counter(); records = []; known = dict(resources.ZERO_TOKENS); unknown = dict(resources.ZERO_TOKENS)
    for key, utc_day, status, request_raw, payload, checksum in db.execute('SELECT * FROM advisor_requests ORDER BY key'):
        request = strict_json(request_raw, max_bytes=512000)
        if digest(request) != key or status not in STATES or re.fullmatch(r'\d{4}-\d{2}-\d{2}', utc_day) is None:
            raise ValueError('original_api_request_identity_required')
        timestamp(utc_day+'T00:00:00Z')
        states[status] += 1; tokens = dict(resources.UNKNOWN_TOKENS); zero_pricing = None; provider = None
        if status == 'completed':
            result = _payload(payload, checksum)
            if result.get('report_sha256') != digest(request['report']) or result.get('provider') != request.get('provider'):
                raise ValueError('original_api_request_response_link_required')
            provider = result['provider']
            if provider not in ('openrouter', 'ollama'): raise ValueError('known_provider_origin_required')
            tokens = resources.provider_tokens(result.get('usage'))
            price = result.get('price_receipt')
            if provider == 'openrouter' and type(price) is dict:
                try:
                    pricing = price['pricing']
                    zero_pricing = (type(price['model']) is str and price['model'] == request['model']
                        and price['model'].endswith(':free') and {'prompt', 'completion'} <= set(pricing)
                        and all(Decimal(str(value)).is_finite() and Decimal(str(value)) == 0 for value in pricing.values()))
                except (KeyError, TypeError, InvalidOperation): zero_pricing = None
        elif payload is not None or checksum is not None:
            raise ValueError('unfinished_api_result_must_stay_unknown')
        for name, value in tokens.items():
            if value is None: unknown[name] += 1
            else: known[name] += value
        records.append({'request_key': key, 'status': status, 'utc_day': utc_day, 'provider': provider,
            'tokens': tokens, 'recorded_zero_pricing': zero_pricing,
            'billing_usd_verified': None, 'current_route_or_account_spend_verified': False})
    return {'kind': 'api', 'reserved_requests': len(records), 'statuses': dict(states),
        'daily_maximum': policy[0][1], 'reserved_on_snapshot_utc_day': sum(record['utc_day'] == day for record in records),
        'known_provider_token_subtotal': known, 'unknown_token_rows_by_field': unknown,
        'measured_wall_seconds': None, 'records': records, 'billing_audited': False}


def _attempts(db):
    manifests = {}; configurations = {}; families = defaultdict(set); reservations = []
    for study, protocol, raw, observed in db.execute('SELECT * FROM studies ORDER BY id'):
        manifest = strict_json(raw, max_bytes=2_000_000)
        if attempts.identity(manifest) != study: raise ValueError('original_study_identity_changed')
        timestamp(observed); manifests[study] = (protocol, manifest)
        for candidate in manifest['grid']:
            family = candidate['family']
            if type(family) is not str or re.fullmatch('[A-Za-z0-9_-]{1,64}', family) is None:
                raise ValueError('bounded_family_identifier_required')
            families[(protocol, family)].add(attempts.budget_key(candidate, manifest))
    for protocol, family, key, raw in db.execute('SELECT * FROM configurations ORDER BY protocol,family,id'):
        candidate = strict_json(raw, max_bytes=64000)
        if attempts.identity(candidate) != key or candidate.get('family') != family:
            raise ValueError('original_configuration_identity_changed')
        configurations[(protocol, key)] = candidate
    budgets = dict(db.execute('SELECT protocol,maximum FROM budgets'))
    for (protocol, family), identities in families.items():
        maximum = budgets.get(protocol)
        if type(maximum) is not int or maximum < 1 or len(identities) > maximum:
            raise ValueError('original_family_budget_inconsistent')
    for study, configuration, status, payload, observed, finished in db.execute('SELECT * FROM attempts ORDER BY study,configuration'):
        if (study not in manifests or (manifests[study][0], configuration) not in configurations
                or configuration not in {attempts.identity(candidate) for candidate in manifests[study][1]['grid']}
                or status not in {'reserved', 'completed', 'failed'}):
            raise ValueError('original_attempt_registration_required')
        timestamp(observed)
        if status == 'reserved':
            if payload is not None or finished is not None: raise ValueError('reserved_attempt_result_must_stay_unknown')
        else:
            if timestamp(finished) < timestamp(observed): raise ValueError('original_attempt_clock_regression')
            strict_json(payload, max_bytes=2_000_000)
        reservations.append({'study': study, 'configuration': configuration, 'status': status,
            'result_sha256': hashlib.sha256(payload.encode()).hexdigest() if payload is not None else None,
            'observed_at': observed, 'finished_at': finished})
    return {'kind': 'attempts', 'reserved_attempts': len(reservations), 'statuses': dict(Counter(row['status'] for row in reservations)),
        'family_usage': [{'protocol_sha256': digest(protocol), 'family': family, 'used_effective_configurations': len(identities),
            'maximum': budgets[protocol]} for (protocol, family), identities in sorted(families.items())],
        'records': reservations, 'actual_fit_invocations_verified': None, 'measured_wall_seconds': None,
        'provider_tokens_verified': None, 'billing_audited': False}


def _common(db, ref, observed_at):
    def read(table):
        rows = db.execute('SELECT id,payload,sha FROM '+table).fetchall()
        if len(rows) != 1 or rows[0][0] != 1: raise ValueError('single_original_budget_policy_required')
        return _payload(rows[0][1], rows[0][2])
    manifest = read('coordinated_policy'); resource_policy = read('coordinated_resource_policy')
    sem = read('coordinated_semantic_extension')['configuration']['policy']
    code = read('coordinated_code_extension')['configuration']['policy']
    exact_fields(ref['options'], {'bindings', 'semantic_live_ledger'})
    legacy = phase.common.ResearchRunBudget(Path(ref['path']), ref['options']['bindings'], policy=manifest['policy'],
        resource_policy=resource_policy, semantic_live_ledger=ref['options']['semantic_live_ledger'],
        semantic_live_policy=sem, code_check_policy=code, clock=lambda: observed_at)
    previous = phase.numeric.NumericControlBudget(legacy, phase.numeric.POLICY)
    reader = phase.ResearchPhaseBudget(previous, phase.POLICY)
    snapshot = reader.snapshot()  # Native readonly path: no migrate/run/reserve/init.
    bindings = {**ref['options']['bindings'], 'semantic_live': ref['options']['semantic_live_ledger']}
    return {'kind': 'common_v5', 'native_snapshot': snapshot,
        'original_binding_files_present': {name: Path(path).is_file() for name, path in bindings.items()},
        'inner_journal_contents_verified': False, 'standalone_older_history_automatically_imported': False,
        'billing_audited': False}


def collect(request, observed_at):
    _guard(); exact_fields(request, {'schema_version', 'scope', 'journals'})
    if request['schema_version'] != 'research-budget-inventory-request-v1' or request['scope'] != POLICY['scope']:
        raise ValueError('explicit_local_visible_inventory_required')
    observed_at = timestamp(observed_at); refs = request['journals']
    if type(refs) is not list or not 1 <= len(refs) <= POLICY['maximum_ledgers']:
        raise ValueError('bounded_explicit_journal_list_required')
    seen = set(); paths = set(); result = []; overlaps = defaultdict(list); identical = defaultdict(list)
    for ref in refs:
        exact_fields(ref, {'id', 'kind', 'path', 'sha256', 'options'})
        if (type(ref['id']) is not str or re.fullmatch('[a-z][a-z0-9_]{0,47}', ref['id']) is None
                or type(ref['path']) is not str or type(ref['kind']) is not str
                or ref['id'] in seen or ref['path'] in paths or ref['kind'] not in TABLES):
            raise ValueError('unique_closed_journal_reference_required')
        seen.add(ref['id']); paths.add(ref['path'])
        if ref['kind'] != 'common_v5': exact_fields(ref['options'], set())
        db = _connect(ref)
        try:
            if ref['kind'] == 'api': record = _api(db, observed_at.date().isoformat())
            elif ref['kind'] == 'attempts': record = _attempts(db)
            elif ref['kind'] == 'common_v5': record = _common(db, ref, observed_at)
            else:
                rows = db.execute('SELECT id,payload,sha FROM semantic_policy').fetchall()
                if len(rows) != 1 or rows[0][0] != 1: raise ValueError('single_original_semantic_policy_required')
                policy = _payload(rows[0][1], rows[0][2])
                record = {'kind': 'semantic_fixture', 'native_snapshot': semantic.SemanticRequests(Path(ref['path']),
                    policy=policy, clock=lambda: observed_at).snapshot(), 'billing_audited': False}
        finally: db.close()
        _pinned(ref); identical[ref['sha256']].append(ref['id'])
        for row in record.get('records', []) if ref['kind'] == 'attempts' else []:
            overlaps[(row['study'], row['configuration'])].append({'journal_id': ref['id'], 'status': row['status'],
                'result_sha256': row['result_sha256']})
        result.append({'id': ref['id'], 'path_sha256': digest(ref['path']), 'source_sha256': ref['sha256'], **record})
    for ref in refs: _pinned(ref)
    core = {'schema_version': 'research-budget-inventory-v1', 'observed_at': observed_at.isoformat(),
        'request_sha256': digest(request), 'policy_sha256': digest(POLICY), 'journals': result,
        'byte_identical_journal_groups': [ids for ids in identical.values() if len(ids) > 1],
        'overlapping_attempt_identity_groups': [{'study': key[0], 'configuration': key[1], 'records': rows,
            'interpretation': 'possible_replay_copy_or_separate_execution_not_deduplicated'} for key, rows in sorted(overlaps.items()) if len(rows) > 1],
        'cross_journal_global_totals': None, 'deduplication_or_double_charging_resolved': False,
        'account_wide_spend_usd': None, 'jobpilot_shared_quota_verified': False,
        'cpu_ram_disk_server_cli_cost_complete': False, 'billing_audited': False,
        'journal_copied_migrated_reset_or_refunded': False, 'new_budget_actions': 0,
        'provider_called': False, 'fit_performed': False, 'model_prediction_performed': False,
        'execution_authorized': False, 'production_promotion_authorized': False, 'implementation': _LOADED}
    report = {**core, 'inventory_sha256': digest(core)}
    if len(canonical(report).encode()) > POLICY['maximum_report_bytes']:
        raise ValueError('budget_inventory_report_limit')
    _guard(); return report


def prepare(directory, request):
    directory = Path(directory).absolute(); private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_budget_inventory_directory_required')
    now = datetime.now(timezone.utc).isoformat(); report = collect(request, now)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('request.json', request), ('inventory.json', report)):
        files._write(directory, name, value)
    files._sync(directory); files._sync(directory.parent); return report


def verify(directory):
    directory = private._safe_directory(directory, private=True)
    if temporal._read(directory, 'policy.json', 16000) != POLICY: raise ValueError('fixed_inventory_policy_required')
    saved = temporal._read(directory, 'inventory.json', POLICY['maximum_report_bytes'])
    report = collect(temporal._read(directory, 'request.json', 64000), saved['observed_at'])
    if canonical(saved) != canonical(report): raise ValueError('budget_inventory_or_original_sources_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--request', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify(args.directory) if args.command == 'verify' else prepare(args.directory,
            temporal._read(args.request.parent, args.request.name, 64000))
    except Exception:
        print('Local budget inventory refused; no budget changes'); return 2
    print('Local budget inventory verified: '+str(len(result['journals']))+' journals; global spend unknown'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
