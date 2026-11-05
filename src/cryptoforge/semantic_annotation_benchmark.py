"""Frozen group-wise annotation evaluation, separate from trading qualification.

The current adapter accepts only explicit mock predictions. Synthetic gold labels
verify evaluator arithmetic, never Jev quality. No external inference is performed.
"""
import argparse
import hashlib
import os
from pathlib import Path
import random
import sys

from cryptoforge.training_diagnostics import canonical, digest, exact_fields, number
from cryptoforge.training_experiment_planner import read_json
from cryptoforge.typesafe_judgment_contracts import validate_catalog, normalize_answer


def sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in 'abcdef0123456789' for c in value):
        raise ValueError('SHA256 identity required')


def implementation():
    root = Path(__file__).parent
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in
            ('semantic_annotation_benchmark.py', 'typesafe_judgment_contracts.py')}


def validate_gold(gold, catalog):
    validate_catalog(catalog)
    exact_fields(gold, {'schema_version', 'label_origin', 'examples'})
    if gold['schema_version'] != 'semantic-gold-v1' or gold['label_origin'] not in ('synthetic_fixture', 'human_reviewed'):
        raise ValueError('explicit gold schema and origin required')
    examples = gold['examples']
    if not isinstance(examples, list) or not 2 <= len(examples) <= 1000:
        raise ValueError('two to 1000 labeled research examples required')
    seen, state_groups = set(), {}
    for example in examples:
        exact_fields(example, {'record_id', 'group_id', 'state_sha256', 'labels'})
        for key in ('record_id', 'group_id', 'state_sha256'): sha(example[key])
        if example['record_id'] in seen:
            raise ValueError('duplicate gold record')
        seen.add(example['record_id'])
        prior_group = state_groups.setdefault(example['state_sha256'], example['group_id'])
        if prior_group != example['group_id']:
            raise ValueError('identical states cannot cross groups')
        exact_fields(example['labels'], set(catalog['questions']))
        for name, label in example['labels'].items():
            if label is None:  # Explicit insufficient evidence, not a negative label.
                continue
            question = catalog['questions'][name]
            if question['type'] == 'choice':
                if not isinstance(label, str) or label not in question['criteria']:
                    raise ValueError('gold choice outside criteria')
            elif question['type'] == 'noul':
                if not isinstance(label, str) or label not in ('yes', 'no'):
                    raise ValueError('gold Noul label must be yes/no or null')
            else:
                number(label, 0, len(question['criteria'])-1)
    return sorted(examples, key=lambda e: e['record_id'])


def freeze_benchmark(gold, catalog, *, seed=0, holdout_fraction=0.25):
    examples = validate_gold(gold, catalog)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('32-bit random seed required')
    fraction = number(holdout_fraction, 0.1, 0.5)
    groups = sorted({example['group_id'] for example in examples})
    if len(groups) < 2:
        raise ValueError('at least two independent groups required')
    random.Random(seed).shuffle(groups)
    held = set(groups[:max(1, int(len(groups)*fraction))])
    partitions = {name: [e['record_id'] for e in examples if (e['group_id'] in held) == is_held]
                  for name, is_held in (('calibration', False), ('annotation_holdout', True))}
    return {'schema_version': 'semantic-annotation-benchmark-v1', 'gold': {**gold, 'examples': examples},
        'catalog': catalog, 'gold_sha256': digest({**gold, 'examples': examples}),
        'catalog_sha256': digest(catalog), 'seed': seed, 'holdout_fraction': fraction,
        'partitions': partitions, 'implementation_hashes': implementation(),
        'python_version': list(sys.version_info[:3]), 'contains_predictions': False,
        'grouping_basis': 'caller_supplied_clusters_not_independently_audited'}


def validate_prediction(prediction, example, catalog, sources):
    if not isinstance(prediction, dict):
        raise ValueError('normalized prediction object required')
    if (prediction.get('schema_version') != 'semantic-research-judgments-v2' or
            prediction.get('origin') != 'mock' or prediction.get('api_calls') != 0 or
            prediction.get('calibrated_policy') is not False):
        raise ValueError('only explicitly mock annotations are currently supported')
    if prediction.get('normalizer_sha256') != sources['typesafe_judgment_contracts.py']:
        raise ValueError('prediction normalizer differs from frozen implementation')
    if (prediction.get('state_sha256') != example['state_sha256'] or
            prediction.get('question_catalog_sha256') != digest(catalog) or
            prediction.get('question_snapshot') != catalog or
            prediction.get('policy_version') != catalog['policy_version']):
        raise ValueError('prediction state, questions or policy mismatch')
    answers = prediction['answers']
    exact_fields(answers, set(catalog['questions']))
    for name, answer in answers.items():
        question = catalog['questions'][name]
        if not isinstance(answer, dict):
            raise ValueError('normalized answer object required')
        if answer.get('status') == 'error':
            exact_fields(answer, {'status', 'type', 'error'})
            if answer['type'] != question['type'] or answer['error'] != 'invalid_or_missing_answer':
                raise ValueError('invalid error outcome')
            continue
        if question['type'] == 'noul':
            raw = {'type': 'noul', 'noul': answer.get('probability')}
        else:
            raw = {'type': question['type'], question['type']: answer.get('value'),
                   'confidence': answer.get('confidence'), 'probabilities': answer.get('probabilities')}
        if normalize_answer(question, raw) != answer:
            raise ValueError('normalized answer or uncertainty policy was changed')
    return answers


