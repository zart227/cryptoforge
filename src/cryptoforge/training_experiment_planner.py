"""Bounded offline long-head experiments over development examples only.

Uses the existing fitting primitives and ResearchAttempts without changing them.
No test split, production registry, network calls, or generated-code execution.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

from cryptoforge import model_training
from cryptoforge.llm_research_contracts import strict_json, validate_proposal
from cryptoforge.research_attempts import ResearchAttempts
from cryptoforge.research_environment import research_environment
from cryptoforge.training_diagnostics import (
    build_diagnostics, canonical, digest, exact_fields, number, timestamp,
)

DATA_VERSION = 'llm-development-examples-v1'
PROTOCOL_VERSION = 'llm-offline-training-protocol-v1'
SOURCE_MODULES = ('model_training.py', 'research_attempts.py', 'training_diagnostics.py',
                  'llm_research_contracts.py', 'training_experiment_planner.py', 'research_environment.py')
BASELINE = {'l2': 0.01, 'threshold': 0.6}


def implementation_hashes():
    root = Path(__file__).parent
    hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_MODULES}
    if globals().get('_LOADED_HASHES', hashes) != hashes:
        raise ValueError('source changed since worker import; restart required')
    return hashes


_LOADED_HASHES = implementation_hashes()


def read_json(path, limit=16_000_000):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('input size limit exceeded')
    return strict_json(raw.decode('utf-8'), max_bytes=limit)


def load_development(path):
    return parse_development(read_json(path))


def parse_development(data):
    exact_fields(data, {'schema_version', 'target_version', 'feature_version', 'feature_names', 'train', 'validation'})
    if (data['schema_version'] != DATA_VERSION or data['target_version'] != 'fixed-future-return-v1'
            or data['feature_version'] != model_training.FEATURE_VERSION
            or data['feature_names'] != list(model_training.FEATURE_NAMES)):
        raise ValueError('supported primary development contract required')
    splits, seen = {}, set()
    for split in ('train', 'validation'):
        rows = data[split]
        if not isinstance(rows, list) or not 2 <= len(rows) <= 10000:
            raise ValueError('two to 10000 examples required per split')
        examples = []
        for row in rows:
            exact_fields(row, {'pair', 'open_time', 'label_end_time', 'features', 'label'})
            if not isinstance(row['pair'], str) or not re.fullmatch('[A-Z0-9]{1,20}/[A-Z0-9]{2,10}', row['pair']):
                raise ValueError('invalid development pair')
            start, end = timestamp(row['open_time']), timestamp(row['label_end_time'])
            if start >= end or (row['pair'], start) in seen:
                raise ValueError('duplicate observation or invalid label boundary')
            seen.add((row['pair'], start))
            features = row['features']
            if not isinstance(features, list) or len(features) != len(model_training.FEATURE_NAMES):
                raise ValueError('compatible feature vector required')
            values = tuple(number(x, -1e6, 1e6) for x in features)
            if type(row['label']) is not int or row['label'] not in (0, 1):
                raise ValueError('binary label required')
            examples.append(model_training.TrainingExample(row['pair'], start, values,
                                                          row['label'], 0, label_end_time=end))
        splits[split] = sorted(examples, key=lambda r: (r.open_time, r.pair))
    if max(row.label_end_time for row in splits['train']) >= min(row.open_time for row in splits['validation']):
        raise ValueError('training labels overlap validation')
    if {row.label for row in splits['train']} != {0, 1}:
        raise ValueError('both training classes required')
    if len({pair for pair, _ in seen}) > 1000:
        raise ValueError('at most 1000 development pairs supported')
    return data, splits


def freeze_protocol(dataset, *, version, maximum=12, epochs=50):
    data, splits = load_development(dataset)
    if not isinstance(version, str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', version):
        raise ValueError('bounded protocol version required')
    if type(maximum) is not int or not 1 <= maximum <= 50:
        raise ValueError('budget must be within 50 attempts')
    if type(epochs) is not int or not 1 <= epochs <= 100:
        raise ValueError('epochs must be within 100')
    return {'schema_version': PROTOCOL_VERSION, 'version': version, 'dataset_sha256': digest(data),
            'implementation_hashes': implementation_hashes(), 'maximum_per_family': maximum,
            'epochs': epochs, 'learning_rate': 0.08, 'baseline': dict(BASELINE),
            'validation_start': min(r.open_time for r in splits['validation']).isoformat(),
            'development_end': max(r.label_end_time for r in splits['validation']).isoformat(),
            'maximum_fit_operations': 3_500_000}


def validate_protocol(protocol, data, splits):
    exact_fields(protocol, {'schema_version', 'version', 'dataset_sha256', 'implementation_hashes',
        'maximum_per_family', 'epochs', 'learning_rate', 'baseline', 'validation_start',
        'development_end', 'maximum_fit_operations'})
    if protocol['schema_version'] != PROTOCOL_VERSION:
        raise ValueError('unsupported training protocol')
    if not isinstance(protocol['version'], str) or not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', protocol['version']):
        raise ValueError('invalid protocol version')
    if protocol['dataset_sha256'] != digest(data) or protocol['implementation_hashes'] != implementation_hashes():
        raise ValueError('frozen data or source identity changed; new protocol required')
    if protocol['baseline'] != BASELINE:
        raise ValueError('unsupported baseline')
    if type(protocol['maximum_per_family']) is not int or not 1 <= protocol['maximum_per_family'] <= 50:
        raise ValueError('invalid persistent budget')
    if type(protocol['epochs']) is not int or not 1 <= protocol['epochs'] <= 100:
        raise ValueError('invalid epoch budget')
    if type(protocol['maximum_fit_operations']) is not int or not 1 <= protocol['maximum_fit_operations'] <= 3_500_000:
        raise ValueError('invalid operation budget')
    number(protocol['learning_rate'], 0.0001, 0.1)
    if (timestamp(protocol['validation_start']) != min(r.open_time for r in splits['validation']) or
            timestamp(protocol['development_end']) != max(r.label_end_time for r in splits['validation'])):
        raise ValueError('frozen development window differs')
    if len(splits['train']) * protocol['epochs'] * len(model_training.FEATURE_NAMES) > protocol['maximum_fit_operations']:
        raise ValueError('fit operation budget exceeded')


@contextmanager
def ledger_lock(path):
    """Single writer/worker per ledger, including across processes. Never wait."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path)+'.worker.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('another offline worker owns this ledger') from None
        yield
    finally:
        os.close(fd)



