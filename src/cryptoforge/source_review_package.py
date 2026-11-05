"""Frozen source review sampling, blind forms and two-reviewer disagreements.

No model answers, invented human labels, semantic group inference or training.
Human authorship and independent review are declarations, not authentication.
"""
import argparse
from copy import deepcopy
import hashlib
from pathlib import Path
import re

from cryptoforge import semantic_event_review as events, semantic_asset_registry as assets
from cryptoforge import semantic_source_snapshot as snapshots, semantic_source_collector as collector
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp


MAX_PACKAGE_BYTES = 8_000_000
MAX_RESPONSE_BYTES = 1_000_000
PARTITIONS = ('calibration', 'annotation_holdout')


def _implementation():
    return {'source_review_package': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'source_event_protocol': events._implementation()}


def _rubric(packet):
    return {name: {key: deepcopy(question[key]) for key in ('type', 'instructions', 'criteria')}
            for name, question in packet['catalog']['questions'].items()}


def _task_id(packet):
    # Code-side confidence changes must not multiply the sampling units.
    return digest({'state_sha256': packet['model_state_sha256'], 'rubric': _rubric(packet)})


def make_package(entries, *, seed, sample_groups, holdout_groups, frame_kind):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('explicit 32-bit sampling seed required')
    if frame_kind not in ('engineering_examples', 'declared_population'):
        raise ValueError('explicit sampling frame origin required')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise ValueError('one to 64 source review entries required')
    if len(canonical(entries).encode()) > MAX_PACKAGE_BYTES:
        raise ValueError('bounded review evidence required; no truncation')
    normalized, seen = [], set()
    for entry in entries:
        exact_fields(entry, {'snapshot', 'registry_bundle', 'packet', 'declared_event_group'})
        events.validate_packet(entry['packet'], entry['snapshot'], entry['registry_bundle'])
        cluster = entry['declared_event_group']
        if cluster is not None:
            snapshots._text(cluster, 120, identifier=True)
        task_id = _task_id(entry['packet'])
        if task_id in seen:
            raise ValueError('duplicate source task including confidence-only variants')
        seen.add(task_id); normalized.append((task_id, deepcopy(entry)))
    normalized.sort(key=lambda item: item[0])
    # Connected components: exact text, capture, URL, source document/revisions and
    # explicit caller links can merge groups, never force related tasks apart.
    parent = {task_id: task_id for task_id, _ in normalized}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]; key = parent[key]
        return key

    tokens = {}
    for task_id, entry in normalized:
        state = entry['packet']['model_state']; source = state['source']
        keys = [('content', source['content_sha256'])]
        keys += [('document', value) for value in source['document_ids']]
        keys += [('url', value['source_url']) for value in state['source_context']]
        observations = set(source['observation_ids'])
        keys += [('capture', row['capture_sha256']) for row in entry['snapshot']['observations']
                 if row['observation_id'] in observations]
        if entry['declared_event_group'] is not None:
            keys.append(('declared_event', entry['declared_event_group']))
        for key in keys:
            if key in tokens:
                left, right = find(task_id), find(tokens[key])
                parent[max(left, right)] = min(left, right)
            tokens[key] = task_id
    groups = {}
    for task_id, _ in normalized:
        groups.setdefault(find(task_id), []).append(task_id)
    membership = {}
    for members in groups.values():
        group_id = digest({'source_review_task_ids': sorted(members)})
        membership.update({task_id: group_id for task_id in members})
    group_ids = sorted(set(membership.values()), key=lambda key: digest({'seed': seed, 'group_id': key}))
    if type(sample_groups) is not int or not 1 <= sample_groups <= len(group_ids):
        raise ValueError('explicit sample group count within frozen frame required')
    if type(holdout_groups) is not int or not 0 <= holdout_groups < sample_groups:
        raise ValueError('holdout must leave at least one calibration group; zero is an explicit pilot')
    sampled, held = set(group_ids[:sample_groups]), set(group_ids[:holdout_groups])
    tasks = [{'task_id': task_id, 'entry_index': index, 'group_id': membership[task_id],
        'packet_sha256': entry['packet']['packet_sha256'],
        'state_sha256': entry['packet']['model_state_sha256'], 'rubric_sha256': digest(_rubric(entry['packet']))}
        for index, (task_id, entry) in enumerate(normalized)]
    partitions = {name: [row['task_id'] for row in tasks if row['group_id'] in sampled
        and (row['group_id'] in held) == is_held]
        for name, is_held in (('calibration', False), ('annotation_holdout', True))}
    core = {'schema_version': 'source-review-package-v1',
        'parameters': {'seed': seed, 'sample_groups': sample_groups, 'holdout_groups': holdout_groups,
                       'frame_kind': frame_kind},
        'entries': [entry for _, entry in normalized], 'tasks': tasks, 'partitions': partitions,
        'frame_group_count': len(group_ids), 'sampled_group_count': sample_groups,
        'sampled_task_count': sum(len(value) for value in partitions.values()),
        'sampling_policy': 'sha256_seed_rank_without_replacement_over_connected_groups_v1',
        'grouping_policy': 'exact_content_capture_url_document_or_declared_link_connected_components_v1',
        'minimum_split_group_count_met': sample_groups >= 2 and holdout_groups >= 1,
        'source_coverage_verified': False, 'sampling_preregistered': False, 'semantic_groups_audited': False,
        'statistical_benchmark_qualified': False, 'contains_model_answers': False, 'human_review_completed': False,
        'implementation': _implementation(), 'api_calls': 0, 'training_executed': False}
    result = {**core, 'package_sha256': digest(core)}
    if len(canonical(result).encode()) > MAX_PACKAGE_BYTES:
        raise ValueError('bounded frozen package required; no truncation')
    return result


