"""Review-only historical allocation scenario; cannot mutate or activate budgets."""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path

from cryptoforge import research_budget_inventory as inventory
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


POLICY = {'schema_version': 'research-historical-debits-policy-v1',
    'api_reservation_kind': 'proposal', 'legacy_attempt_reservation_kind': 'fit',
    'offline_fixture_reservation_kind': 'semantic_fixture',
    'overlap_treatment': 'charge_every_visible_row_in_dry_allocation_scenario',
    'prior_numeric_control_charges': 'already_in_native_common_snapshot_do_not_recharge',
    'limits_may_increase': False, 'refunds_enabled': False, 'activation_enabled': False,
    'actual_consumption_upper_bound_claimed': False}


def implementation():
    return {'debits': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'inventory': inventory.implementation()}


_LOADED = implementation()
_POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('historical_debit_source_or_policy_changed')


def bind(directory):
    directory = inventory.private._safe_directory(directory, private=True)
    report = inventory.verify(directory)
    request = inventory.temporal._read(directory, 'request.json', 64000)
    common_refs = [ref for ref in request['journals'] if ref['kind'] == 'common_v5']
    if len(common_refs) != 1: raise ValueError('one_original_common_budget_required')
    ref = common_refs[0]; db = inventory._connect(ref)
    try:
        def read(table):
            rows = db.execute('SELECT id,payload,sha FROM '+table).fetchall()
            if len(rows) != 1 or rows[0][0] != 1: raise ValueError('single_original_policy_required')
            return inventory._payload(rows[0][1], rows[0][2])
        policies = {'resources': read('coordinated_resource_policy'),
            'semantic_live': read('coordinated_semantic_extension')['configuration']['policy'],
            'code_check': read('coordinated_code_extension')['configuration']['policy']}
    finally: db.close()
    inventory._pinned(ref)
    hashes = {name: hashlib.sha256(inventory.private._private_read(directory, name,
        inventory.POLICY['maximum_report_bytes'])).hexdigest() for name in ('policy.json', 'request.json', 'inventory.json')}
    return {'directory': str(directory), 'files': hashes, 'inventory_sha256': report['inventory_sha256']}, report, policies


def _charge_tokens(tokens, allocation):
    """Charge full reservations and at least recorded usage; unknown overrun stays unknown."""
    tokens = inventory.resources.validate_tokens(tokens)
    result = {name: max(allocation[name], tokens[name] or 0) for name in ('input_tokens', 'output_tokens')}
    total = tokens['total_tokens']
    if total is not None and sum(result.values()) < total:
        # Both components cannot be known here: validate_tokens enforces their sum.
        for name in ('input_tokens', 'output_tokens'):
            if tokens[name] is None:
                other = 'output_tokens' if name == 'input_tokens' else 'input_tokens'
                result[name] = max(result[name], total-(tokens[other] or 0))
    return result


