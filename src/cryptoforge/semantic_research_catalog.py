"""Immutable numerical research records with separate mock semantic annotations."""
import argparse
from contextlib import closing
from pathlib import Path
import re
import sqlite3

from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, validate_diagnostics, number
from cryptoforge.training_experiment_planner import read_json
from cryptoforge.typesafe_judgment_contracts import evaluate_mock, text, validate_catalog


def validate_record(record):
    exact_fields(record, {'schema_version', 'experiment_id', 'artifact_sha256', 'dataset_sha256', 'source_sha256',
        'partition', 'config', 'decision_threshold', 'metrics', 'hypothesis', 'conclusion', 'independent_evidence'})
    if (record['schema_version'] != 'semantic-research-record-v1' or record['partition'] != 'validation'
            or record['independent_evidence'] is not False):
        raise ValueError('development record required')
    for key in ('experiment_id', 'artifact_sha256', 'dataset_sha256', 'source_sha256'):
        if not isinstance(record[key], str) or not re.fullmatch('[a-f0-9]{64}', record[key]):
            raise ValueError('research SHA256 required')
    text(record['hypothesis']); text(record['conclusion'])
    exact_fields(record['config'], {'l2', 'threshold'})
    number(record['config']['l2'], 0, 1)
    number(record['config']['threshold'], 0, 1)
    number(record['decision_threshold'], 0, 1)
    if record['decision_threshold'] != record['config']['threshold']:
        raise ValueError('record threshold differs from recorded configuration')
    exact_fields(record['metrics'], {'count', 'positive_rate', 'predicted_positive_rate', 'precision',
        'recall', 'calibration_error_10', 'brier_score', 'log_loss'})
    if type(record['metrics']['count']) is not int or not 1 <= record['metrics']['count'] <= 100000:
        raise ValueError('bounded evidence count required')
    for key, value in record['metrics'].items():
        if key == 'count' or (key in ('precision', 'recall') and value is None): continue
        number(value, 0, 36 if key == 'log_loss' else 1)
    return record


def record_from_receipt(receipt, *, hypothesis, conclusion):
    if receipt.get('status') != 'completed' or receipt.get('command') != 'run':
        raise ValueError('completed offline experiment receipt required')
    text(hypothesis)
    text(conclusion)
    result = receipt['result']
    artifact = result['artifact']
    if digest(artifact) != result['artifact_sha256'] or artifact.get('production_compatible') is not False:
        raise ValueError('verified offline artifact required')
    report = validate_diagnostics(result['reports']['validation']['diagnostics'])
    if report['partition'] != 'validation' or report['dataset_sha256'] != result['dataset_sha256']:
        raise ValueError('consistent development evidence required')
    exact_fields(artifact['config'], {'l2', 'threshold'})
    number(artifact['config']['l2'], 0, 1)
    number(artifact['config']['threshold'], 0, 1)
    if artifact['config']['threshold'] != report['decision_threshold']:
        raise ValueError('record threshold differs from measured diagnostics')
    study = result['study_id']
    if not isinstance(study, str) or len(study) != 64 or any(c not in 'abcdef0123456789' for c in study):
        raise ValueError('study SHA256 required')
    return validate_record({'schema_version': 'semantic-research-record-v1', 'experiment_id': study,
        'artifact_sha256': result['artifact_sha256'], 'dataset_sha256': report['dataset_sha256'],
        'source_sha256': report['source_sha256'], 'partition': 'validation',
        'config': artifact['config'], 'decision_threshold': report['decision_threshold'],
        'metrics': report['evidence']['overall'], 'hypothesis': hypothesis, 'conclusion': conclusion,
        'independent_evidence': False})


