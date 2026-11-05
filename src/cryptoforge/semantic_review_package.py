"""Blank human-review tasks with immutable evidence and explicit completion.

Never invents human labels or creates a holdout from related configurations.
Reviewer declarations are recorded, not independently authenticated.
"""
import argparse
import os
from pathlib import Path

from cryptoforge.semantic_research_catalog import record_from_receipt, validate_record
from cryptoforge.semantic_annotation_benchmark import sha, validate_gold
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp
from cryptoforge.training_experiment_planner import read_json
from cryptoforge.typesafe_judgment_contracts import validate_catalog, text


def make_package(entries, catalog):
    validate_catalog(catalog)
    if not isinstance(entries, list) or not 2 <= len(entries) <= 1000:
        raise ValueError('two to 1000 source records required')
    records, seen = [], set()
    for entry in entries:
        exact_fields(entry, {'receipt', 'hypothesis', 'conclusion'})
        record = record_from_receipt(entry['receipt'], hypothesis=entry['hypothesis'], conclusion=entry['conclusion'])
        record_id = record['experiment_id']
        if record_id in seen:
            raise ValueError('duplicate experiment in review package')
        seen.add(record_id)
        state = {'experiment': record}
        records.append({'record_id': record_id, 'state': state, 'state_sha256': digest(state),
            'source_receipt_sha256': digest(entry['receipt']),
            'group_id': digest({'dataset_sha256': record['dataset_sha256']})})
    records.sort(key=lambda r: r['record_id'])
    groups = len({r['group_id'] for r in records})
    return {'schema_version': 'semantic-review-package-v1', 'catalog': catalog, 'records': records,
        'grouping_policy': 'same_dataset_same_group_v1', 'group_count': groups,
        'minimum_group_count_met': groups >= 2, 'independent_groups_audited': False,
        'contains_model_answers': False, 'human_review_completed': False}


def validate_package(package):
    exact_fields(package, {'schema_version', 'catalog', 'records', 'grouping_policy', 'group_count',
        'minimum_group_count_met', 'independent_groups_audited', 'contains_model_answers', 'human_review_completed'})
    if (package['schema_version'] != 'semantic-review-package-v1' or
            package['grouping_policy'] != 'same_dataset_same_group_v1' or
            any(package[k] is not False for k in ('contains_model_answers', 'human_review_completed', 'independent_groups_audited'))):
        raise ValueError('unlabeled research review package required')
    validate_catalog(package['catalog'])
    records = package['records']
    if not isinstance(records, list) or not 2 <= len(records) <= 1000:
        raise ValueError('bounded review records required')
    seen = set()
    for item in records:
        exact_fields(item, {'record_id', 'state', 'state_sha256', 'source_receipt_sha256', 'group_id'})
        for key in ('record_id', 'state_sha256', 'source_receipt_sha256', 'group_id'): sha(item[key])
        exact_fields(item['state'], {'experiment'})
        r = validate_record(item['state']['experiment'])
        if item['record_id'] != r['experiment_id'] or digest(item['state']) != item['state_sha256']:
            raise ValueError('review state identity changed')
        if item['group_id'] != digest({'dataset_sha256': r['dataset_sha256']}):
            raise ValueError('related dataset was split into separate groups')
        if item['record_id'] in seen:
            raise ValueError('duplicate review identity')
        seen.add(item['record_id'])
    count = len({item['group_id'] for item in records})
    if type(package['group_count']) is not int or package['group_count'] != count or package['minimum_group_count_met'] is not (count >= 2):
        raise ValueError('incorrect group qualification')
    return package


def blank_response(package):
    validate_package(package)
    return {'schema_version': 'semantic-review-response-v1', 'package_sha256': digest(package),
        'reviewer_id': None, 'review_kind': None, 'reviewed_at': None,
        'attestation': {'human_authored': False, 'no_model_answers_shown': False},
        'reviews': [{'record_id': r['record_id'], 'state_sha256': r['state_sha256'],
                     'decisions': {name: {'status': 'pending', 'value': None, 'reason': None}
                                   for name in package['catalog']['questions']}} for r in package['records']]}


