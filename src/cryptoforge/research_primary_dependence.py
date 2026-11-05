"""Descriptive dependence/concentration over saved primary examples; no inferential claims."""
import argparse
from collections import Counter, defaultdict
from datetime import timedelta
from fractions import Fraction
import hashlib
from pathlib import Path

from cryptoforge import research_primary_packet_audit as primary
from cryptoforge.training_diagnostics import canonical, digest, timestamp

POLICY = {'schema_version': 'research-primary-dependence-policy-v1', 'maximum_examples': 10000,
    'maximum_report_bytes': 262144, 'label_window': 'reference_close_to_future_close_half_open',
    'endpoint_touch_counts_as_overlap': False, 'grouping': 'exact_same_input_anchor',
    'statistical_effective_sample_size_estimated': False, 'confidence_intervals_enabled': False,
    'model_prediction_enabled': False, 'training_admission_enabled': False}


def implementation():
    return {'audit': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'primary_packet': primary.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('fixed_descriptive_dependence_required')


def bind(directory):
    _guard(); directory = primary.private._safe_directory(directory, private=True)
    report = primary.verify(directory)
    original = primary.registry.bridge._read(directory, 'binding.json', 262144)
    bound = primary.bind(original['registry'], original['project'])
    if bound[0] != original: raise ValueError('original_primary_packet_binding_required')
    return {'directory': str(directory), 'files': {n: hashlib.sha256(primary.private._private_read(directory, n, 262144)).hexdigest()
        for n in ('policy.json', 'binding.json', 'audit.json')}, 'audit_sha256': report['audit_sha256']}, bound[2], report


def _concentration(counts):
    total = sum(counts); hhi = sum(Fraction(n, total)**2 for n in counts)
    return {'hhi': float(hhi), 'hhi_fraction': [str(hhi.numerator), str(hhi.denominator)],
        'inverse_hhi_group_count': float(1/hhi), 'largest_group_fraction': max(counts)/total,
        'inverse_hhi_is_statistical_effective_sample_size': False}


def summarize(rows):
    if type(rows) is not list or not 1 <= len(rows) <= 10000:
        raise ValueError('bounded_nonempty_dependence_rows_required')
    groups = defaultdict(list); by_pair = defaultdict(list); identities = set()
    for row in rows:
        start = timestamp(row['open_time']); end = timestamp(row['label_end_time'])
        identity = (row['pair'], start)
        if (identity in identities or (end-start).total_seconds() != 1200 or start.second or start.microsecond
                or start.minute % 5 or any(type(row[k]) is not int or row[k] not in (0, 1) for k in ('label', 'short_label'))):
            raise ValueError('fixed_primary_dependence_identity_horizon_required')
        identities.add(identity); groups[start].append(row); by_pair[row['pair']].append(row)
    intervals = []; time_groups = []
    for start, sample in sorted(groups.items()):
        # TrainingExample.open_time is the last input candle's open. Its close is
        # the price-return reference, one candle later, not the horizon's start open.
        beginning = start+timedelta(minutes=5); end = timestamp(sample[0]['label_end_time'])
        if any(timestamp(r['label_end_time']) != end for r in sample): raise ValueError('same_anchor_same_horizon_required')
        intervals.append((beginning, end, len(sample)))
        time_groups.append({'input_anchor': start.isoformat(), 'examples': len(sample),
            'long_positives': sum(r['label'] for r in sample), 'short_positives': sum(r['short_label'] for r in sample)})
    events = []
    for start, end, count in intervals:
        events.extend([(start, 1, count), (end, -1, -count)])
    active_time = active_examples = maximum_time = maximum_examples = 0
    for _, time_delta, example_delta in sorted(events):
        # End(-1) precedes start(+1) at the same time: touching is not overlap.
        active_time += time_delta; active_examples += example_delta
        maximum_time = max(maximum_time, active_time); maximum_examples = max(maximum_examples, active_examples)
    last_end = None; disjoint = 0
    for start, end, _ in sorted(intervals, key=lambda x: x[1]):
        if last_end is None or start >= last_end:
            disjoint += 1; last_end = end
    pairs = {pair: {'count': len(values), 'long_positives': sum(r['label'] for r in values),
        'short_positives': sum(r['short_label'] for r in values)} for pair, values in sorted(by_pair.items())}
    return {'nominal_examples': len(rows), 'unique_input_anchors': len(groups), 'pair_count': len(by_pair),
        'examples_per_anchor_minimum': min(map(len, groups.values())), 'examples_per_anchor_maximum': max(map(len, groups.values())),
        'pair_concentration': _concentration([len(v) for v in by_pair.values()]),
        'time_concentration': _concentration([len(v) for v in groups.values()]),
        'maximum_overlapping_time_label_windows': maximum_time,
        'maximum_overlapping_example_label_windows': maximum_examples,
        'maximum_count_nonoverlapping_time_label_windows': disjoint,
        'nonoverlapping_count_is_independent_sample_size': False,
        'label_return_window_seconds': 900, 'time_group_summary_sha256': digest(time_groups), 'by_pair': pairs}


def compose(binding, snapshot, primary_report):
    _guard()
    if primary_report['audit_sha256'] != binding['audit_sha256']:
        raise ValueError('original_primary_packet_report_required')
    splits = {name: summarize(snapshot['splits'][name]) for name in primary.SPLITS}
    for name, report in splits.items():
        if report['nominal_examples'] != primary_report['splits'][name]['count']:
            raise ValueError('original_primary_split_count_required')
    core = {'schema_version': 'research-primary-dependence-v1', 'status': 'descriptive_groups_verified',
        'binding_sha256': digest(binding), 'primary_audit_sha256': primary_report['audit_sha256'],
        'candidate_artifact_sha256': primary_report['candidate_artifact_sha256'],
        'policy_sha256': digest(POLICY), 'implementation': _LOADED, 'splits': splits,
        'statistical_effective_sample_size_estimated': False, 'independence_verified': False,
        'significance_test_or_bootstrap_performed': False, 'confidence_intervals_computed': False,
        'dependence_or_strategy_profitability_corrected_metrics': None,
        'training_data_admitted': False, 'model_prediction_performed': False, 'fit_performed': False,
        'provider_called': False, 'new_budget_actions': 0, 'production_promotion_authorized': False}
    result = {**core, 'audit_sha256': digest(core)}
    if len(canonical(result).encode()) > 262144: raise ValueError('descriptive_dependence_report_byte_limit')
    return result


def prepare(directory, primary_pack):
    _guard(); directory = Path(directory).absolute(); primary.private._safe_directory(directory.parent)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_dependence_audit_directory_required')
    bound = bind(primary_pack); report = compose(*bound)
    if bind(primary_pack) != bound: raise ValueError('primary_packet_changed_during_dependence_audit')
    directory.mkdir(mode=0o700)
    for n, v in (('policy.json', POLICY), ('binding.json', bound[0]), ('audit.json', report)): primary.files._write(directory, n, v)
    primary.files._sync(directory); return report


def verify(directory):
    _guard(); directory = primary.private._safe_directory(directory, private=True)
    read = lambda n: primary.registry.bridge._read(directory, n, 262144)
    if read('policy.json') != POLICY: raise ValueError('fixed_descriptive_dependence_policy_required')
    saved = read('binding.json'); bound = bind(saved['directory'])
    if saved != bound[0]: raise ValueError('original_dependence_packet_binding_required')
    report = compose(*bound)
    if canonical(report) != canonical(read('audit.json')): raise ValueError('descriptive_dependence_report_changed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify'):
        command = commands.add_parser(name); command.add_argument('--directory', type=Path, required=True)
        if name == 'prepare': command.add_argument('--primary-pack', type=Path, required=True)
    args = parser.parse_args(argv)
    try: report = prepare(args.directory, args.primary_pack) if args.command == 'prepare' else verify(args.directory)
    except Exception:
        print('Descriptive dependence audit refused; model operations disabled'); return 2
    print('Descriptive dependence audit: '+report['status']+'; independence/significance unqualified'); return 0


if __name__ == '__main__':
    raise SystemExit(main())