def validate_plan(plan):
    exact_fields(plan, {'schema_version', 'gold', 'catalog', 'gold_sha256', 'catalog_sha256', 'seed',
        'holdout_fraction', 'partitions', 'implementation_hashes', 'python_version',
        'contains_predictions', 'grouping_basis'})
    expected = freeze_benchmark(plan['gold'], plan['catalog'], seed=plan['seed'], holdout_fraction=plan['holdout_fraction'])
    if canonical(expected) != canonical(plan):
        raise ValueError('frozen benchmark, labels or policy changed')


def public_view(plan, *, partition):
    validate_plan(plan)
    if partition not in ('calibration', 'annotation_holdout'):
        raise ValueError('explicit annotation partition required')
    selected = set(plan['partitions'][partition])
    return {'schema_version': 'semantic-annotation-public-v1', 'benchmark_sha256': digest(plan),
        'partition': partition, 'catalog': plan['catalog'],
        'examples': [{k:v for k,v in e.items() if k != 'labels'} for e in plan['gold']['examples']
                     if e['record_id'] in selected], 'contains_gold_labels': False}


def evaluate_benchmark(plan, predictions, *, partition):
    validate_plan(plan)
    if partition not in ('calibration', 'annotation_holdout'):
        raise ValueError('explicit annotation partition required')
    if not isinstance(predictions, dict):
        raise ValueError('prediction mapping required')
    selected = set(plan['partitions'][partition])
    if set(predictions) != selected:
        raise ValueError('exact prediction coverage of selected partition required')
    examples = {e['record_id']: e for e in plan['gold']['examples'] if e['record_id'] in selected}
    answers = {key: validate_prediction(predictions[key], examples[key], plan['catalog'], plan['implementation_hashes'])
               for key in sorted(selected)}
    metrics = {}
    for name, question in plan['catalog']['questions'].items():
        available = abstained = errors = labeled = correct = accepted_labeled = insufficient = 0
        expected_abstentions = respected_abstentions = available_insufficient = 0
        losses = []
        for key in sorted(selected):
            answer = answers[key][name]
            label = examples[key]['labels'][name]
            available += answer['status'] == 'available'
            abstained += answer['status'] == 'abstain'
            errors += answer['status'] == 'error'
            insufficient += label is None
            expects_abstain = label is None or (question['type'] == 'choice' and label == 'unknown')
            expected_abstentions += expects_abstain
            respected_abstentions += expects_abstain and answer['status'] == 'abstain'
            available_insufficient += label is None and answer['status'] == 'available'
            if label is None:
                continue
            labeled += 1
            if answer['status'] == 'error':
                continue
            if question['type'] == 'noul':
                losses.append((answer['probability']-(label == 'yes'))**2)
                guess = answer['decision']
            elif question['type'] == 'choice':
                losses.append(sum((p-(option == label))**2 for option,p in answer['probabilities'].items()))
                guess = answer['value']
            else:
                losses.append(abs(answer['value']-label))
                guess = None
            if answer['status'] == 'available':
                accepted_labeled += 1
                correct += guess == label if question['type'] != 'score' else 0
        loss_name = {'noul': 'binary_brier', 'choice': 'multiclass_brier_sum', 'score': 'mean_absolute_error'}[question['type']]
        metrics[name] = {'count': len(selected), 'labeled_count': labeled, 'insufficient_gold_count': insufficient,
            'expected_abstention_count': expected_abstentions, 'respected_abstention_count': respected_abstentions,
            'available_on_insufficient_gold_count': available_insufficient,
            'available_count': available, 'abstain_count': abstained, 'error_count': errors,
            'coverage': available/len(selected), 'accepted_labeled_count': accepted_labeled,
            'selective_accuracy': correct/accepted_labeled if accepted_labeled and question['type'] != 'score' else None,
            'loss_name': loss_name, 'scored_count': len(losses), 'mean_loss': sum(losses)/len(losses) if losses else None}
    return {'schema_version': 'semantic-annotation-evaluation-v1', 'benchmark_sha256': digest(plan),
        'partition': partition, 'prediction_sha256': digest(predictions), 'label_origin': plan['gold']['label_origin'],
        'prediction_origin': 'mock', 'questions': metrics,
        'live_model_quality_evaluated': False, 'independent_trading_evidence': False,
        'thresholds_selected': False, 'api_calls': 0}


def write_new(path, payload):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(canonical(payload)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    freeze = sub.add_parser('freeze')
    freeze.add_argument('--gold', type=Path, required=True)
    freeze.add_argument('--questions', type=Path, required=True)
    freeze.add_argument('--output', type=Path, required=True)
    freeze.add_argument('--seed', type=int, default=0)
    score = sub.add_parser('score')
    score.add_argument('--plan', type=Path, required=True)
    score.add_argument('--predictions', type=Path, required=True)
    score.add_argument('--partition', choices=('calibration','annotation_holdout'), required=True)
    score.add_argument('--output', type=Path, required=True)
    public = sub.add_parser('public')
    public.add_argument('--plan', type=Path, required=True)
    public.add_argument('--partition', choices=('calibration','annotation_holdout'), required=True)
    public.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'freeze':
        result = freeze_benchmark(read_json(args.gold), read_json(args.questions), seed=args.seed)
    elif args.command == 'public':
        result = public_view(read_json(args.plan), partition=args.partition)
    else:
        result = evaluate_benchmark(read_json(args.plan), read_json(args.predictions), partition=args.partition)
    write_new(args.output, result)
    print('Annotation benchmark receipt written; no API calls or trading qualification')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
