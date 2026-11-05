"""Explain retained native source exclusions before any model hypothesis or API call."""
import argparse
from datetime import timedelta
from decimal import Decimal
from fractions import Fraction
import hashlib
from pathlib import Path

from cryptoforge import research_cohort_http_audit as source
from cryptoforge.research_training_diagnostics import canonical, digest

POLICY = {'schema_version': 'research-source-diagnostics-policy-v1', 'pairs': source.POLICY['pairs'],
    'timeframe_seconds': 300, 'feature_lookback_candles': 120, 'horizon_candles': 3,
    'minimum_known_closed_rows': 123, 'maximum_source_age_microseconds': 900000000,
    'minimum_pair_coverage_numerator': 4, 'minimum_pair_coverage_denominator': 5,
    'provider_requests_enabled': False, 'model_fit_prediction_enabled': False, 'training_admission_enabled': False}


def implementation():
    return {'diagnostics': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'source': source.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY: raise ValueError('fixed_source_diagnostics_required')


def _microseconds(delta):
    return (delta.days*86400+delta.seconds)*1000000+delta.microseconds


def pair_diagnostics(pair, rows, as_of):
    """Disjoint eligibility reasons and the pinned native loader's first refusal."""
    cutoff = source.wire.stamp(as_of); groups = {k: 0 for k in ('not_closed_by_cutoff', 'ingested_before_close', 'ingested_after_cutoff', 'known_closed')}
    known = []; ordered = []
    if pair not in POLICY['pairs'] or type(rows) is not list or len(rows) > 500: raise ValueError('fixed_source_pair_and_row_limit_required')
    for row in rows:
        opened = source.wire.stamp(row['open_time']); ingested = source.wire.stamp(row['ingested_at']); closed = opened+timedelta(minutes=5)
        ordered.append(opened)
        if closed > cutoff: reason = 'not_closed_by_cutoff'
        elif ingested < closed: reason = 'ingested_before_close'
        elif ingested > cutoff: reason = 'ingested_after_cutoff'
        else: reason = 'known_closed'; known.append(opened)
        groups[reason] += 1
    if ordered != sorted(set(ordered), reverse=True): raise ValueError('unique_descending_source_rows_required')
    known = sorted(known); gaps = [{'previous_open': left.isoformat(), 'next_open': right.isoformat(),
        'missing_5m_intervals': int((right-left).total_seconds())//300-1}
        for left, right in zip(known, known[1:]) if right-left != timedelta(minutes=5)]
    latest = known[-1]+timedelta(minutes=5) if known else None
    age = _microseconds(cutoff-latest) if latest is not None else None
    if gaps: refusal = 'duplicate, unordered or gapped training candles'
    elif not known: refusal = 'no known closed source candles'
    elif age > POLICY['maximum_source_age_microseconds']: refusal = 'stale closed training source'
    elif len(known) < POLICY['minimum_known_closed_rows']: refusal = 'insufficient closed history for complete labels'
    else: refusal = None
    return {'pair': pair, 'rows': len(rows), 'eligibility': groups,
        'latest_cached_open': max(ordered).isoformat() if ordered else None,
        'latest_known_closed_at': latest.isoformat() if latest else None, 'latest_known_closed_age_microseconds': age,
        'known_closed_gap_count': len(gaps), 'known_closed_missing_intervals': sum(g['missing_5m_intervals'] for g in gaps),
        'first_known_closed_gaps': gaps[:8], 'expected_native_exclusion': refusal,
        'expected_native_examples': len(known)-122 if refusal is None else 0,
        'upstream_venue_or_collector_fault_identified': False}


def compose(rows, native_audit):
    _guard()
    if type(rows) is not dict or set(rows) != set(POLICY['pairs']): raise ValueError('all_fixed_source_pairs_required')
    admission = native_audit['native_source_admission']; as_of = native_audit['capture_completed_at']
    if (native_audit['schema_version'] != 'research-cohort-HTTP-audit-v1' or admission['requested_pairs'] != POLICY['pairs']
            or admission['as_of'] != as_of or admission['status'] != 'completed'
            or admission['gap_filling_allowed'] is not False or admission['minimum_source_coverage'] != .8
            or admission['maximum_source_age_seconds'] != 900):
        raise ValueError('original_pinned_native_source_contract_required')
    pairs = [pair_diagnostics(pair, rows[pair], as_of) for pair in POLICY['pairs']]
    accepted = [row['pair'] for row in pairs if row['expected_native_exclusion'] is None]
    excluded = {row['pair']: row['expected_native_exclusion'] for row in pairs if row['expected_native_exclusion'] is not None}
    latest = {row['pair']: row['latest_known_closed_at'] for row in pairs if row['latest_known_closed_at'] is not None and not row['known_closed_gap_count']}
    examples = sum(row['expected_native_examples'] for row in pairs)
    if (admission['accepted_pairs'] != accepted or admission['excluded_pairs'] != excluded
            or type(admission['examples']) is not int or admission['examples'] != examples
            or type(native_audit['native_all_examples']) is not int or native_audit['native_all_examples'] != examples
            or set(admission['last_closed_at_by_pair']) != set(latest)
            or any(source.wire.stamp(admission['last_closed_at_by_pair'][p]) != source.wire.stamp(v) for p, v in latest.items())
            or type(admission['coverage_fraction']) not in (float, int)
            or Fraction(str(admission['coverage_fraction'])) != Fraction(len(accepted), len(POLICY['pairs']))):
        raise ValueError('independent_source_diagnostics_do_not_reconcile_with_native_loader')
    coverage = Fraction(len(accepted), 20); minimum = Fraction(4, 5)
    numeric_pass = (type(native_audit['scalar_mismatch_count']) is int and native_audit['scalar_mismatch_count'] == 0
        and type(native_audit['independent_sample_mismatches']) is int and native_audit['independent_sample_mismatches'] == 0
        and native_audit['all_native_examples_equal_exact_parser'] is True)
    enough = coverage >= minimum; reasons = []
    if not enough: reasons.append('minimum_pair_coverage_not_met')
    if not numeric_pass: reasons.append('source_numeric_parity_not_verified')
    if examples == 0: reasons.append('no_complete_native_examples')
    route = 'review_source_data' if reasons else 'review_research_protocol'
    core = {'schema_version': 'research-source-diagnostics-v1', 'implementation': _LOADED, 'policy_sha256': digest(POLICY),
        'source_audit_sha256': native_audit['audit_sha256'], 'capture_sha256': native_audit['capture_sha256'],
        'diagnostic_as_of': as_of, 'evidence_kind': native_audit['evidence_kind'], 'pairs': pairs,
        'accepted_pairs': accepted, 'excluded_pairs': excluded, 'native_examples': examples,
        'coverage': {'accepted_pairs': len(accepted), 'requested_pairs': 20, 'numerator': coverage.numerator, 'denominator': coverage.denominator,
            'minimum_numerator': 4, 'minimum_denominator': 5, 'minimum_satisfied': enough},
        'error_attribution': {'data_source': 'observed_failure' if not enough or examples == 0 else 'minimum_pair_gate_only_satisfied',
            'numeric_transport_and_selected_features_labels': 'no_mismatch_on_checked_values' if numeric_pass else 'not_verified',
            'model_prediction_quality': 'not_evaluated', 'strategy_execution': 'not_evaluated', 'trade_accounting': 'not_evaluated'},
        'proposal_route': route, 'source_blocking_reasons': reasons, 'eligible_model_parameter_proposals': [],
        'provider_request_authorized': False, 'training_admission_authorized': False, 'model_fit_prediction_provider_actions': 0,
        'numeric_budget_change_or_new_allowance': False, 'old_windows_or_candidate_metrics_repaired': False,
        'current_cache_is_historical_first_seen_lineage': False, 'automatically_modify_collector_or_trading': False,
        'quality_status_is_current_at_verify_time': False, 'full_training_protocol_approved': False}
    return {**core, 'report_sha256': digest(core)}


def load(source_pack):
    source_pack = source.prior.late.cohort.values.private._safe_directory(source_pack, private=True)
    report = source.verify(source_pack); saved, rows, _, _ = source.inspect_capture(source_pack/'captures')
    if report['capture_sha256'] != digest(saved): raise ValueError('same_original_HTTP_source_required')
    names = ['policy.json', 'binding.json', 'native.json', 'audit.json', 'captures/capture.json']
    names += [f'captures/{kind}-{index:02d}.json' for index in range(20) for kind in ('attempt', 'body', 'receipt')]
    binding = {'source_pack': str(source_pack), 'files': {name: hashlib.sha256((source_pack/name).read_bytes()).hexdigest() for name in names}}
    return binding, compose(rows, report)


def prepare(directory, source_pack):
    _guard(); directory = Path(directory).absolute(); source.prior.late.cohort.values.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_source_diagnostics_directory_required')
    binding, report = load(source_pack); directory.mkdir(mode=0o700)
    for name, value in (('policy.json', POLICY), ('binding.json', binding), ('diagnostics.json', report)):
        source.prior.late.cohort.values.files._write(directory, name, value)
    return report


def verify(directory):
    _guard(); directory = source.prior.late.cohort.values.private._safe_directory(directory, private=True)
    read = lambda name: source.prior.late.cohort.values.temporal._read(directory, name, 262144)
    if read('policy.json') != POLICY: raise ValueError('original_source_diagnostics_policy_changed')
    saved = read('binding.json'); binding, report = load(saved['source_pack'])
    if binding != saved or report != read('diagnostics.json'): raise ValueError('original_source_diagnostics_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'inspect': command.add_argument('--source-pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.source_pack) if args.command == 'inspect' else verify(args.directory)
    except Exception:
        print('Source diagnostics refused; no model or provider action authorized'); return 2
    print('Source diagnostics: '+report['proposal_route']+'; no model or provider action authorized'); return 0


if __name__ == '__main__': raise SystemExit(main())