def complete_review(package, response):
    validate_package(package)
    exact_fields(response, {'schema_version', 'package_sha256', 'reviewer_id', 'review_kind', 'reviewed_at', 'attestation', 'reviews'})
    if response['schema_version'] != 'semantic-review-response-v1' or response['package_sha256'] != digest(package):
        raise ValueError('review belongs to another or changed package')
    text(response['reviewer_id'])
    timestamp(response['reviewed_at'])
    kind = response['review_kind']
    if kind not in ('human_review', 'synthetic_fixture'):
        raise ValueError('human declaration or synthetic fixture origin required')
    exact_fields(response['attestation'], {'human_authored', 'no_model_answers_shown'})
    if any(type(v) is not bool for v in response['attestation'].values()):
        raise ValueError('boolean attestation required')
    if kind == 'human_review' and not all(response['attestation'].values()):
        raise ValueError('explicit human and no-model-answer declarations required')
    if kind == 'synthetic_fixture' and any(response['attestation'].values()):
        raise ValueError('synthetic fixture must not assert human authorship')
    records = {r['record_id']: r for r in package['records']}
    if not isinstance(response['reviews'], list) or len(response['reviews']) != len(records):
        raise ValueError('complete review coverage required')
    seen, examples, rationale = set(), [], []
    for review in response['reviews']:
        exact_fields(review, {'record_id', 'state_sha256', 'decisions'})
        record_id = review['record_id']
        sha(record_id)
        if record_id not in records or record_id in seen:
            raise ValueError('unknown or repeated review record')
        seen.add(record_id)
        item = records[record_id]
        if review['state_sha256'] != item['state_sha256']:
            raise ValueError('review state changed')
        exact_fields(review['decisions'], set(package['catalog']['questions']))
        labels = {}
        for name, decision in review['decisions'].items():
            exact_fields(decision, {'status', 'value', 'reason'})
            if decision['status'] not in ('answered', 'insufficient'):
                raise ValueError('pending labels cannot become human gold')
            text(decision['reason'])
            value = decision['value']
            if decision['status'] == 'insufficient':
                if value is not None: raise ValueError('insufficient evidence needs null label')
            elif value is None:
                raise ValueError('answered label cannot be null')
            labels[name] = value
            rationale.append({'record_id': record_id, 'question_id': name, **decision})
        examples.append({'record_id': record_id, 'group_id': item['group_id'],
                         'state_sha256': item['state_sha256'], 'labels': labels})
    gold = {'schema_version': 'semantic-gold-v1',
            'label_origin': 'human_reviewed' if kind == 'human_review' else 'synthetic_fixture', 'examples': examples}
    gold['examples'] = validate_gold(gold, package['catalog'])
    audit = {'schema_version': 'semantic-review-audit-v1', 'package_sha256': digest(package),
        'response_sha256': digest(response), 'gold_sha256': digest(gold), 'reviewer_id': response['reviewer_id'],
        'reviewed_at': response['reviewed_at'], 'review_kind': kind, 'attestation': response['attestation'],
        'attestation_assurance': 'reviewer_declaration_only', 'independent_label_audit_performed': False,
        'rationale': rationale, 'minimum_group_count_met': package['minimum_group_count_met'],
        'independent_groups_audited': False, 'api_calls': 0}
    return gold, audit


def write_bundle(directory, files):
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, data in files.items():
        fd = os.open(directory/name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical(data)+'\n'); stream.flush(); os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--manifest', type=Path, required=True)
    prepare.add_argument('--questions', type=Path, required=True)
    prepare.add_argument('--directory', type=Path, required=True)
    complete = sub.add_parser('complete')
    complete.add_argument('--package', type=Path, required=True)
    complete.add_argument('--response', type=Path, required=True)
    complete.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        items = read_json(args.manifest)
        if not isinstance(items, list) or not 2 <= len(items) <= 1000:
            raise ValueError('two to 1000 manifest records required')
        entries, total_bytes = [], 0
        for item in items:
            exact_fields(item, {'receipt_path', 'hypothesis', 'conclusion'})
            receipt_path = Path(item['receipt_path'])
            if not receipt_path.is_absolute(): receipt_path = args.manifest.parent/receipt_path
            total_bytes += receipt_path.stat().st_size
            if total_bytes > 32_000_000: raise ValueError('bulk review input size limit exceeded')
            entries.append({'receipt': read_json(receipt_path), 'hypothesis': item['hypothesis'], 'conclusion': item['conclusion']})
        package = make_package(entries, read_json(args.questions))
        write_bundle(args.directory, {'package.json': package, 'response-template.json': blank_response(package)})
        print('Unlabeled human-review tasks prepared; no model answers or API calls')
    else:
        gold, audit = complete_review(read_json(args.package), read_json(args.response))
        write_bundle(args.directory, {'gold.json': gold, 'review-audit.json': audit})
        print('Declared review imported; independent provenance and group qualification remain separate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