def validate_package(package):
    if not isinstance(package, dict) or not isinstance(package.get('parameters'), dict):
        raise ValueError('frozen source review package required')
    exact_fields(package['parameters'], {'seed', 'sample_groups', 'holdout_groups', 'frame_kind'})
    rebuilt = make_package(package.get('entries'), **package['parameters'])
    if canonical(rebuilt) != canonical(package):
        raise ValueError('source package, sample, related group, policy or implementation changed')
    return package


def blind_view(package, *, partition):
    validate_package(package)
    if partition not in PARTITIONS:
        raise ValueError('explicit review partition required')
    selected = set(package['partitions'][partition])
    if not selected:
        raise ValueError('empty partition is not a holdout or a negative example')
    tasks = []
    for row in package['tasks']:
        if row['task_id'] not in selected: continue
        packet = package['entries'][row['entry_index']]['packet']
        tasks.append({'task_id': row['task_id'], 'state_sha256': row['state_sha256'],
            'rubric_sha256': row['rubric_sha256'], 'state': deepcopy(packet['model_state']),
            'questions': _rubric(packet), 'source_origin': packet['source_origin'],
            'registry_origin': packet['registry_origin']})
    core = {'schema_version': 'source-review-blind-view-v1', 'package_sha256': package['package_sha256'],
        'partition': partition, 'tasks': tasks, 'contains_model_answers': False,
        'contains_gold_labels': False, 'reviewer_independence_authenticated': False}
    return {**core, 'view_sha256': digest(core)}


def blank_response(package, *, partition):
    view = blind_view(package, partition=partition)
    return {'schema_version': 'source-review-response-v1', 'package_sha256': package['package_sha256'],
        'view_sha256': view['view_sha256'], 'partition': partition,
        'reviewer_id': None, 'review_kind': None, 'reviewed_at': None,
        'attestation': {'human_authored': False, 'no_model_answers_shown': False,
                        'independent_of_other_reviewers': False},
        'reviews': [{'task_id': task['task_id'], 'state_sha256': task['state_sha256'],
            'rubric_sha256': task['rubric_sha256'], 'decisions': {
                name: {'status': 'pending', 'value': None, 'reason': None} for name in task['questions']}}
            for task in view['tasks']]}


