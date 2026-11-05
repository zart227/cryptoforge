"""Prospective common admission budget for explicitly coordinated research.

Trusted Python handlers supply operations; user text never selects executable
code. Inner proposer, semantic and fit ledgers retain their original limits.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import time

from cryptoforge.research_resource_budget import (DEFAULT_RESOURCES, RESOURCE_TABLES, ZERO_TOKENS,
    validate_resources, ensure_resources, reserve_resources, finish_resources, measurement,
    resource_snapshot, read_measurement, allocation)

from cryptoforge import research_code_budget as code_budget
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields
from cryptoforge.research_semantic_budget import (EXTENSION_TABLE, validate_semantic_policy,
    extension_configuration, check_extension, create_extension, table_digest, check_legacy_actions)


DEFAULT_POLICY = {'schema_version': 'coordinated-research-budget-v1', 'daily_actions': 12, 'total_actions': 24,
    'maximum_by_kind': {'proposal': 5, 'semantic_fixture': 10, 'fit': 12}, 'semantic_questions': 80, 'free_only': True}
ZERO_USAGE = {'remote_completions': 0, 'local_llm_completions': 0, 'fixture_workers': 0, 'numeric_fits': 0}


def _source_sha():
    return digest({name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                   for name in code_budget.SOURCE_NAMES})


_LOADED_SHA = _source_sha()


class BudgetCancelled(RuntimeError):
    pass


class BudgetTimedOut(RuntimeError):
    pass


def validate_policy(policy):
    exact_fields(policy, set(DEFAULT_POLICY))
    exact_fields(policy['maximum_by_kind'], set(DEFAULT_POLICY['maximum_by_kind']))
    if policy['schema_version'] != DEFAULT_POLICY['schema_version'] or policy['free_only'] is not True:
        raise ValueError('free-only coordinated budget required')
    for value, lo, hi in [(policy['daily_actions'], 1, 1000), (policy['total_actions'], 1, 10000),
                          (policy['semantic_questions'], 0, 16000),
                          *((v, 0, 1000) for v in policy['maximum_by_kind'].values())]:
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError('bounded integer research limits required')
    return {**policy, 'maximum_by_kind': dict(policy['maximum_by_kind'])}


def validate_usage(usage, kind):
    exact_fields(usage, set(ZERO_USAGE))
    if any(type(v) is not int or v not in (0, 1) for v in usage.values()):
        raise ValueError('bounded observed operation counts required')
    allowed = {'proposal': {'remote_completions', 'local_llm_completions'},
               'semantic_fixture': {'fixture_workers'}, 'semantic_live': {'local_llm_completions'}, 'fit': {'numeric_fits'}, 'code_check': set()}[kind]
    if any(v and name not in allowed for name, v in usage.items()) or sum(usage.values()) > 1:
        raise ValueError('observed operation differs from reserved kind')


class ResearchRunBudget:
    def __init__(self, path, bindings, *, policy=None, resource_policy=None, clock=None, timer=None,
                 semantic_live_ledger=None, semantic_live_policy=None, code_check_policy=None):
        self.path = Path(path).resolve()
        exact_fields(bindings, {'proposal', 'semantic_fixture', 'fit'})
        resolved = {kind: str(Path(value).resolve()) for kind, value in bindings.items()}
        if len(set(resolved.values()) | {str(self.path.resolve())}) != 4:
            raise ValueError('four separate research journals required')
        self.policy = validate_policy(DEFAULT_POLICY if policy is None else policy)
        self.resource_policy = validate_resources(DEFAULT_RESOURCES if resource_policy is None else resource_policy)
        self.timer = timer or time.monotonic_ns
        self.manifest = {'schema_version': 'coordinated-research-bindings-v1', 'policy': self.policy,
                         'journal_path_hashes': {kind: digest(value) for kind, value in resolved.items()}}
        if (semantic_live_ledger is None) != (semantic_live_policy is None):
            raise ValueError('semantic-live policy and ledger must be explicit together')
        self.semantic_policy = None
        self.semantic_configuration = None
        if semantic_live_ledger is not None:
            if str(Path(semantic_live_ledger).resolve()) in set(resolved.values()) | {str(self.path)}:
                raise ValueError('five separate research journals required')
            self.semantic_policy = validate_semantic_policy(semantic_live_policy)
            self.semantic_configuration = extension_configuration(self.semantic_policy, semantic_live_ledger,
                self.manifest, self.resource_policy)
        self.code_policy = code_budget.validate_policy(code_check_policy) if code_check_policy is not None else None
        self.code_configuration = (code_budget.configuration(self.code_policy, self.manifest, self.resource_policy,
            self.semantic_configuration) if self.code_policy is not None else None)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _check_objects(self, db, *, allow_empty=False):
        objects = set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
        base = {('table', 'coordinated_policy'), ('table', 'coordinated_actions')}
        resources = {('table', name) for name in RESOURCE_TABLES}
        if objects not in ((set(), base, base | resources, base | resources | {('table', EXTENSION_TABLE)},
            base | resources | {('table', EXTENSION_TABLE), ('table', code_budget.CODE_TABLE)})
                           if allow_empty else (base, base | resources, base | resources | {('table', EXTENSION_TABLE)},
            base | resources | {('table', EXTENSION_TABLE), ('table', code_budget.CODE_TABLE)})):
            raise ValueError('coordinator requires a separate database with complete accounting')
        return {name for _, name in objects}

    def _check_extension(self, db, tables):
        result = check_extension(db, self.semantic_configuration, present=EXTENSION_TABLE in tables)
        if self.code_configuration is not None:
            current = code_budget.configuration(self.code_policy, self.manifest, self.resource_policy,
                self.semantic_configuration)
            if canonical(current) != canonical(self.code_configuration):
                raise ValueError('code configuration changed; restart required')
        code_budget.check_extension(db, self.code_configuration, present=code_budget.CODE_TABLE in tables)
        return result

    def migrate_semantic_budget(self):
        """Explicit, atomic extension of an existing inactive common journal."""
        if self.semantic_configuration is None:
            raise ValueError('explicit semantic-live policy and ledger required')
        if not self.path.is_file():
            raise ValueError('existing common research journal required for migration')
        if _source_sha() != _LOADED_SHA:
            raise ValueError('common budget source changed; restart required')
        db = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=5)
        try:
            db.execute('BEGIN IMMEDIATE')
            tables = self._check_objects(db)
            self._check_manifest(db)
            if EXTENSION_TABLE in tables:
                extension = self._check_extension(db, tables)
                resource_snapshot(db, self.resource_policy, self.semantic_policy, self.code_policy)
                already_migrated = True
            else:
                if db.execute("SELECT count(*) FROM coordinated_actions WHERE status='reserved'").fetchone()[0]:
                    raise ValueError('unfinished common reservations; migration requires inactive resolved history')
                before = {name: table_digest(db, name) for name in tables}
                ensure_resources(db, self.resource_policy, tables)
                check_legacy_actions(db, validate_usage)
                extension = create_extension(db, self.semantic_configuration, self._now().isoformat(),
                    resource_backfilled=not bool(tables & RESOURCE_TABLES))
                if any(table_digest(db, name) != checksum for name, checksum in before.items()):
                    raise ValueError('migration changed existing research history')
                already_migrated = False
            if _source_sha() != _LOADED_SHA:
                raise ValueError('common budget source changed during migration')
            db.commit()
            return {'schema_version': 'coordinated-semantic-migration-result-v2',
                'already_migrated': already_migrated, 'extension': extension,
                'extension_sha256': digest(extension), 'action_reserved': False,
                'live_transport_enabled': False, 'inference_requests': 0}
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def _now(self):
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('aware coordinator clock required')
        return now.astimezone(timezone.utc)

    def _check_manifest(self, db):
        row = db.execute('SELECT payload,sha FROM coordinated_policy WHERE id=1').fetchone()
        if row != (canonical(self.manifest), digest(self.manifest)):
            raise ValueError('persisted coordinator policy or journal bindings changed')

    @contextmanager
    def _transaction(self):
        if self.semantic_configuration is not None and not self.path.is_file():
            raise ValueError('existing common journal and explicit semantic migration required')
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
            tables = self._check_objects(db, allow_empty=True)
            self._check_extension(db, tables)
            db.execute('CREATE TABLE IF NOT EXISTS coordinated_policy (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, sha TEXT)')
            db.execute('''CREATE TABLE IF NOT EXISTS coordinated_actions (key TEXT PRIMARY KEY,
                kind TEXT NOT NULL, input_sha TEXT NOT NULL, utc_day TEXT NOT NULL, questions INTEGER NOT NULL,
                status TEXT NOT NULL, reserved_at TEXT NOT NULL, finished_at TEXT,
                payload TEXT, payload_sha TEXT, observed TEXT, observed_sha TEXT, safe_error TEXT) WITHOUT ROWID''')
            db.execute('INSERT OR IGNORE INTO coordinated_policy VALUES (1,?,?)', (canonical(self.manifest), digest(self.manifest)))
            self._check_manifest(db)
            ensure_resources(db, self.resource_policy, tables, self.semantic_policy, self.code_policy)
            self.path.chmod(0o600)
            db.commit()  # Keep first initialization immutable even if admission fails.
            db.execute('BEGIN IMMEDIATE')
            self._check_manifest(db)
            self._check_extension(db, tables)
            resource_snapshot(db, self.resource_policy, self.semantic_policy, self.code_policy)
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def _finish(self, key, status, measured, envelope=None):
        with self._transaction() as db:
            changed = db.execute('''UPDATE coordinated_actions SET status=?,finished_at=?,payload=?,payload_sha=?,observed=?,observed_sha=?,safe_error=?
                WHERE key=? AND status='reserved' ''', (status, self._now().isoformat(),
                canonical(envelope) if envelope else None, digest(envelope) if envelope else None,
                canonical(envelope['observed']) if envelope else None,
                digest(envelope['observed']) if envelope else None,
                None if envelope else 'coordinated_'+status, key)).rowcount
            if changed != 1:
                raise ValueError('coordinated result is immutable')
            finish_resources(db, key, measured)

    def run(self, kind, identity, operation, *, questions=0, cancel_event=None):
        kinds = {**self.policy['maximum_by_kind'], **({'semantic_live': self.semantic_policy['maximum_actions']} if self.semantic_policy else {}),
                 **({'code_check': self.code_policy['maximum_actions']} if self.code_policy else {})}
        if kind not in kinds:
            raise ValueError('unsupported coordinated research action')
        if type(questions) is not int or (not 1 <= questions <= 16 if kind in ('semantic_fixture', 'semantic_live') else questions != 0):
            raise ValueError('question count differs from reserved action')
        if cancel_event is not None and cancel_event.is_set():
            raise BudgetCancelled('cancelled before common reservation')
        if len(canonical(identity).encode()) > 16000:
            raise ValueError('bounded coordinated identity required')
        identity = strict_json(canonical(identity), max_bytes=16000)
        source_sha = _source_sha()
        if source_sha != _LOADED_SHA:
            raise ValueError('common budget source changed; restart required')
        key_input = {'kind': kind, 'identity': identity, 'questions': questions, 'executor': source_sha}
        if kind == 'semantic_live':
            key_input['semantic_configuration_sha256'] = digest(self.semantic_configuration)
        if kind == 'code_check':
            key_input['code_configuration_sha256'] = digest(self.code_configuration)
        key = digest(key_input)
        now = self._now(); day = now.date().isoformat()
        with self._transaction() as db:
            row = db.execute('SELECT status,payload,payload_sha,input_sha FROM coordinated_actions WHERE key=?', (key,)).fetchone()
            if row:
                if row[0] != 'completed':
                    raise ValueError('prior failed or interrupted coordinated action; no automatic retry')
                envelope = strict_json(row[1], max_bytes=2_000_000)
                if digest(envelope) != row[2] or row[3] != digest(identity):
                    raise ValueError('coordinator cache checksum mismatch')
                exact_fields(envelope, {'result', 'observed', 'tokens'} if isinstance(envelope, dict) and 'tokens' in envelope else {'result', 'observed'})
                validate_usage(envelope['observed'], kind)
                cached = True
            else:
                total, used_questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM coordinated_actions').fetchone()
                daily = db.execute('SELECT count(*) FROM coordinated_actions WHERE utc_day=?', (day,)).fetchone()[0]
                used_kind = db.execute('SELECT count(*) FROM coordinated_actions WHERE kind=?', (kind,)).fetchone()[0]
                if total >= self.policy['total_actions'] or daily >= self.policy['daily_actions']:
                    raise ValueError('common research action budget exhausted')
                if used_kind >= kinds[kind] or used_questions+questions > self.policy['semantic_questions']:
                    raise ValueError('coordinated kind or question budget exhausted')
                reserve_resources(db, self.resource_policy, key, kind, self.semantic_policy, self.code_policy)
                db.execute('INSERT INTO coordinated_actions VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL)',
                           (key, kind, digest(identity), day, questions, 'reserved', now.isoformat()))
                cached = False
        if not cached:
            started = self.timer()
            def observed_resources(value=None):
                return measurement(kind, max(0, (self.timer()-started+999_999)//1_000_000), value)
            try:
                envelope = operation()
                exact_fields(envelope, {'result', 'observed', 'tokens'} if isinstance(envelope, dict) and 'tokens' in envelope else {'result', 'observed'})
                validate_usage(envelope['observed'], kind)
                if len(canonical(envelope).encode()) > 2_000_000:
                    raise ValueError('coordinated result too large')
                envelope = strict_json(canonical(envelope), max_bytes=2_000_000)
                measured = observed_resources(envelope)
                if _source_sha() != source_sha:
                    raise ValueError('common budget source changed during execution')
            except (BudgetCancelled, KeyboardInterrupt):
                self._finish(key, 'cancelled', observed_resources()); raise BudgetCancelled('coordinated action cancelled') from None
            except BudgetTimedOut:
                self._finish(key, 'timed_out', observed_resources()); raise
            except Exception:
                self._finish(key, 'failed', observed_resources())
                raise RuntimeError('coordinated action failed; details not logged') from None
            self._finish(key, 'completed', measured, envelope)
        else:
            with self._transaction() as db:
                measured = read_measurement(db, key)
        return {'schema_version': 'coordinated-research-result-v3' if kind == 'code_check' else ('coordinated-research-result-v2' if kind == 'semantic_live' else 'coordinated-research-result-v1'), 'kind': kind, 'operation_key': key,
                'budget_manifest_sha256': digest(self.manifest), 'coordinator_cached': cached,
                'result': envelope['result'], 'result_sha256': digest(envelope['result']),
                'resource_policy_sha256': digest(self.resource_policy), 'resource_allocation': allocation(self.resource_policy, kind, self.semantic_policy, self.code_policy),
                'semantic_configuration_sha256': digest(self.semantic_configuration) if self.semantic_configuration else None,
                'code_configuration_sha256': digest(self.code_configuration) if self.code_configuration else None,
                'original_resources': measured,
                'invocation_resources': {'origin': 'coordinator_cache', 'handler_wall_ms': 0, 'tokens': dict(ZERO_TOKENS),
                    'token_origin': 'no_new_completion'} if cached else measured,
                'original_observed': dict(envelope['observed']), 'invocation_observed': dict(ZERO_USAGE) if cached else dict(envelope['observed'])}

    def snapshot(self):
        if not self.path.is_file():
            raise ValueError('existing common research journal required')
        db = sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
            tables = self._check_objects(db)
            self._check_manifest(db)
            extension = self._check_extension(db, tables)
            day = self._now().date().isoformat()
            total, questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM coordinated_actions').fetchone()
            daily = db.execute('SELECT count(*) FROM coordinated_actions WHERE utc_day=?', (day,)).fetchone()[0]
            kinds = dict(db.execute('SELECT kind,count(*) FROM coordinated_actions GROUP BY kind'))
            statuses = dict(db.execute('SELECT status,count(*) FROM coordinated_actions GROUP BY status'))
            observed = dict(ZERO_USAGE)
            for kind, raw, checksum in db.execute("SELECT kind,observed,observed_sha FROM coordinated_actions WHERE status='completed'"):
                values = strict_json(raw); validate_usage(values, kind)
                if digest(values) != checksum:
                    raise ValueError('observed work checksum mismatch')
                for name, value in values.items(): observed[name] += value
            return {'schema_version': 'coordinated-research-budget-snapshot-v3' if self.code_configuration else ('coordinated-research-budget-snapshot-v2' if extension else 'coordinated-research-budget-snapshot-v1'), 'utc_day': day,
                'manifest': strict_json(canonical(self.manifest)), 'total_reserved_actions': total, 'daily_reserved_actions': daily,
                'reserved_by_kind': kinds, 'reserved_semantic_questions': questions, 'statuses': statuses,
                'observed_completed_work': observed, 'unknown_work_attempts': total-statuses.get('completed', 0),
                'resources': resource_snapshot(db, self.resource_policy, self.semantic_policy, self.code_policy) if RESOURCE_TABLES <= tables else None,
                'resource_accounting': 'enabled' if RESOURCE_TABLES <= tables else 'legacy_unmeasured_not_initialized',
                'semantic_extension': extension,
                'code_extension': code_budget.check_extension(db, self.code_configuration, present=code_budget.CODE_TABLE in tables),
                'candidate_execution_enabled': False, 'transport_status': 'budget_does_not_infer_transport_readiness',
                'coverage': 'coordinator_entrypoint_only_not_historical_or_account_wide', 'billing_audited': False}
        finally:
            db.close()