class SemanticResearchCatalog:
    def __init__(self, path):
        self.path = Path(path)

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables-{'semantic_records', 'semantic_annotations'}:
            db.close()
            raise ValueError('semantic catalog requires a separate database')
        self.path.chmod(0o600)
        db.executescript('''
          CREATE TABLE IF NOT EXISTS semantic_records (id TEXT PRIMARY KEY, sha TEXT NOT NULL, payload TEXT NOT NULL) WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS semantic_annotations (id TEXT PRIMARY KEY, record_id TEXT NOT NULL,
              sha TEXT NOT NULL, payload TEXT NOT NULL) WITHOUT ROWID;
        ''')
        return db

    def register(self, receipt, *, hypothesis, conclusion):
        record = record_from_receipt(receipt, hypothesis=hypothesis, conclusion=conclusion)
        with closing(self._db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT sha FROM semantic_records WHERE id=?', (record['experiment_id'],)).fetchone()
            if prior and prior[0] != digest(record):
                raise ValueError('research record is immutable; add a separate annotation')
            db.execute('INSERT OR IGNORE INTO semantic_records VALUES (?,?,?)',
                       (record['experiment_id'], digest(record), canonical(record)))
        return record

    def read_records(self):
        """Bounded, checksum-verified snapshot; never initialize or write a catalog."""
        from cryptoforge.llm_research_contracts import strict_json
        if not self.path.is_file():
            raise ValueError('existing semantic catalog required')
        uri = self.path.resolve().as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri, uri=True, timeout=5)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables != {'semantic_records', 'semantic_annotations'}:
                raise ValueError('separate semantic catalog required')
            rows = db.execute('SELECT id,sha,length(CAST(payload AS BLOB)) FROM semantic_records ORDER BY id LIMIT 1001').fetchall()
            if len(rows) > 1000 or any(type(r[2]) is not int or not 1 <= r[2] <= 64000 for r in rows):
                raise ValueError('bounded research catalog required')
            if sum(r[2] for r in rows) > 8_000_000:
                raise ValueError('research catalog byte limit exceeded')
            records = []
            # Length inspection and payload reads share one read transaction.
            for record_id, checksum, _ in rows:
                payload = db.execute('SELECT payload FROM semantic_records WHERE id=?', (record_id,)).fetchone()
                if not payload:
                    raise ValueError('research catalog changed during read')
                record = validate_record(strict_json(payload[0]))
                if digest(record) != checksum or record['experiment_id'] != record_id:
                    raise ValueError('stored numerical record checksum mismatch')
                records.append(record)
        return records

    def annotate_mock(self, experiment_id, catalog, response):
        validate_catalog(catalog)
        with closing(self._db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT sha,payload FROM semantic_records WHERE id=?', (experiment_id,)).fetchone()
            if not row:
                raise ValueError('registered experiment required')
            from cryptoforge.llm_research_contracts import strict_json
            record = strict_json(row[1])
            if digest(record) != row[0]:
                raise ValueError('stored numerical record checksum mismatch')
            state = {'experiment': record}
            result = evaluate_mock(state, catalog, response)
            key = digest({'state': digest(state), 'catalog': digest(catalog),
                          'model_revision': result['model_revision'], 'origin': result['origin'],
                          'schema_version': result['schema_version'], 'normalizer_sha256': result['normalizer_sha256']})
            prior = db.execute('SELECT sha,payload FROM semantic_annotations WHERE id=?', (key,)).fetchone()
            if prior:
                saved = strict_json(prior[1])
                if digest(saved) != prior[0]:
                    raise ValueError('stored annotation checksum mismatch')
                return {**saved, 'cached': True, 'annotation_id': key}
            db.execute('INSERT INTO semantic_annotations VALUES (?,?,?,?)',
                       (key, experiment_id, digest(result), canonical(result)))
        return {**result, 'cached': False, 'annotation_id': key}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--questions', type=Path, default=Path('config/semantic-research-questions-v1.json'))
    parser.add_argument('--mock-response', type=Path, required=True)
    parser.add_argument('--hypothesis', required=True, help='approved sanitized research description')
    parser.add_argument('--conclusion', required=True, help='claim for annotation, never a numerical override')
    args = parser.parse_args(argv)
    catalog = SemanticResearchCatalog(args.database)
    record = catalog.register(read_json(args.receipt), hypothesis=args.hypothesis, conclusion=args.conclusion)
    result = catalog.annotate_mock(record['experiment_id'], read_json(args.questions), read_json(args.mock_response))
    print(canonical({'experiment_id': record['experiment_id'], 'annotation_id': result['annotation_id'],
                     'origin': result['origin'], 'cached': result['cached'], 'api_calls': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
