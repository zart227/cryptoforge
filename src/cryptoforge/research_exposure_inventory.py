"""Read-only inventory of the retained M48, M52 and M64 exposure manifests.

A missing flag or a zero mismatch count does not prove holdout independence.
The inventory reads local JSON only. It does not train, query a database,
contact a provider or change the manifests.
"""
import argparse
import hashlib
import json
from pathlib import Path

from cryptoforge.research_training_diagnostics import canonical, digest


SCHEMA = 'exposure-inventory-v1'
ADMISSION_KEYS = frozenset({
    'training_admitted', 'training_data_admitted', 'training_admission_enabled',
    'approved_dataset_or_training_admission', 'whole_dataset_admitted',
    'training_data_protocol_or_next_budget_approved', 'source_or_model_training_admission'})
INDEPENDENCE_KEYS = frozenset({
    'holdout_independence_attested', 'independent_holdout_or_prospective_study',
    '20_cross_market_samples_assumed_independent'})
MISMATCH_KEYS = frozenset({
    'wire_numeric_scalar_mismatches', 'independent_sample_mismatches'})
BINDINGS = (
    {'id': 'M48', 'exposure': '.local/research-cohort-http-real-20261026/exposures.json',
     'schema_version': 'cohort-HTTP-development-exposure-v1',
     'companions': (
         '.local/research-cohort-http-real-20261026/verification.json',
         '.local/research-cohort-http-real-20261026/pack/audit.json',
         '.local/research-cohort-http-real-20261026/pack/policy.json')},
    {'id': 'M52', 'exposure': '.local/research-cohort-and-fit-graph-real-20261026/exposures.json',
     'schema_version': 'prospective-cohort-source-exposure-v1',
     'companions': (
         '.local/research-cohort-and-fit-graph-real-20261026/original-source/feature-slot-progress.json',
         '.local/research-cohort-and-fit-graph-real-20261026/archived-source-values/audit.json',
         '.local/research-cohort-and-fit-graph-real-20261026/archived-source-values/policy.json')},
    {'id': 'M64', 'exposure': '.local/research-source-dataset-real-20261028/exposure.json',
     'schema_version': 'source-dataset-exposure-record-v1',
     'companions': (
         '.local/research-source-dataset-real-20261028/review/review.json',
         '.local/research-source-dataset-real-20261028/review/policy.json',
         '.local/research-source-dataset-real-20261028/observations.json')},
)


def _load(root, relative):
    path = Path(root) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular exposure manifest required')
    raw = path.read_bytes()
    if not 2 <= len(raw) <= 2_000_000:
        raise ValueError('bounded exposure manifest required')
    try:
        text = raw.decode()
    except UnicodeError:
        raise ValueError('utf-8 exposure manifest required') from None
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate exposure key')
            result[key] = value
        return result
    def reject_nonfinite(_value):
        raise ValueError('nonfinite exposure number')
    try:
        document = json.loads(text, object_pairs_hook=pairs, parse_constant=reject_nonfinite)
    except (json.JSONDecodeError, RecursionError):
        raise ValueError('invalid exposure manifest') from None
    if type(document) is not dict:
        raise ValueError('exposure manifest object required')
    return document, hashlib.sha256(raw).hexdigest()


def flags_from(document):
    """Copy only explicit admission and independence booleans.

    Recomputed-component counts that happen to contain the word independent
    are mismatch observations. They are not holdout attestation.
    """
    found = []
    for key in sorted(ADMISSION_KEYS | INDEPENDENCE_KEYS):
        if key not in document:
            found.append({'key': key, 'present': False, 'value': None})
            continue
        value = document[key]
        if type(value) is not bool:
            raise ValueError('boolean exposure flag required')
        found.append({'key': key, 'present': True, 'value': value})
    return found


def reject_admitted_flags(records):
    """Fail when any reviewed set admits training or attests holdout independence."""
    for record in records:
        for flag in record['flags']:
            if flag['present'] and flag['value'] is True and flag['key'] in ADMISSION_KEYS | INDEPENDENCE_KEYS:
                raise ValueError('reviewed_exposure_admits_training_or_independence')
    return records


def _mismatch(document):
    observed = {}
    for key in sorted(MISMATCH_KEYS):
        if key in document:
            value = document[key]
            if type(value) is not int or value < 0:
                raise ValueError('nonnegative mismatch count required')
            observed[key] = value
    return {'observed': observed, 'absence_or_zero_proves_holdout_independence': False}