def complete_review(package, response, *, partition):
    view = blind_view(package, partition=partition)
    if len(canonical(response).encode()) > MAX_RESPONSE_BYTES:
        raise ValueError('bounded reviewer response required')
    exact_fields(response, {'schema_version', 'package_sha256', 'view_sha256', 'partition',
        'reviewer_id', 'review_kind', 'reviewed_at', 'attestation', 'reviews'})
    if (response['schema_version'] != 'source-review-response-v1'
            or response['package_sha256'] != package['package_sha256']
            or response['view_sha256'] != view['view_sha256'] or response['partition'] != partition):
        raise ValueError('review must match this frozen package, view and partition')
    if not isinstance(response['reviewer_id'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', response['reviewer_id']):
        raise ValueError('opaque bounded reviewer identity required')
    timestamp(response['reviewed_at'])
    kind = response['review_kind']
    if kind not in ('human_review', 'synthetic_fixture'):
        raise ValueError('explicit human declaration or synthetic fixture required')
    attestation = response['attestation']
    exact_fields(attestation, {'human_authored', 'no_model_answers_shown', 'independent_of_other_reviewers'})
    if (any(type(value) is not bool for value in attestation.values())
            or (kind == 'human_review' and not all(attestation.values()))
            or (kind == 'synthetic_fixture' and any(attestation.values()))):
        raise ValueError('human declarations required; synthetic fixture cannot assert human authorship')
    tasks = {task['task_id']: task for task in view['tasks']}
    reviews = response['reviews']
    if not isinstance(reviews, list) or len(reviews) != len(tasks):
        raise ValueError('complete partition review coverage required')
    seen, clean = set(), []
    for row in reviews:
        exact_fields(row, {'task_id', 'state_sha256', 'rubric_sha256', 'decisions'})
        key = row['task_id']
        if not isinstance(key, str) or key not in tasks or key in seen:
            raise ValueError('unknown or repeated source review task')
        seen.add(key); task = tasks[key]
        if row['state_sha256'] != task['state_sha256'] or row['rubric_sha256'] != task['rubric_sha256']:
            raise ValueError('reviewed state or rubric changed')
        exact_fields(row['decisions'], set(task['questions']))
        for name, decision in row['decisions'].items():
            exact_fields(decision, {'status', 'value', 'reason'})
            snapshots._text(decision['reason'], 2000)
            if decision['status'] == 'insufficient':
                if decision['value'] is not None:
                    raise ValueError('insufficient evidence must have a null value')
            elif decision['status'] == 'answered':
                if not isinstance(decision['value'], str) or decision['value'] not in task['questions'][name]['criteria']:
                    raise ValueError('review choice must exist in this task criteria')
            else:
                raise ValueError('pending decisions cannot become reviewed labels')
        clean.append(deepcopy(row))
    core = {'schema_version': 'source-completed-review-v1', 'package_sha256': package['package_sha256'],
        'view_sha256': view['view_sha256'], 'partition': partition, 'response_sha256': digest(response),
        'reviewer_id': response['reviewer_id'], 'review_kind': kind, 'reviewed_at': response['reviewed_at'],
        'attestation': deepcopy(attestation), 'reviews': sorted(clean, key=lambda row: row['task_id']),
        'authorship_assurance': 'reviewer_declaration_only_not_authenticated',
        'human_gold_verified': False, 'semantic_groups_audited': False, 'training_labels_created': False,
        'historical_feature_availability_verified': False, 'api_calls': 0}
    return {**core, 'completed_review_sha256': digest(core)}


def compare_reviews(package, response_a, response_b, *, partition):
    left = complete_review(package, response_a, partition=partition)
    right = complete_review(package, response_b, partition=partition)
    if left['reviewer_id'] == right['reviewer_id'] or left['review_kind'] != right['review_kind']:
        raise ValueError('two distinct declared reviewers of the same origin required')
    rows_b = {row['task_id']: row for row in right['reviews']}
    outcomes, metrics = [], {}
    for row in left['reviews']:
        decisions = {}
        for name, a in row['decisions'].items():
            b = rows_b[row['task_id']]['decisions'][name]
            both = a['status'] == b['status'] == 'answered'
            agreed = both and a['value'] == b['value']
            insufficient = a['status'] == b['status'] == 'insufficient'
            status = 'agreed' if agreed else 'joint_insufficient' if insufficient else 'disputed'
            decisions[name] = {'status': status, 'value': a['value'] if agreed else None,
                               'left': deepcopy(a), 'right': deepcopy(b)}
            metric = metrics.setdefault(name, {'both_answered_count': 0, 'agreed_answer_count': 0,
                'joint_insufficient_count': 0, 'disputed_count': 0})
            metric['both_answered_count'] += both; metric['agreed_answer_count'] += agreed
            metric['joint_insufficient_count'] += insufficient; metric['disputed_count'] += status == 'disputed'
        outcomes.append({'task_id': row['task_id'], 'decisions': decisions})
    for metric in metrics.values():
        count = metric['both_answered_count']
        metric['agreement_on_answered'] = metric['agreed_answer_count'] / count if count else None
    core = {'schema_version': 'source-review-comparison-v1', 'package_sha256': package['package_sha256'],
        'partition': partition, 'review_kind': left['review_kind'],
        'reviewer_ids': [left['reviewer_id'], right['reviewer_id']],
        'completed_review_sha256': [left['completed_review_sha256'], right['completed_review_sha256']],
        'task_count': len(outcomes), 'questions': metrics, 'outcomes': outcomes,
        'reviewer_independence_authenticated': False, 'disagreements_adjudicated': False,
        'human_gold_verified': False, 'semantic_groups_audited': False, 'statistical_benchmark_qualified': False,
        'model_quality_evaluated': False, 'training_labels_created': False, 'api_calls': 0}
    return {**core, 'comparison_sha256': digest(core)}


def _bundle(directory, files):
    directory = Path(directory); directory.mkdir(mode=0o700)
    for name, value in files.items(): collector._write(directory, name, value)
    collector._sync(directory); collector._sync(directory.parent)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--manifest', type=Path, required=True)
    prepare.add_argument('--seed', type=int, required=True)
    prepare.add_argument('--sample-groups', type=int, required=True)
    prepare.add_argument('--holdout-groups', type=int, required=True)
    prepare.add_argument('--frame-kind', choices=('engineering_examples', 'declared_population'), required=True)
    forms = commands.add_parser('forms')
    complete = commands.add_parser('complete'); complete.add_argument('--response', type=Path, required=True)
    compare = commands.add_parser('compare')
    compare.add_argument('--response-a', type=Path, required=True); compare.add_argument('--response-b', type=Path, required=True)
    for sub in (forms, complete, compare):
        sub.add_argument('--package', type=Path, required=True)
        sub.add_argument('--partition', choices=PARTITIONS, required=True)
    for sub in (prepare, forms): sub.add_argument('--directory', type=Path, required=True)
    for sub in (complete, compare): sub.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        manifest = snapshots._read(args.manifest, 128000)
        if not isinstance(manifest, list) or not 1 <= len(manifest) <= 64:
            raise ValueError('one to 64 manifest entries required')
        entries, total = [], 0
        for row in manifest:
            exact_fields(row, {'snapshot', 'registry', 'packet', 'declared_event_group'})
            paths = {key: (args.manifest.parent / row[key]).resolve() for key in ('snapshot', 'registry', 'packet')}
            files = [paths['snapshot'], paths['packet'], paths['registry']/'registry.json', paths['registry']/'registration.json']
            total += sum(path.stat().st_size for path in files)
            if total > MAX_PACKAGE_BYTES: raise ValueError('bounded total review input required')
            entries.append({'snapshot': snapshots._read(paths['snapshot'], snapshots.MAX_SNAPSHOT_BYTES),
                'registry_bundle': assets.read_registry(paths['registry']),
                'packet': snapshots._read(paths['packet'], events.MAX_PACKET_BYTES),
                'declared_event_group': row['declared_event_group']})
        package = make_package(entries, seed=args.seed, sample_groups=args.sample_groups,
            holdout_groups=args.holdout_groups, frame_kind=args.frame_kind)
        _bundle(args.directory, {'package.json': package})
    else:
        package = snapshots._read(args.package, MAX_PACKAGE_BYTES)
        if args.command == 'forms':
            _bundle(args.directory, {'blind-view.json': blind_view(package, partition=args.partition),
                'response-a.json': blank_response(package, partition=args.partition),
                'response-b.json': blank_response(package, partition=args.partition)})
        else:
            if args.command == 'complete':
                result = complete_review(package, snapshots._read(args.response, MAX_RESPONSE_BYTES), partition=args.partition)
            else:
                result = compare_reviews(package, snapshots._read(args.response_a, MAX_RESPONSE_BYTES),
                    snapshots._read(args.response_b, MAX_RESPONSE_BYTES), partition=args.partition)
            collector._write(args.output.parent, args.output.name, result)
    print('Offline source review artifact saved; no model answers, authenticated gold or training')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
