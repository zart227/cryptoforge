"""Inner persistent request journal for the fixed local semantic worker."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3

from cryptoforge import local_semantic_worker
from cryptoforge.local_semantic_worker import run_worker, SemanticCancelled, SemanticTimedOut
from cryptoforge.local_semantic_contracts import validate_request, normalize_transport, inference_identity
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, number, timestamp


DEFAULT_POLICY = {'schema_version': 'local-semantic-inner-budget-v1', 'daily_requests': 5, 'total_requests': 5,
    'daily_questions': 80, 'total_questions': 80, 'wall_seconds': 30.0}
TABLES = {'local_semantic_policy', 'local_semantic_requests'}
_LOADED_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def validate_policy(policy):
    exact_fields(policy, set(DEFAULT_POLICY))
    if policy['schema_version'] != DEFAULT_POLICY['schema_version']:
        raise ValueError('supported local semantic inner policy required')
    for name, maximum in (('daily_requests', 1000), ('total_requests', 10000),
                          ('daily_questions', 16000), ('total_questions', 160000)):
        if type(policy[name]) is not int or not 1 <= policy[name] <= maximum:
            raise ValueError('bounded positive local semantic quotas required')
    return {**policy, 'wall_seconds': number(policy['wall_seconds'], 0.001, local_semantic_worker.MAX_WALL_SECONDS)}


class LocalSemanticRequests:
    def __init__(self, path, binding, *, policy=None, clock=None):
        self.path = Path(path).resolve()
        exact_fields(binding, {'common_path_sha256', 'semantic_configuration_sha256'})
        for value in binding.values():
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('common semantic binding hashes required')
        self.policy = validate_policy(DEFAULT_POLICY if policy is None else policy)
        self.manifest = {'schema_version': 'local-semantic-inner-bindings-v1', 'policy': self.policy,
            'journal_path_sha256': digest(str(self.path)), 'common_binding': dict(binding)}
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self):
        now = self.clock()
        if now.tzinfo is None: raise ValueError('aware local semantic clock required')
        return now.astimezone(timezone.utc)

    def _objects(self, db, *, allow_empty=False):
        objects = set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
        expected = {('table', name) for name in TABLES}
        if objects != expected and not (allow_empty and not objects):
            raise ValueError('separate complete local semantic journal required')
        return objects

    def _check_manifest(self, db):
        if db.execute('SELECT payload,sha FROM local_semantic_policy WHERE id=1').fetchone() != (canonical(self.manifest), digest(self.manifest)):
            raise ValueError('persisted local semantic policy or common binding changed')

    @contextmanager
    def _transaction(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try: fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError: pass
        else: os.close(fd)
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('BEGIN IMMEDIATE')
            if not self._objects(db, allow_empty=True):
                db.execute('CREATE TABLE local_semantic_policy (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, sha TEXT NOT NULL)')
                db.execute('''CREATE TABLE local_semantic_requests (key TEXT PRIMARY KEY,
                    request_sha TEXT NOT NULL, utc_day TEXT NOT NULL, questions INTEGER NOT NULL,
                    status TEXT NOT NULL, reserved_at TEXT NOT NULL, finished_at TEXT,
                    payload TEXT, payload_sha TEXT, safe_error TEXT) WITHOUT ROWID''')
                db.execute('INSERT INTO local_semantic_policy VALUES (1,?,?)', (canonical(self.manifest), digest(self.manifest)))
            self._check_manifest(db)
            self.path.chmod(0o600)
            db.commit()  # Refused first admission must still freeze the policy.
            db.execute('BEGIN IMMEDIATE'); self._check_manifest(db)
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def _finish(self, key, status, payload=None):
        with self._transaction() as db:
            finished_at = self._now().isoformat()
            changed = db.execute('''UPDATE local_semantic_requests SET status=?,finished_at=?,payload=?,payload_sha=?,safe_error=?
                WHERE key=? AND status='reserved' ''', (status, finished_at,
                canonical(payload) if payload is not None else None, digest(payload) if payload is not None else None,
                None if status == 'completed' else 'local_semantic_'+status, key)).rowcount
            if changed != 1: raise ValueError('local semantic result is immutable')
        return finished_at

    def _validated_payload(self, request, payload):
        exact_fields(payload, {'transport', 'execution'})
        execution = payload['execution']
        exact_fields(execution, {'wall_seconds', 'cleanup_grace_seconds', 'implementation', 'server_cancellation_verified'})
        number(execution['wall_seconds'], 0.001, self.policy['wall_seconds'])
        if (execution['cleanup_grace_seconds'] != local_semantic_worker.CLEANUP_SECONDS
                or execution['server_cancellation_verified'] is not False):
            raise ValueError('invalid local semantic execution receipt')
        names = set(execution['implementation']) if isinstance(execution['implementation'], dict) else set()
        allowed = [set(local_semantic_worker.SOURCE_NAMES)]
        if request['schema_version'] == 'local-semantic-request-v1':
            allowed.append(set(local_semantic_worker.LEGACY_SOURCE_NAMES))
        if names not in allowed:
            raise ValueError('recognized historical semantic source profile required')
        for checksum in execution['implementation'].values():
            if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
                raise ValueError('historical semantic source hash required')
        return normalize_transport(request, payload['transport'])

    def evaluate(self, request, *, wall_seconds=None, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise SemanticCancelled('local semantic cancelled before reservation')
        validate_request(request)
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != _LOADED_SHA:
            raise ValueError('local semantic journal source changed; restart required')
        if len(canonical(request).encode()) > 180000:
            raise ValueError('bounded local semantic request required')
        wall = number(self.policy['wall_seconds'] if wall_seconds is None else wall_seconds, 0.001, self.policy['wall_seconds'])
        sources = {'journal': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'worker': local_semantic_worker.implementation()}
        key = digest({'inference_identity': inference_identity(request), 'manifest': digest(self.manifest)})
        now = self._now(); day = now.date().isoformat(); questions = len(request['catalog']['questions'])
        with self._transaction() as db:
            prior = db.execute('SELECT status,request_sha,payload,payload_sha,finished_at FROM local_semantic_requests WHERE key=?', (key,)).fetchone()
            if prior:
                if prior[0] != 'completed':
                    raise ValueError('prior failed or interrupted local semantic request; no automatic retry')
                payload = strict_json(prior[2], max_bytes=256000)
                if digest(payload) != prior[3] or prior[1] != payload['transport']['request_sha256']:
                    raise ValueError('local semantic cache checksum mismatch')
                result = self._validated_payload(request, payload); cached = True
                finished_at = prior[4]
            else:
                total, total_q = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM local_semantic_requests').fetchone()
                daily, daily_q = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM local_semantic_requests WHERE utc_day=?', (day,)).fetchone()
                if total >= self.policy['total_requests'] or daily >= self.policy['daily_requests']:
                    raise ValueError('persistent local semantic request quota exhausted')
                if total_q+questions > self.policy['total_questions'] or daily_q+questions > self.policy['daily_questions']:
                    raise ValueError('persistent local semantic question quota exhausted')
                db.execute('INSERT INTO local_semantic_requests VALUES (?,?,?,?,?,?,NULL,NULL,NULL,NULL)',
                    (key, request['request_sha256'], day, questions, 'reserved', now.isoformat()))
                cached = False
        if not cached:
            try:
                transport = run_worker(request, wall_seconds=wall, cancel_event=cancel_event)
                payload = {'transport': transport, 'execution': {'wall_seconds': wall,
                    'cleanup_grace_seconds': local_semantic_worker.CLEANUP_SECONDS,
                    'implementation': sources['worker'], 'server_cancellation_verified': False}}
                if len(canonical(payload).encode()) > 256000:
                    raise ValueError('local semantic payload too large')
                if (hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != sources['journal']
                        or local_semantic_worker.implementation() != sources['worker']):
                    raise ValueError('local semantic implementation changed during execution')
                result = self._validated_payload(request, payload)
            except (SemanticCancelled, KeyboardInterrupt):
                self._finish(key, 'cancelled'); raise SemanticCancelled('local semantic cancelled') from None
            except SemanticTimedOut:
                self._finish(key, 'timed_out'); raise
            except Exception:
                self._finish(key, 'failed')
                raise RuntimeError('local semantic evaluation failed; details not logged') from None
            finished_at = self._finish(key, 'completed', payload)
        extra = {}
        if request['schema_version'] == 'local-semantic-source-request-v2':
            timestamp(finished_at)
            extra['semantic_journal_finished_at'] = finished_at
        return {**result, 'semantic_cached': cached, 'semantic_request_key': key,
            'inner_manifest_sha256': digest(self.manifest), 'local_execution': payload['execution'],
            'invocation_inference_requests': 0 if cached else 1, **extra}

    def snapshot(self):
        if not self.path.is_file(): raise ValueError('existing local semantic journal required')
        db = sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True, timeout=5)
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
            self._objects(db); self._check_manifest(db)
            day = self._now().date().isoformat()
            total, total_q = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM local_semantic_requests').fetchone()
            daily, daily_q = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM local_semantic_requests WHERE utc_day=?', (day,)).fetchone()
            return {'schema_version': 'local-semantic-inner-budget-snapshot-v1', 'manifest': self.manifest,
                'utc_day': day, 'total_requests': total, 'total_questions': total_q,
                'daily_requests': daily, 'daily_questions': daily_q,
                'statuses': dict(db.execute('SELECT status,count(*) FROM local_semantic_requests GROUP BY status')),
                'observed_counts_not_runtime_attestation': True}
        finally:
            db.close()
