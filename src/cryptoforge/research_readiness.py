"""Read-only evidence freshness and prerequisite checks; never reserves or authorizes operations."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from cryptoforge import research_cohort_reader_audit as reader, research_provider_limits as limits
from cryptoforge import llm_research_advisor as advisor
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, timestamp

POLICY = {'schema_version': 'research-evidence-readiness-policy-v1', 'maximum_evidence_age_seconds': 900,
    'modes': ['generative', 'semantic'], 'operational_actions_enabled': False,
    'budget_or_credential_or_model_operations_enabled': False}


def implementation():
    return {'readiness': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'reader': reader.implementation(),
        'limits': limits.implementation(), 'advisor': hashlib.sha256(Path(advisor.__file__).read_bytes()).hexdigest()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY: raise ValueError('fixed_evidence_readiness_required')


def assess(facts, as_of, mode):
    _guard()
    if mode not in POLICY['modes']: raise ValueError('closed_research_readiness_mode_required')
    try: now = timestamp(as_of)
    except (ValueError, TypeError, AttributeError): raise ValueError('valid_readiness_asof_required') from None
    state = facts['state']; reasons = []; ages = {}
    used, cap = state['numeric_lifetime_used'], state['numeric_lifetime_cap']
    if type(used) is not int or type(cap) is not int or not 0 <= used <= cap <= 1000:
        raise ValueError('exact_retained_budget_counts_required')
    if used == cap: reasons.append('prototype_numeric_lifetime_exhausted')
    for name in ('approved_executable_continuation_protocol', 'main_runtime_integrated'):
        if type(state[name]) is not bool: raise ValueError('boolean_research_prerequisites_required')
        if state[name] is not True: reasons.append(name+'_missing')
    missing = facts['missing_original_operational_bindings']
    if type(missing) is not int or not 0 <= missing <= 16: raise ValueError('bounded_original_binding_count_required')
    if missing: reasons.append('original_operational_budget_bindings_missing')
    for name, value in facts['observed_at'].items():
        if name not in ('source', 'free_catalog', 'provider_limits'): raise ValueError('known_evidence_clock_required')
        try: age = (now-timestamp(value)).total_seconds()
        except (ValueError, TypeError, AttributeError): raise ValueError('valid_evidence_timestamp_required') from None
        ages[name] = age
        if age < 0: reasons.append(name+'_observation_is_after_preflight')
        elif age > POLICY['maximum_evidence_age_seconds']: reasons.append(name+'_snapshot_outside_freshness_window')
    if set(ages) != {'source', 'free_catalog', 'provider_limits'}: raise ValueError('all_evidence_clocks_required')
    if facts['fixed_free_catalog_entry_verified'] is not True: reasons.append('fixed_free_catalog_entry_unverified')
    if state['early_primary_captured_label_horizons'] == 0: reasons.append('original_early_label_horizons_unavailable')
    if mode == 'semantic' and state['installed_local_semantic_backend_qualified'] is not True:
        reasons.append('installed_semantic_backend_unqualified')
    core = {'schema_version': 'research-evidence-readiness-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'facts_sha256': digest(facts), 'as_of': as_of, 'mode': mode, 'status': 'blocked' if reasons else 'evidence_checks_passed_review_only',
        'blocking_reasons': reasons, 'evidence_ages_seconds': ages, 'prototype_numeric_attempts_remaining': cap-used,
        'shared_provider_free_daily_remaining': facts['shared_provider_free_daily_remaining'],
        'shared_provider_counter_is_project_allowance': False, 'manual_patch_required_as_new_MVP_gate': False,
        'operational_actions_enabled': False, 'existing_phase_or_trainer_admission_replaced': False,
        'new_allowance_worker_HTTP_SQL_credential_or_model_operation': False}
    return {**core, 'readiness_sha256': digest(core)}


def load(root):
    _guard(); root = Path(root).absolute()
    private = reader.late.cohort.values.private
    raw_read = lambda path, maximum: private._private_read(path.parent, path.name, maximum)
    read = lambda path, maximum=262144: strict_json(raw_read(path, maximum).decode(), max_bytes=maximum)
    state_path = root/'.local/research-checklist-reconcile-real-20261026/current-status.json'
    state = read(state_path); source_pack = root/'.local/research-cohort-reader-real-20261026/reader'; source = reader.verify(source_pack)
    catalog_dir = root/'.local/research-backend-refresh-real-20261026/observations'
    catalog_raw = raw_read(catalog_dir/'catalog-body.json', 1000000)
    catalog = strict_json(catalog_raw.decode(), max_bytes=1000000); receipt = read(catalog_dir/'catalog-receipt.json')
    if hashlib.sha256(catalog_raw).hexdigest() != receipt['body_sha256']:
        raise ValueError('original_catalog_body_required')
    if advisor.free_model_receipt(catalog, advisor.DEFAULT_MODEL) != receipt['free_model_receipt']:
        raise ValueError('same_fixed_free_catalog_receipt_required')
    folder = root/'.local/research-provider-limits-real-20261026/captured'; spend = read(folder/'normalized-revalidated.json')
    if limits.normalize(read(folder/'sanitized-native.json'), spend['observed_at'], response_sha256=spend['response_sha256']) != spend:
        raise ValueError('same_sanitized_provider_limit_receipt_required')
    ref_path = root/'.local/research-checklist-reconcile-real-20261026/source-reference.json'; ref = read(ref_path)
    for entry in ref['original_journals']:
        if hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('original_research_budget_history_changed')
    common = next(e for e in ref['original_journals'] if e['kind'] == 'common_v5')
    paths = [*common['options']['bindings'].values(), common['options']['semantic_live_ledger']]
    missing = sum(not Path(path).is_file() for path in paths)
    free = spend['free_model_daily_requests']
    facts = {'state': state, 'observed_at': {'source': source['native_source_admission']['as_of'],
        'free_catalog': receipt['completed_at'], 'provider_limits': spend['observed_at']},
        'fixed_free_catalog_entry_verified': True, 'missing_original_operational_bindings': missing,
        'shared_provider_free_daily_remaining': None if free is None else free['remaining']}
    files = [state_path, ref_path, catalog_dir/'catalog-body.json', catalog_dir/'catalog-receipt.json',
        folder/'normalized-revalidated.json', folder/'sanitized-native.json']+[source_pack/n for n in ('policy.json', 'binding.json', 'native.json', 'audit.json')]
    binding = {'worktree': str(root), 'files': {str(p): hashlib.sha256(raw_read(p, 1048576)).hexdigest() for p in files}}
    return binding, facts


def prepare(directory, root, mode, as_of=None):
    _guard(); directory = Path(directory).absolute(); reader.late.cohort.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_readiness_directory_required')
    binding, facts = load(root); report = assess(facts, as_of or datetime.now(timezone.utc).isoformat(), mode)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', binding), ('facts.json', facts), ('readiness.json', report)):
        reader.late.cohort.values.files._write(directory, name, value)
    return report


def verify(directory):
    _guard(); directory = reader.late.cohort.values.private._safe_directory(directory, private=True)
    read = lambda name: reader.late.cohort.values.temporal._read(directory, name, 262144)
    if read('policy.json') != POLICY: raise ValueError('fixed_readiness_policy_required')
    saved = read('binding.json'); binding, facts = load(saved['worktree']); result = read('readiness.json')
    if binding != saved or facts != read('facts.json'): raise ValueError('original_readiness_evidence_changed')
    report = assess(facts, result['as_of'], result['mode'])
    if report != result: raise ValueError('saved_readiness_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'inspect': command.add_argument('--worktree', type=Path, required=True); command.add_argument('--mode', choices=POLICY['modes'], required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.worktree, args.mode) if args.command == 'inspect' else verify(args.directory)
    except Exception:
        print('Evidence readiness refused; no operation authorized'); return 2
    print('Evidence readiness: '+report['status']+'; no operation authorized'); return 0


if __name__ == '__main__': raise SystemExit(main())
