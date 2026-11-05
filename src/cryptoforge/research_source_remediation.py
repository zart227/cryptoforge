"""Explain an already verified source-review snapshot; never admit or refresh data.

Timing calculations are counterfactual boundaries for the original cutoff. They
are not evidence that candles exist, were known in time, or are current now.
"""
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import hashlib
from pathlib import Path

from cryptoforge import research_source_dataset as dataset
from cryptoforge.training_diagnostics import canonical, digest, timestamp

POLICY = {'schema_version':'source-remediation-diagnostic-v1',
          'uses_original_review_only':True, 'historical_lineage_or_repair_attested':False,
          'database_network_provider_fit_prediction_or_admission_enabled':False}


def implementation():
    return {'remediation':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_dataset':dataset.implementation()}


_LOADED=implementation(); _POLICY=canonical(POLICY)


def _guard():
    dataset._guard()
    if implementation()!=_LOADED or canonical(POLICY)!=_POLICY:
        raise ValueError('fixed_source_remediation_required')


def _next_boundary(cutoff, max_age_us, interval_seconds):
    """First five-minute close at or after cutoff minus the permitted age."""
    threshold=timestamp(cutoff)-timedelta(microseconds=max_age_us)
    epoch=datetime(1970,1,1,tzinfo=timezone.utc); delta=threshold-epoch
    micros=(delta.days*86400+delta.seconds)*1_000_000+delta.microseconds
    step=interval_seconds*1_000_000
    return (epoch+timedelta(microseconds=-(-micros//step)*step)).isoformat()


def _derive(review, diagnostic):
    """Input must come from the original verifiers; this function does no I/O."""
    _guard(); policy=dataset.source.POLICY
    if (review['source_diagnostics_sha256']!=diagnostic['report_sha256']
            or review['binding']['capture_sha256']!=diagnostic['capture_sha256']
            or review['source_coverage']!=diagnostic['coverage']
            or review['source_proposal_route']!=diagnostic['proposal_route']
            or review['source_blocking_reasons']!=diagnostic['source_blocking_reasons']
            or review['training_admitted'] is not False
            or review['historical_first_seen_revision_lineage_verified'] is not False
            or review['provider_proposals_authorized'] is not False):
        raise ValueError('same_review_only_source_binding_required')
    pairs=diagnostic['pairs']; names=[row['pair'] for row in pairs]
    if names!=policy['pairs']: raise ValueError('original_ordered_pair_set_required')
    accepted=[row['pair'] for row in pairs if row['expected_native_exclusion'] is None]
    excluded={row['pair']:row['expected_native_exclusion'] for row in pairs if row['expected_native_exclusion'] is not None}
    coverage=diagnostic['coverage']; total=len(names)
    if (accepted!=diagnostic['accepted_pairs'] or excluded!=diagnostic['excluded_pairs']
            or coverage['accepted_pairs']!=len(accepted) or coverage['requested_pairs']!=total):
        raise ValueError('original_coverage_reconciliation_required')
    minimum=Fraction(policy['minimum_pair_coverage_numerator'],policy['minimum_pair_coverage_denominator'])
    required=-(-(minimum.numerator*total)//minimum.denominator)
    if coverage['minimum_satisfied'] != (len(accepted)>=required):
        raise ValueError('original_coverage_gate_required')
    max_age=policy['maximum_source_age_microseconds']
    target=_next_boundary(diagnostic['diagnostic_as_of'],max_age,policy['timeframe_seconds'])
    excluded_rows=[]
    for row in pairs:
        if row['expected_native_exclusion'] is None: continue
        age=row['latest_known_closed_age_microseconds']
        if age is not None and (type(age) is not int or age<0): raise ValueError('original_age_required')
        if row['expected_native_exclusion']=='stale closed training source' and (age is None or age<=max_age):
            raise ValueError('original_stale_age_required')
        excluded_rows.append({'pair':row['pair'],'observed_exclusion':row['expected_native_exclusion'],
            'latest_known_closed_at':row['latest_known_closed_at'],'age_microseconds':age,
            'age_over_limit_microseconds':max(0,age-max_age) if age is not None else None,
            'known_closed_gap_count':row['known_closed_gap_count'],
            'fault_or_historical_availability_identified':False})
    result={'schema_version':'source-remediation-report-v1', 'implementation':_LOADED,
        'policy_sha256':digest(POLICY), 'review_sha256':review['review_sha256'],
        'source_diagnostics_sha256':diagnostic['report_sha256'],'capture_sha256':diagnostic['capture_sha256'],
        'diagnostic_as_of':diagnostic['diagnostic_as_of'],'accepted_pair_count':len(accepted),
        'requested_pair_count':total,'required_pair_count':required,
        'minimum_additional_accepted_pairs_if_existing_remain_accepted':max(0,required-len(accepted)),
        'excluded_pairs':excluded_rows,'maximum_closed_age_microseconds':max_age,
        'first_fresh_close_for_original_cutoff':target,'source_blocking_reasons':diagnostic['source_blocking_reasons'],
        'snapshot_status_is_current':False,'historical_lineage_or_missing_candles_proven':False,
        'coverage_implies_training_or_provider_admission':False,'source_refreshed_or_modified':False,
        'database_network_provider_fit_prediction_actions':0}
    return {**result,'report_sha256':digest(result)}


def analyze_verified(review_directory):
    """Offline re-verification of original capture and replay; no worker or refresh."""
    _guard()
    review=dataset.verify(review_directory)
    diagnostic=dataset.source.verify(review['binding']['diagnostics_directory'])
    result=_derive(review,diagnostic); _guard(); return result