def save_development_snapshot(ledger_path, data):
    directory = Path(str(ledger_path)+'.inputs')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory/(digest(data)+'.json')
    raw = canonical(data)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if digest(read_json(path)) != digest(data):
            raise ValueError('development snapshot content-address mismatch')
    else:
        with os.fdopen(fd, 'w') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    return {'path': str(path.resolve()), 'sha256': digest(data), 'schema_version': DATA_VERSION}


def evaluate(splits, config, protocol):
    train = splits['train']
    means, stds = model_training.fit_standardizer([row.features for row in train])
    weights, bias = model_training.fit_logistic_head(train, means, stds,
        learning_rate=protocol['learning_rate'], epochs=protocol['epochs'], label_attr='label', l2=config['l2'])
    reports = {}
    for name, rows in splits.items():
        predictions = [{'pair': r.pair, 'open_time': r.open_time.isoformat(),
            'label_end_time': r.label_end_time.isoformat(), 'label': r.label,
            'probability': model_training.predict_probability(r.features, weights, bias, means, stds)} for r in rows]
        report = build_diagnostics({'partition': name, 'dataset_sha256': protocol['dataset_sha256'],
            'source_sha256': digest(protocol['implementation_hashes']),
            'development_end': protocol['development_end'], 'rows': predictions}, threshold=config['threshold'])
        selected = [row for row in predictions if row['probability'] >= config['threshold']]
        reports[name] = {'diagnostics': report, 'selected_observations': len(selected),
            'selected_positive_rate': sum(r['label'] for r in selected)/len(selected) if selected else None}
    artifact = {'schema_version': 'offline-long-head-v1', 'family': model_training.MODEL_FAMILY,
        'target_version': 'fixed-future-return-v1', 'feature_version': model_training.FEATURE_VERSION,
        'feature_names': list(model_training.FEATURE_NAMES), 'weights': weights, 'bias': bias,
        'means': means, 'stds': stds, 'config': config,
        'fit_information_end': protocol['development_end'], 'production_compatible': False}
    return {'artifact': artifact, 'artifact_sha256': digest(artifact), 'reports': reports,
            'environment': research_environment(Path(__file__).resolve().parents[2])}



