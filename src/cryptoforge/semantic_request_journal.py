"""Persistent quotas and bounded workers for offline semantic SDK fixtures.

This is not a live transport or a sandbox for generated code. Reservations cover
local fixture evaluations only; existing proposer/fit budgets remain separate.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.semantic_annotation_benchmark import validate_prediction
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, number
from cryptoforge.training_experiment_planner import read_json
from cryptoforge.typesafe_sdk_bridge import prepare_request, evaluate_fixture


DEFAULT_POLICY = {'schema_version': 'semantic-fixture-budget-v1', 'daily_requests': 20, 'total_requests': 100,
                  'daily_questions': 160, 'total_questions': 1000, 'wall_seconds': 15.0}
_LOADED_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class RequestCancelled(RuntimeError):
    pass


class RequestTimedOut(RuntimeError):
    pass


def validate_policy(policy):
    exact_fields(policy, set(DEFAULT_POLICY))
    if policy['schema_version'] != DEFAULT_POLICY['schema_version']:
        raise ValueError('unsupported semantic budget policy')
    for name, maximum in (('daily_requests', 1000), ('total_requests', 10000),
                          ('daily_questions', 16000), ('total_questions', 160000)):
        if type(policy[name]) is not int or not 1 <= policy[name] <= maximum:
            raise ValueError('bounded positive semantic quotas required')
    return {**policy, 'wall_seconds': number(policy['wall_seconds'], 0.01, 30)}


def validate_result(result, request, fixture):
    if (not isinstance(result, dict) or result.get('schema_version') != 'semantic-sdk-fixture-result-v1'
            or result.get('origin') != 'offline_sdk_fixture' or result.get('api_calls') != 0
            or result.get('request_sha256') != request['request_sha256']
            or result.get('source_fixture_sha256') != digest(fixture)
            or result.get('reported_model') != request['requested_model']
            or result.get('model_identity_assurance') != 'fixture_declaration_only'
            or any(result.get(name) is not False for name in ('live_access_verified', 'usage_is_external_observation',
                    'inference_cost_evaluated', 'live_model_quality_evaluated', 'independent_trading_evidence'))):
        raise ValueError('verified offline fixture result required')
    validate_prediction(result['normalized_judgments'], {'state_sha256': digest(request['state'])}, request['catalog'],
                        {'typesafe_judgment_contracts.py': request['normalizer_sha256']})


def _stop(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=2)


def run_worker(request, fixture, *, wall_seconds, cancel_event=None):
    body = canonical({'request': request, 'fixture': fixture}).encode()
    if len(body) > 256000:
        raise ValueError('fixture worker input too large')
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
           'PYTHONDONTWRITEBYTECODE': '1'}
    deadline = time.monotonic()+wall_seconds
    process = subprocess.Popen([sys.executable, '-m', 'cryptoforge.semantic_request_journal', '--fixture-worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
        cwd=Path(__file__).resolve().parents[2])
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise RequestCancelled('semantic fixture cancelled')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise RequestTimedOut('semantic fixture wall time exceeded')
            try:
                stdout, _ = process.communicate(input=body, timeout=min(0.1, remaining))
                break
            except subprocess.TimeoutExpired:
                body = None
        if process.returncode or len(stdout) > 512000:
            raise ValueError('fixture worker failed or exceeded output limit')
        envelope = strict_json(stdout.decode(), max_bytes=512000)
        exact_fields(envelope, {'status', 'result'})
        if envelope['status'] != 'completed':
            raise ValueError('fixture worker rejected input')
        return envelope['result']
    except KeyboardInterrupt:
        raise RequestCancelled('semantic fixture interrupted') from None
    finally:
        _stop(process)


class SemanticRequests:
    def __init__(self, path, *, policy=None, clock=None):
        self.path = Path(path)
        self.policy = validate_policy(DEFAULT_POLICY if policy is None else policy)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('aware semantic quota clock required')
        return now.astimezone(timezone.utc)

    def snapshot(self):
        """Read-only usage including every reserved, failed and cancelled attempt."""
        if not self.path.is_file():
            raise ValueError('existing semantic journal required')
        db = sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
            tables = db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')").fetchall()
            if set(tables) != {('table', 'semantic_policy'), ('table', 'semantic_requests')}:
                raise ValueError('separate semantic journal required')
            row = db.execute('SELECT payload,sha FROM semantic_policy WHERE id=1').fetchone()
            if not row or row != (canonical(self.policy), digest(self.policy)):
                raise ValueError('persisted semantic policy mismatch')
            day = self._now().date().isoformat()
            total, total_questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM semantic_requests').fetchone()
            daily, daily_questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM semantic_requests WHERE utc_day=?', (day,)).fetchone()
            states = dict(db.execute('SELECT status,count(*) FROM semantic_requests GROUP BY status'))
            return {'schema_version': 'semantic-fixture-budget-snapshot-v1', 'utc_day': day,
                'budget_policy_sha256': digest(self.policy), 'policy': dict(self.policy),
                'daily_requests': daily, 'total_requests': total, 'daily_questions': daily_questions,
                'total_questions': total_questions, 'statuses': states,
                'origin': 'offline_sdk_fixture', 'api_calls': 0, 'includes_external_proposer_or_fit': False}
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('BEGIN IMMEDIATE')
            objects = db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')").fetchall()
            if any(kind != 'table' or name not in {'semantic_policy', 'semantic_requests'} for kind, name in objects):
                raise ValueError('semantic requests require a separate isolated database')
            db.execute('CREATE TABLE IF NOT EXISTS semantic_policy (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, sha TEXT)')
            db.execute('''CREATE TABLE IF NOT EXISTS semantic_requests (key TEXT PRIMARY KEY,
                request_sha TEXT NOT NULL, fixture_sha TEXT NOT NULL, utc_day TEXT NOT NULL,
                questions INTEGER NOT NULL, status TEXT NOT NULL, reserved_at TEXT NOT NULL,
                finished_at TEXT, payload TEXT, payload_sha TEXT, safe_error TEXT) WITHOUT ROWID''')
            row = db.execute('SELECT payload,sha FROM semantic_policy WHERE id=1').fetchone()
            if row and (row[0] != canonical(self.policy) or row[1] != digest(self.policy)):
                raise ValueError('persisted semantic policy cannot silently change')
            db.execute('INSERT OR IGNORE INTO semantic_policy VALUES (1,?,?)', (canonical(self.policy), digest(self.policy)))
            self.path.chmod(0o600)
            # Freeze initialization even when a subsequent reservation is refused.
            db.commit()
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _finish(self, key, status, *, result=None):
        with self._transaction() as db:
            changed = db.execute('''UPDATE semantic_requests SET status=?,finished_at=?,payload=?,payload_sha=?,safe_error=?
                WHERE key=? AND status='reserved' ''', (status, self._now().isoformat(),
                canonical(result) if result is not None else None, digest(result) if result is not None else None,
                None if status == 'completed' else 'fixture_'+status, key)).rowcount
            if changed != 1:
                raise ValueError('semantic reservation cannot be overwritten')

    def evaluate(self, request, fixture, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise RequestCancelled('cancelled before reservation')
        rebuilt = prepare_request(request['state'], request['catalog'], model=request['requested_model'])
        if canonical(rebuilt) != canonical(request):
            raise ValueError('semantic request changed before reservation')
        if len(canonical(fixture).encode()) > 64000:
            raise ValueError('semantic fixture response too large')
        executor = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        if executor != _LOADED_SHA:
            raise ValueError('semantic executor changed since import; restart required')
        key = digest({'request': request['request_sha256'], 'fixture': digest(fixture), 'executor': executor})
        now = self._now(); day = now.date().isoformat()
        questions = len(request['catalog']['questions'])
        with self._transaction() as db:
            prior = db.execute('SELECT status,payload,payload_sha FROM semantic_requests WHERE key=?', (key,)).fetchone()
            if prior:
                if prior[0] != 'completed':
                    raise ValueError('prior failed, cancelled or interrupted fixture; no automatic retry')
                result = strict_json(prior[1], max_bytes=512000)
                if digest(result) != prior[2]:
                    raise ValueError('cached semantic result checksum mismatch')
                validate_result(result, request, fixture)
                return {**result, 'semantic_cached': True, 'semantic_request_key': key, 'budget_policy_sha256': digest(self.policy)}
            total, total_questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM semantic_requests').fetchone()
            daily, daily_questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM semantic_requests WHERE utc_day=?', (day,)).fetchone()
            if total >= self.policy['total_requests'] or daily >= self.policy['daily_requests']:
                raise ValueError('persistent semantic request quota exhausted')
            if total_questions+questions > self.policy['total_questions'] or daily_questions+questions > self.policy['daily_questions']:
                raise ValueError('persistent semantic question quota exhausted')
            db.execute('INSERT INTO semantic_requests VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,NULL)',
                       (key, request['request_sha256'], digest(fixture), day, questions, 'reserved', now.isoformat()))
        try:
            result = run_worker(request, fixture, wall_seconds=self.policy['wall_seconds'], cancel_event=cancel_event)
            if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != executor:
                raise ValueError('semantic executor changed during evaluation')
            validate_result(result, request, fixture)
        except RequestCancelled:
            self._finish(key, 'cancelled'); raise
        except RequestTimedOut:
            self._finish(key, 'timed_out'); raise
        except Exception:
            self._finish(key, 'failed')
            raise RuntimeError('semantic fixture execution failed; details are not logged') from None
        self._finish(key, 'completed', result=result)
        return {**result, 'semantic_cached': False, 'semantic_request_key': key, 'budget_policy_sha256': digest(self.policy)}


def worker_main():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    os.nice(10)
    try:
        raw = sys.stdin.buffer.read(256001)
        data = strict_json(raw.decode(), max_bytes=256000)
        exact_fields(data, {'request', 'fixture'})
        result = evaluate_fixture(data['request'], data['fixture'])
        sys.stdout.write(canonical({'status': 'completed', 'result': result}))
    except Exception:
        sys.stdout.write(canonical({'status': 'failed', 'result': None}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--response', type=Path, required=True)
    parser.add_argument('--database', type=Path, default=Path('.local/semantic-requests.sqlite'))
    parser.add_argument('--policy', type=Path, help='immutable policy on first initialization')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(canonical({'status': 'started', 'origin': 'offline_sdk_fixture'})+'\n')
        stream.flush(); os.fsync(stream.fileno())
        try:
            journal = SemanticRequests(args.database, policy=read_json(args.policy) if args.policy else None)
            result = journal.evaluate(read_json(args.request), read_json(args.response, 64000))
            receipt, code = {'status': 'completed', 'result': result, 'budget': journal.snapshot()}, 0
        except RequestCancelled:
            receipt, code = {'status': 'cancelled', 'error': 'semantic fixture cancelled'}, 130
        except RequestTimedOut:
            receipt, code = {'status': 'timed_out', 'error': 'semantic fixture timed out'}, 1
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, sqlite3.Error):
            receipt, code = {'status': 'failed', 'error': 'semantic fixture or budget rejected'}, 1
        stream.seek(0); stream.truncate(); stream.write(canonical(receipt)+'\n')
        stream.flush(); os.fsync(stream.fileno())
    print('Semantic fixture receipt saved; no external inference or model changes')
    return code


if __name__ == '__main__':
    raise SystemExit(worker_main() if sys.argv[1:] == ['--fixture-worker'] else main())