def _windows(binding_id, exposure, companions):
    if binding_id == 'M48':
        entries = exposure['entries']
        if type(entries) is not list or not entries:
            raise ValueError('M48 exposure entries required')
        pairs = [row['pair'] for row in entries]
        if len(pairs) != len(set(pairs)):
            raise ValueError('duplicate M48 pair')
        return {'purpose': exposure['scope'], 'pairs': pairs, 'pair_count': len(pairs),
            'roles': sorted({row['role'] for row in entries}),
            'registered_at': exposure['registered_at'],
            'capture_started_at': exposure['first_current_client_capture_started_at'],
            'capture_completed_at': exposure['current_capture_completed_at'],
            'earliest_open': min(row['first_open_time'] for row in entries),
            'latest_open': max(row['last_open_time'] for row in entries),
            'earliest_label_close': min(row['latest_label_close_time'] for row in entries),
            'latest_label_close': max(row['latest_label_close_time'] for row in entries),
            'historical_lineage_claimed': exposure['historical_first_seen_or_revisions_claimed'],
            'future_final_or_forward_requested': exposure['future_final_test_or_forward_data_intentionally_requested']}
    if binding_id == 'M52':
        pairs = exposure['pairs']
        if type(pairs) is not list or len(pairs) != len(exposure['observations']):
            raise ValueError('M52 pair observations required')
        return {'purpose': exposure['scope'], 'pairs': list(pairs), 'pair_count': len(pairs),
            'feature_anchor': exposure['feature_anchor'], 'decision_at': exposure['decision_at'],
            'label_close_anchor': exposure['label_close_anchor'],
            'label_information_end': exposure['label_information_end'],
            'distinct_decision_anchors': exposure['distinct_decision_anchors'],
            'all_labels_exposed_development': exposure['all_labels_now_exposed_development'],
            'approved_train_validation_manifest_created': exposure['approved_train_validation_manifest_created'],
            'final_or_forward_requested': exposure['final_test_28_29_or_forward_30_31_Oct_requested']}
    review = companions['.local/research-source-dataset-real-20261028/review/review.json']
    split = exposure['candidate_split_train_validation_purged']
    return {'purpose': exposure['purpose'], 'scope': exposure['scope'],
        'pairs_with_examples': list(exposure['pairs_with_examples']),
        'pair_count_with_examples': len(exposure['pairs_with_examples']),
        'earliest_example_open': exposure['earliest_example_open'],
        'latest_example_open': exposure['latest_example_open'],
        'latest_label_end': exposure['latest_label_end'],
        'source_capture_as_of': exposure['source_capture_as_of'],
        'split': split, 'source_coverage': review['source_coverage'],
        'global_exposure_inventory_complete': exposure['global_exposure_inventory_complete']}


def _coverage(records, documents):
    by_id = {record['id']: record for record in records}
    cohort = by_id['M48']['windows']['pairs']
    if by_id['M52']['windows']['pairs'] != cohort:
        raise ValueError('M48 and M52 pair cohorts differ')
    present = set(by_id['M64']['windows']['pairs_with_examples'])
    if not present <= set(cohort):
        raise ValueError('M64 pair outside the retained cohort')
    m48 = documents['.local/research-cohort-http-real-20261026/verification.json']
    m64_coverage = by_id['M64']['windows']['source_coverage']
    reasons = []
    if m48['minimum_pair_coverage_satisfied'] is not False or m48['native_pair_coverage'] < m48['minimum_native_pair_coverage']:
        reasons.append('M48 native pair coverage is below its saved minimum')
    if by_id['M52']['windows']['approved_train_validation_manifest_created'] is not False:
        raise ValueError('M52 exposure claims an approved manifest')
    if by_id['M52']['windows']['distinct_decision_anchors'] != 1:
        reasons.append('M52 decision-anchor count is not the retained single anchor')
    reasons.append('M52 observes one decision anchor and has no approved train/validation manifest')
    if m64_coverage['minimum_satisfied'] is not False or m64_coverage['numerator'] < m64_coverage['requested_pairs']:
        reasons.append('M64 source coverage is below its saved minimum')
    if by_id['M64']['windows']['global_exposure_inventory_complete'] is not False:
        raise ValueError('M64 exposure claims a complete global inventory')
    missing = [pair for pair in cohort if pair not in present]
    return {'complete': False, 'reasons': reasons, 'cohort_pairs': cohort,
        'm64_pairs_with_examples': sorted(present), 'm64_pairs_absent_from_examples': missing,
        'm48_native_pair_coverage': m48['native_pair_coverage'],
        'm48_minimum_native_pair_coverage': m48['minimum_native_pair_coverage'],
        'm64_accepted_pairs': m64_coverage['numerator'], 'm64_requested_pairs': m64_coverage['requested_pairs']}


def inventory(root):
    records = []
    documents = {}
    for binding in BINDINGS:
        exposure, exposure_hash = _load(root, binding['exposure'])
        if exposure.get('schema_version') != binding['schema_version']:
            raise ValueError('pinned exposure schema required')
        companions = {}
        companion_hashes = {}
        for relative in binding['companions']:
            document, file_hash = _load(root, relative)
            companions[relative] = document
            companion_hashes[relative] = file_hash
            documents[relative] = document
        documents[binding['exposure']] = exposure
        combined = []
        for document in (exposure, *companions.values()):
            combined.extend(flags_from(document))
        mismatches = []
        for relative, document in ((binding['exposure'], exposure), *companions.items()):
            item = _mismatch(document)
            if item['observed']:
                mismatches.append({'path': relative, **item})
        records.append({'id': binding['id'], 'exposure': binding['exposure'],
            'exposure_sha256': exposure_hash, 'companion_sha256': companion_hashes,
            'windows': _windows(binding['id'], exposure, companions), 'flags': combined,
            'mismatch_observations': mismatches,
            'absence_of_a_flag_or_mismatch_proves_independence': False})
    reject_admitted_flags(records)
    covered = _coverage(records, documents)
    report = {'schema_version': SCHEMA, 'records': records, 'coverage': covered,
        'training_admitted': False, 'holdout_independence_attested': False,
        'independence_proven': False, 'coverage_complete': covered['complete'],
        'network_database_fit_or_provider_actions': 0}
    report['report_sha256'] = digest({key: value for key, value in report.items() if key != 'report_sha256'})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Write the retained exposure inventory')
    parser.add_argument('--root', default='.')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    report = inventory(args.root)
    destination = Path(args.output)
    if destination.exists():
        raise ValueError('exposure inventory output already exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(canonical({'schema_version': report['schema_version'], 'report_sha256': report['report_sha256'],
        'coverage_complete': report['coverage_complete'], 'training_admitted': report['training_admitted'],
        'holdout_independence_attested': report['holdout_independence_attested']}))


if __name__ == '__main__':
    main()
