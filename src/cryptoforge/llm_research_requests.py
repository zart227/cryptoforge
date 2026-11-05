"""Private API request reservations, UTC daily quota and exact-input caching."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from cryptoforge.llm_research_advisor import PROMPT_VERSION, SYSTEM, AdvisorCancelled, AdvisorTimedOut
from cryptoforge.llm_research_contracts import CATALOG, validate_proposal
from cryptoforge.training_diagnostics import canonical, digest, validate_diagnostics


class ResearchRequests:
    def __init__(self, path, *, daily_maximum=5, clock=None):
        if type(daily_maximum) is not int or not 1 <= daily_maximum <= 20:
            raise ValueError('daily API quota must be within 20')
        self.path = Path(path)
        self.daily_maximum = daily_maximum
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        self.path.chmod(0o600)
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {'request_policy', 'advisor_requests'}:
            db.close()
            raise ValueError('API requests require a separate isolated database')
        db.executescript('''
            CREATE TABLE IF NOT EXISTS request_policy (id INTEGER PRIMARY KEY CHECK(id=1), maximum INTEGER);
            CREATE TABLE IF NOT EXISTS advisor_requests (
                key TEXT PRIMARY KEY, utc_day TEXT NOT NULL, status TEXT NOT NULL,
                request TEXT NOT NULL, payload TEXT, payload_sha256 TEXT
            ) WITHOUT ROWID;
        ''')
        return db

    def _inputs(self, advisor, report):
        return {'report': report, 'provider': advisor.provider, 'model': advisor.model,
                  'endpoint_sha256': digest(advisor.ollama_url) if advisor.provider == 'ollama' else None,
                  'parameters': list(advisor.parameters), 'prompt_version': PROMPT_VERSION,
                  'system_sha256': digest(SYSTEM),
                  'catalog': {p: CATALOG[p] for p in advisor.parameters}}

    def _cached(self, prior, key, advisor, report):
        if prior is None:
            return None
        if prior[0] != 'completed':
            raise ValueError('prior failed or interrupted API request; no automatic retry')
        from cryptoforge.llm_research_contracts import strict_json
        result = strict_json(prior[1], max_bytes=512000)
        if digest(result) != prior[2] or result['report_sha256'] != digest(report):
            raise ValueError('cached advice checksum mismatch')
        validate_proposal(result['proposal'], report)
        if result['proposal']['parameter'] not in advisor.parameters:
            raise ValueError('cached parameter unsupported')
        return {**result, 'api_cached': True, 'request_key': key}

    def read_cached(self, advisor, report):
        """Check the established cache without initialization, quota changes or keys."""
        validate_diagnostics(report)
        if not self.path.is_file():
            return None
        inputs = self._inputs(advisor, report); key = digest(inputs)
        db = sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True, timeout=5)
        try:
            db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
            objects = set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
            if objects != {('table','request_policy'), ('table','advisor_requests')}:
                raise ValueError('separate API journal required')
            policy = db.execute('SELECT maximum FROM request_policy WHERE id=1').fetchone()
            if policy and policy[0] != self.daily_maximum:
                raise ValueError('persisted API quota cannot silently change')
            prior = db.execute('SELECT status,payload,payload_sha256 FROM advisor_requests WHERE key=?', (key,)).fetchone()
            if prior and not policy:
                raise ValueError('API cache policy missing')
            return self._cached(prior, key, advisor, report)
        finally:
            db.close()

    def propose(self, advisor, report, *, execute=None, admit=None):
        validate_diagnostics(report)
        preflight = getattr(advisor, 'preflight', None)
        if preflight is not None:
            preflight(report)
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('aware quota clock required')
        day = now.astimezone(timezone.utc).date().isoformat()
        # No credentials, request headers, endpoints or provider error bodies stored.
        inputs = self._inputs(advisor, report); key = digest(inputs)
        db = self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            policy = db.execute('SELECT maximum FROM request_policy WHERE id=1').fetchone()
            if policy and policy[0] != self.daily_maximum:
                raise ValueError('persisted API quota cannot silently change')
            db.execute('INSERT OR IGNORE INTO request_policy VALUES (1,?)', (self.daily_maximum,))
            prior = db.execute('SELECT status,payload,payload_sha256 FROM advisor_requests WHERE key=?', (key,)).fetchone()
            cached = self._cached(prior, key, advisor, report)
            if cached is not None:
                db.commit()
                return cached
            if admit is not None:
                admit()
            used = db.execute('SELECT count(*) FROM advisor_requests WHERE utc_day=?', (day,)).fetchone()[0]
            if used >= self.daily_maximum:
                raise ValueError('persistent daily API quota exhausted')
            db.execute('INSERT INTO advisor_requests VALUES (?,?,?, ?,NULL,NULL)',
                       (key, day, 'reserved', canonical(inputs)))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        try:
            result = advisor.propose(report) if execute is None else execute()
            validate_proposal(result['proposal'], report)
            if result['proposal']['parameter'] not in advisor.parameters:
                raise ValueError('advisor parameter unsupported')
            if result['report_sha256'] != digest(report):
                raise ValueError('advisor returned mismatched report identity')
            payload = canonical(result)
            if len(payload.encode()) > 512000:
                raise ValueError('bounded API cache payload required')
        except (AdvisorCancelled, KeyboardInterrupt):
            with closing(self._db()) as db, db:
                db.execute("UPDATE advisor_requests SET status='cancelled' WHERE key=? AND status='reserved'", (key,))
            raise AdvisorCancelled('provider attempt cancelled') from None
        except AdvisorTimedOut:
            with closing(self._db()) as db, db:
                db.execute("UPDATE advisor_requests SET status='timed_out' WHERE key=? AND status='reserved'", (key,))
            raise
        except Exception:
            with closing(self._db()) as db, db:
                db.execute("UPDATE advisor_requests SET status='failed' WHERE key=?", (key,))
            raise
        with closing(self._db()) as db, db:
            db.execute("UPDATE advisor_requests SET status='completed',payload=?,payload_sha256=? WHERE key=?",
                       (payload, digest(result), key))
        return {**result, 'api_cached': False, 'request_key': key}