def compose(binding, report, policies):
    _guard()
    if (report['inventory_sha256'] != binding['inventory_sha256']
            or report['inventory_sha256'] != digest({key: value for key, value in report.items() if key != 'inventory_sha256'})):
        raise ValueError('verified_original_inventory_required')
    common_entries = [entry for entry in report['journals'] if entry['kind'] == 'common_v5']
    if len(common_entries) != 1: raise ValueError('one_original_common_budget_required')
    common = common_entries[0]; snapshot = common['native_snapshot']
    base_policy = inventory.phase.common.validate_policy(snapshot['manifest']['policy'])
    resource_policy = inventory.resources.validate_resources(policies['resources'])
    semantic_policy = inventory.phase.common.validate_semantic_policy(policies['semantic_live'])
    code_policy = inventory.phase.code.validate_policy(policies['code_check'])
    inherited = {**base_policy['maximum_by_kind'], 'semantic_live': semantic_policy['maximum_actions'],
        'code_check': code_policy['maximum_actions'], 'numeric_control': snapshot['numeric_control_lifetime_limit']}
    base_counts = {name: snapshot['reserved_by_kind'].get(name, 0) for name in inherited}
    counts = dict(base_counts); allocated = dict(snapshot['resources']['reserved_allocations'])
    total = snapshot['total_reserved_actions']; daily = snapshot['daily_reserved_actions']
    questions = snapshot['reserved_semantic_questions']; charges = []
    day = snapshot['utc_day']
    if day != timestamp(report['observed_at']).date().isoformat(): raise ValueError('same_snapshot_day_required')
    inner_paths = set(snapshot['manifest']['journal_path_hashes'].values())
    for entry in report['journals']:
        if entry['id'] == common['id']: continue
        if entry['path_sha256'] in inner_paths:
            raise ValueError('already_bound_inner_journal_requires_exact_operation_linkage')
        kind = entry['kind']; extra_questions = 0
        if kind == 'api':
            target = 'proposal'; rows = entry['reserved_requests']
            if rows != len(entry['records']): raise ValueError('original_api_reservation_coverage_required')
            new_daily = entry['reserved_on_snapshot_utc_day']
            rate = inventory.resources.allocation(resource_policy, target, semantic_policy, code_policy)
            delta = {'input_tokens': 0, 'output_tokens': 0, 'wall_ms': rows*rate['wall_ms']}
            for row in entry['records']:
                for field, value in _charge_tokens(row['tokens'], rate).items(): delta[field] += value
        elif kind == 'attempts':
            target = 'fit'; rows = entry['reserved_attempts']
            if rows != len(entry['records']): raise ValueError('original_attempt_reservation_coverage_required')
            new_daily = sum(timestamp(row['observed_at']).date().isoformat() == day for row in entry['records'])
            rate = inventory.resources.allocation(resource_policy, target, semantic_policy, code_policy)
            delta = {field: rows*value for field, value in rate.items()}
        elif kind == 'semantic_fixture':
            target = 'semantic_fixture'; source = entry['native_snapshot']; rows = source['total_requests']
            new_daily = source['daily_requests']; extra_questions = source['total_questions']
            rate = inventory.resources.allocation(resource_policy, target, semantic_policy, code_policy)
            delta = {field: rows*value for field, value in rate.items()}
        else:
            raise ValueError('known_standalone_reservation_kind_required')
        if any(type(value) is not int or value < 0 for value in (rows, new_daily, extra_questions)):
            raise ValueError('nonnegative_original_reservations_required')
        counts[target] += rows; total += rows; daily += new_daily; questions += extra_questions
        for field, value in delta.items(): allocated[field] += value
        charges.append({'journal_id': entry['id'], 'source_sha256': entry['source_sha256'], 'charge_kind': target,
            'reservation_rows_charged': rows, 'snapshot_day_rows_charged': new_daily,
            'question_reservations_charged': extra_questions, 'allocation_charge': delta,
            'copy_or_execution_overlap_resolved': False, 'actual_consumption_verified': False})
    caps = {field: resource_policy['total_'+field] for field in ('input_tokens', 'output_tokens', 'wall_ms')}
    balance = {field: caps[field]-allocated[field] for field in caps}
    remaining = {'total_actions': max(0, base_policy['total_actions']-total),
        'snapshot_day_actions': max(0, base_policy['daily_actions']-daily),
        'semantic_questions': max(0, base_policy['semantic_questions']-questions),
        'by_kind': {name: max(0, maximum-counts[name]) for name, maximum in inherited.items()},
        'resources': {field: max(0, value) for field, value in balance.items()}}
    scenarios = {}
    for kind in inherited:
        if kind == 'numeric_control':
            scenarios[kind] = 0; continue
        rate = inventory.resources.allocation(resource_policy, kind, semantic_policy, code_policy)
        available = [remaining['total_actions'], remaining['snapshot_day_actions'], remaining['by_kind'][kind]]
        available += [remaining['resources'][field]//value for field, value in rate.items() if value]
        if kind in ('semantic_live', 'semantic_fixture'): available.append(remaining['semantic_questions'])
        scenarios[kind] = min(available)
    blockers = ['explicit_continuation_protocol_not_approved', 'account_wide_jobpilot_spend_unverified',
        'actual_consumption_not_hard_bounded_by_admission_allocations']
    if report['overlapping_attempt_identity_groups'] or report['byte_identical_journal_groups']:
        blockers.append('execution_replay_copy_lineage_unresolved')
    if not all(common['original_binding_files_present'].values()): blockers.append('operational_inner_journals_not_qualified')
    if counts['fit'] >= inherited['fit']: blockers.append('dry_scenario_fit_reservation_limit_exhausted')
    if scenarios['proposal'] == 0: blockers.append('dry_scenario_proposal_admission_unavailable')
    core = {'schema_version': 'research-historical-debits-v1', 'status': 'review_only_no_activation',
        'source_binding_sha256': digest(binding), 'inventory_sha256': report['inventory_sha256'],
        'policy_sha256': digest(POLICY), 'original_policies_sha256': digest(policies), 'snapshot_utc_day': day,
        'original_native_common': {'total_reserved_actions': snapshot['total_reserved_actions'],
            'reserved_by_kind': base_counts, 'reserved_allocations': snapshot['resources']['reserved_allocations']},
        'unchanged_limits': {'total_actions': base_policy['total_actions'], 'daily_actions': base_policy['daily_actions'],
            'by_kind': inherited, 'semantic_questions': base_policy['semantic_questions'], 'resources': caps},
        'proposed_historical_allocation_charges': charges,
        'hypothetical_after_charges': {'total_reserved_actions': total, 'snapshot_day_reserved_actions': daily,
            'reserved_by_kind': counts, 'semantic_questions_reserved': questions, 'reserved_allocations': allocated},
        'hypothetical_remaining': remaining,
        'resource_allocation_overruns': {field: max(0, -value) for field, value in balance.items()},
        'alternative_additional_actions_by_kind': scenarios, 'scenarios_share_one_budget_and_cannot_be_added': True,
        'alternative_semantic_action_assumption_questions_per_action': 1,
        'activation_blockers': blockers, 'overlap_groups_preserved': len(report['overlapping_attempt_identity_groups']),
        'actual_total_consumption': None, 'account_wide_spend_usd': None,
        'journal_or_caps_or_reservations_changed': False, 'new_allowances_or_refunds': False,
        'native_budget_admission_rights_granted': False, 'numeric_control_cache_only': True,
        'fit_executed': False, 'provider_called': False, 'model_prediction_performed': False,
        'production_promotion_authorized': False, 'implementation': _LOADED}
    _guard(); return {**core, 'proposal_sha256': digest(core)}


def prepare(directory, inventory_pack):
    _guard(); directory = Path(directory).absolute(); inventory.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_historical_debits_directory_required')
    bound = bind(inventory_pack); report = compose(*bound)
    directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('source-binding.json', bound[0]), ('policies.json', bound[2]), ('proposal.json', report)):
        inventory.files._write(directory, name, value)
    inventory.files._sync(directory); inventory.files._sync(directory.parent); return report


def verify(directory):
    _guard(); directory = inventory.private._safe_directory(directory, private=True)
    read = lambda name: inventory.temporal._read(directory, name, inventory.POLICY['maximum_report_bytes'])
    if read('policy.json') != POLICY: raise ValueError('fixed_dry_debit_policy_required')
    binding = read('source-binding.json'); bound = bind(binding['directory'])
    if bound[0] != binding or bound[2] != read('policies.json'): raise ValueError('original_inventory_or_budget_policies_changed')
    report = compose(*bound)
    if canonical(report) != canonical(read('proposal.json')): raise ValueError('historical_debit_proposal_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--inventory-pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = verify(args.directory) if args.command == 'verify' else prepare(args.directory, args.inventory_pack)
    except Exception:
        print('Historical allocation proposal refused; budgets unchanged'); return 2
    print('Historical allocation proposal verified: '+report['status']+'; budgets unchanged'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
