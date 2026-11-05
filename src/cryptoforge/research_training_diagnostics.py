"""Closed-schema development diagnostics. Never accepts model artifacts or test data.

The caller must export an already approved development partition. These checks
validate the declared boundary; they cannot certify the upstream data lineage.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import re


REPORT_VERSION = 'training-diagnostics-v2'
EXPORT_FIELDS = {'partition', 'dataset_sha256', 'source_sha256', 'development_end', 'rows'}
ROW_FIELDS = {'pair', 'open_time', 'label_end_time', 'probability', 'label'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def exact_fields(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('unexpected or missing fields')


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('finite numeric value outside allowed range')
    return float(value)


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timezone-aware timestamp required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('timezone-aware timestamp required') from None
    if result.tzinfo is None:
        raise ValueError('timezone-aware timestamp required')
    return result.astimezone(timezone.utc)


def build_diagnostics(export, *, threshold=0.5):
    threshold = number(threshold, 0, 1)
    exact_fields(export, EXPORT_FIELDS)
    if export['partition'] not in ('train', 'validation'):
        raise ValueError('only development train/validation partitions allowed')
    for field in ('dataset_sha256', 'source_sha256'):
        if not isinstance(export[field], str) or not re.fullmatch('[a-f0-9]{64}', export[field]):
            raise ValueError('source and dataset SHA256 required')
    boundary = timestamp(export['development_end'])
    rows = export['rows']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100_000:
        raise ValueError('one to 100000 observations required')
    seen, groups, normalized = set(), {}, []
    for row in rows:
        exact_fields(row, ROW_FIELDS)
        pair = row['pair']
        if not isinstance(pair, str) or not re.fullmatch('[A-Z0-9]{1,20}/[A-Z0-9]{2,10}', pair):
            raise ValueError('invalid pair identifier')
        start, end = timestamp(row['open_time']), timestamp(row['label_end_time'])
        if not start < end <= boundary:
            raise ValueError('label crosses development boundary or precedes observation')
        identity = (pair, start)
        if identity in seen:
            raise ValueError('duplicate pair/timestamp')
        seen.add(identity)
        probability = number(row['probability'], 0, 1)
        label = row['label']
        if type(label) is not int or label not in (0, 1):
            raise ValueError('binary integer label required')
        groups.setdefault(pair, []).append((probability, label))
        normalized.append({'pair': pair, 'open_time': start.isoformat(),
                           'label_end_time': end.isoformat(), 'probability': probability, 'label': label})
    normalized.sort(key=lambda r: (r['pair'], r['open_time']))
    observations = [(row['probability'], row['label']) for row in normalized]
    def metrics(values):
        n = len(values)
        selected = [(p, y) for p, y in values if p >= threshold]
        positives = sum(y for _, y in values)
        true_positives = sum(y for _, y in selected)
        bins = [[(p, y) for p, y in values if min(int(p*10), 9) == index] for index in range(10)]
        calibration_error = sum(abs(sum(p for p, _ in group)-sum(y for _, y in group))
                                for group in bins if group) / n
        return {'count': n, 'positive_rate': positives / n,
                'predicted_positive_rate': len(selected)/n,
                'precision': true_positives/len(selected) if selected else None,
                'recall': true_positives/positives if positives else None,
                'calibration_error_10': calibration_error,
                'brier_score': sum((p-y)**2 for p, y in values) / n,
                'log_loss': -sum(y*math.log(max(p, 1e-15)) + (1-y)*math.log(max(1-p, 1e-15))
                                 for p, y in values) / n}
    evidence = {'overall': metrics(observations)}
    evidence.update({f'pair:{pair}': metrics(groups[pair]) for pair in sorted(groups)})
    return {'schema_version': REPORT_VERSION, 'partition': export['partition'], 'decision_threshold': threshold,
            'dataset_sha256': export['dataset_sha256'], 'source_sha256': export['source_sha256'],
            'observations_sha256': digest(normalized), 'development_end': boundary.isoformat(),
            'evidence': evidence}


def validate_diagnostics(report):
    exact_fields(report, {'schema_version', 'partition', 'decision_threshold', 'dataset_sha256', 'source_sha256',
                          'observations_sha256', 'development_end', 'evidence'})
    if report['schema_version'] != REPORT_VERSION or report['partition'] not in ('train', 'validation'):
        raise ValueError('development diagnostics required')
    for field in ('dataset_sha256', 'source_sha256', 'observations_sha256'):
        if not isinstance(report[field], str) or not re.fullmatch('[a-f0-9]{64}', report[field]):
            raise ValueError('diagnostic checksum required')
    number(report['decision_threshold'], 0, 1)
    timestamp(report['development_end'])
    evidence = report['evidence']
    if not isinstance(evidence, dict) or 'overall' not in evidence or len(evidence) > 1001:
        raise ValueError('bounded diagnostic evidence required')
    for key, metrics in evidence.items():
        if key != 'overall' and (not isinstance(key, str) or not re.fullmatch(r'pair:[A-Z0-9]{1,20}/[A-Z0-9]{2,10}', key)):
            raise ValueError('invalid evidence identifier')
        exact_fields(metrics, {'count', 'positive_rate', 'brier_score', 'log_loss',
                               'predicted_positive_rate', 'precision', 'recall', 'calibration_error_10'})
        if type(metrics['count']) is not int or not 1 <= metrics['count'] <= 100_000:
            raise ValueError('invalid diagnostic count')
        number(metrics['positive_rate'], 0, 1)
        number(metrics['brier_score'], 0, 1)
        number(metrics['log_loss'], 0, 36)
        number(metrics['predicted_positive_rate'], 0, 1)
        number(metrics['calibration_error_10'], 0, 1)
        for key in ('precision', 'recall'):
            if metrics[key] is not None:
                number(metrics[key], 0, 1)
        if (metrics['precision'] is None) != (metrics['predicted_positive_rate'] == 0):
            raise ValueError('precision denominator inconsistent')
        if (metrics['recall'] is None) != (metrics['positive_rate'] == 0):
            raise ValueError('recall denominator inconsistent')
    return report