def execute_fit(data, config, protocol):
    """Fixed numeric worker; resource isolation, not a sandbox for generated code."""
    try:
        completed = subprocess.run([sys.executable, '-m', 'cryptoforge.training_experiment_planner', '--fit-worker'],
            input=canonical({'data': data, 'config': config, 'protocol': protocol}),
            text=True, capture_output=True, timeout=20, check=False,
            env={'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'LANG': 'C.UTF-8', 'PATH': os.defpath})
    except subprocess.TimeoutExpired:
        raise ValueError('offline fit wall-time limit exceeded') from None
    if completed.returncode != 0:
        raise ValueError('offline fit worker failed or exceeded resources')
    result = strict_json(completed.stdout, max_bytes=2_000_000)
    if digest(result['artifact']) != result['artifact_sha256']:
        raise ValueError('worker artifact checksum mismatch')
    return result


def fit_worker():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    os.nice(10)
    payload = strict_json(sys.stdin.read(20_000_001), max_bytes=20_000_000)
    exact_fields(payload, {'data', 'config', 'protocol'})
    data, splits = parse_development(payload['data'])
    validate_protocol(payload['protocol'], data, splits)
    exact_fields(payload['config'], {'l2', 'threshold'})
    from cryptoforge.llm_research_contracts import CATALOG
    for name, value in payload['config'].items():
        number(value, 0, 1)
        if value not in CATALOG[name]:
            raise ValueError('worker configuration outside catalog')
    print(canonical(evaluate(splits, payload['config'], payload['protocol'])))


def run_experiment(dataset, protocol, ledger_path, *, proposal=None, report=None):
    data, splits = load_development(dataset)
    validate_protocol(protocol, data, splits)
    config = dict(protocol['baseline'])
    if proposal is not None:
        validate_proposal(proposal, report)
        if (report['dataset_sha256'] != protocol['dataset_sha256'] or
                report['source_sha256'] != digest(protocol['implementation_hashes']) or
                timestamp(report['development_end']) != timestamp(protocol['development_end'])):
            raise ValueError('proposal report differs from frozen protocol')
        if proposal['parameter'] not in config:
            raise ValueError('candle-history changes require raw candle rebuild; unsupported in this worker')
        config[proposal['parameter']] = float(proposal['value'])
    candidate = {'family': 'llm-offline-long-head-v1', **config}
    manifest = {'schema_version': 'llm-offline-study-v1', 'grid': [candidate],
        'base_config': {'dataset_sha256': protocol['dataset_sha256'], 'protocol_sha256': digest(protocol)},
        'implementation_hashes': protocol['implementation_hashes']}
    ledger_path = Path(ledger_path)
    with ledger_lock(ledger_path):
        ledger = ResearchAttempts(ledger_path)
        if proposal is not None:
            # A hash declaration alone is not evidence: the exact validation
            # report must come from a completed attempt under this protocol.
            if not ledger_path.exists() or report['partition'] != 'validation':
                raise ValueError('registered validation evidence required')
            with sqlite3.connect(ledger_path.resolve().as_uri()+'?mode=ro', uri=True) as db:
                results = db.execute("SELECT a.payload FROM attempts a JOIN studies s ON s.id=a.study "
                    "WHERE s.protocol=? AND a.status='completed'", (digest(protocol),)).fetchall()
            if not any(digest(json.loads(row[0])['reports']['validation']['diagnostics']) == digest(report)
                       for row in results):
                raise ValueError('report is not registered evidence for this protocol')
        snapshot = save_development_snapshot(ledger_path, data)
        study = ledger.register(manifest, protocol_id=digest(protocol),
            maximum_per_family=protocol['maximum_per_family'], protocol_version=protocol['version'])
        prior = ledger.result(study, candidate)
        if prior is not None:
            if digest(prior['artifact']) != prior['artifact_sha256']:
                raise ValueError('cached experiment artifact checksum mismatch')
            return {**prior, 'cached': True, 'study_id': study, 'training_executed': False,
                    'budget_usage': ledger.budget_usage(digest(protocol))}
        # Excludes explanation/LLM identity: changing hypothesis text cannot bypass dedup.
        claim = ledger_path.parent / (ledger_path.name+'.'+study+'.claim')
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError('interrupted reserved attempt; explicit investigation required') from None
        with os.fdopen(fd, 'w') as stream:
            stream.write(canonical({'study_id': study, 'status': 'claimed'})+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        started = time.monotonic()
        try:
            result = execute_fit(data, config, protocol)
            if implementation_hashes() != protocol['implementation_hashes']:
                raise ValueError('source changed during fit')
            result.update({'protocol_sha256': digest(protocol), 'dataset_sha256': digest(data),
                'development_snapshot': snapshot, 'elapsed_seconds': time.monotonic()-started, 'completed_at': datetime.now(timezone.utc).isoformat(),
                'budget_usage': ledger.budget_usage(digest(protocol)), 'training_executed': True})
            ledger.record(study, candidate, result)
        except Exception:
            ledger.record(study, candidate, {'status': 'failed', 'error': 'offline experiment failed'}, failed=True)
            raise
        return {**result, 'cached': False, 'study_id': study}


if __name__ == '__main__':
    if sys.argv[1:] != ['--fit-worker']:
        raise SystemExit('internal numeric worker only')
    try:
        fit_worker()
    except Exception:
        raise SystemExit('offline numeric worker rejected input') from None
