"""Durable delivery of decision records; never replays exchange operations."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager


class DecisionOutbox:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {'decision_outbox'}:
                raise ValueError('isolated decision outbox database required')
            db.execute('CREATE TABLE IF NOT EXISTS decision_outbox '
                '(id TEXT PRIMARY KEY, payload TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, '
                'last_error TEXT)')
        path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, table, rows, options):
        if table != 'trade_decisions' or options.get('on_conflict') != 'idempotency_key':
            raise ValueError('only idempotent trade decision records allowed')
        if not rows or any(not row.get('idempotency_key') for row in rows):
            raise ValueError('decision idempotency keys required')
        raw = json.dumps(dict(table=table, rows=rows, options=options), sort_keys=True, allow_nan=False)
        key = hashlib.sha256(raw.encode()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO decision_outbox(id,payload) VALUES (?,?)', (key, raw))
        return key

    def pending(self):
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM decision_outbox WHERE delivered=0').fetchone()[0]

    def deliver(self, client, key):
        with self.connect() as db:
            row = db.execute('SELECT payload,delivered FROM decision_outbox WHERE id=?', (key,)).fetchone()
        if row is None:
            raise ValueError('unknown decision receipt')
        if row[1]:
            return True
        if hashlib.sha256(row[0].encode()).hexdigest() != key:
            raise ValueError('corrupt decision receipt')
        request = json.loads(row[0])
        try:
            client.upsert(request['table'], request['rows'], **request['options'])
        except Exception as exc:
            with self.connect() as db:
                db.execute('UPDATE decision_outbox SET last_error=? WHERE id=?', (type(exc).__name__, key))
            return False
        with self.connect() as db:
            db.execute('UPDATE decision_outbox SET delivered=1,last_error=NULL WHERE id=?', (key,))
        return True

    def flush(self, client, *, limit=100):
        with self.connect() as db:
            keys = [row[0] for row in db.execute(
                'SELECT id FROM decision_outbox WHERE delivered=0 ORDER BY rowid LIMIT ?', (limit,))]
        delivered = 0
        for key in keys:
            if not self.deliver(client, key):
                break
            delivered += 1
        return delivered


class DurableDecisionClient:
    def __init__(self, client, outbox):
        self.client, self.outbox = client, outbox

    def __getattr__(self, name):
        return getattr(self.client, name)

    def upsert(self, table, rows, **options):
        if table != 'trade_decisions':
            return self.client.upsert(table, rows, **options)
        self.outbox.enqueue(table, rows, options)
        self.outbox.flush(self.client)
