"""Immutable development search ledger with persistent per-family budgets."""
from datetime import UTC,datetime
import hashlib,json,sqlite3


def encoded(value):return json.dumps(value,sort_keys=True,default=str,separators=(',',':'))
def identity(value):return hashlib.sha256(encoded(value).encode()).hexdigest()


def budget_key(candidate,manifest):
    return identity({'parameters':candidate,'execution':manifest.get('base_config',{}),
                     'implementation':manifest.get('implementation_hashes','legacy_unrecorded')})


class ResearchAttempts:
    def __init__(self,path,*,clock=None):
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))

    def _db(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path,timeout=5)
        existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        allowed={'studies','configurations','attempts','budgets','protocol_versions'}
        if existing-allowed:db.close();raise ValueError('research ledger requires an isolated database')
        db.executescript('''
          CREATE TABLE IF NOT EXISTS studies (id TEXT PRIMARY KEY,protocol TEXT,payload TEXT,observed_at TEXT) WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS protocol_versions (version TEXT PRIMARY KEY,id TEXT UNIQUE) WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS budgets (protocol TEXT PRIMARY KEY,maximum INTEGER) WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS configurations (protocol TEXT,family TEXT,id TEXT,payload TEXT,PRIMARY KEY(protocol,family,id)) WITHOUT ROWID;
          CREATE TABLE IF NOT EXISTS attempts (study TEXT,configuration TEXT,status TEXT,payload TEXT,observed_at TEXT,completed_at TEXT,PRIMARY KEY(study,configuration)) WITHOUT ROWID;
        ''');self.path.chmod(0o600);return db

    def register(self,manifest,*,protocol_id,maximum_per_family,protocol_version=None):
        if type(maximum_per_family) is not int or maximum_per_family<1:raise ValueError('positive search budget required')
        candidates=manifest['grid']
        if not candidates or len({identity(c) for c in candidates})!=len(candidates):raise ValueError('nonempty unique configuration grid required')
        observed=self.clock().isoformat();study=identity(manifest);db=self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            if protocol_version is not None:
                prior=db.execute('SELECT id FROM protocol_versions WHERE version=?',(protocol_version,)).fetchone()
                if prior and prior[0]!=protocol_id:raise ValueError('protocol content changed without a new version')
                db.execute('INSERT OR IGNORE INTO protocol_versions VALUES (?,?)',(protocol_version,protocol_id))
            budget=db.execute('SELECT maximum FROM budgets WHERE protocol=?',(protocol_id,)).fetchone()
            if budget and budget[0]!=maximum_per_family:raise ValueError('search budget cannot change without a new protocol')
            db.execute('INSERT OR IGNORE INTO budgets VALUES (?,?)',(protocol_id,maximum_per_family))
            # Budget the effective strategy+execution contract across all studies,
            # not just the signal parameters; old manifests remain evidence.
            contexts=[json.loads(row[0]) for row in db.execute('SELECT payload FROM studies WHERE protocol=?',(protocol_id,))]
            contexts.append(manifest)
            effective={}
            for context in contexts:
                for candidate in context['grid']:
                    effective.setdefault(candidate['family'],set()).add(budget_key(candidate,context))
            if any(len(values)>maximum_per_family for values in effective.values()):
                raise ValueError('persistent family search budget exhausted')
            old=db.execute('SELECT protocol,payload FROM studies WHERE id=?',(study,)).fetchone()
            if old and old!=(protocol_id,encoded(manifest)):raise ValueError('study identity changed')
            for candidate in candidates:
                family=candidate['family'];key=identity(candidate)
                db.execute('INSERT OR IGNORE INTO configurations VALUES (?,?,?,?)',(protocol_id,family,key,encoded(candidate)))
                count=db.execute('SELECT count(*) FROM configurations WHERE protocol=? AND family=?',(protocol_id,family)).fetchone()[0]
                if count>maximum_per_family:raise ValueError('persistent family search budget exhausted')
            db.execute('INSERT OR IGNORE INTO studies VALUES (?,?,?,?)',(study,protocol_id,encoded(manifest),observed))
            for candidate in candidates:
                db.execute('INSERT OR IGNORE INTO attempts VALUES (?,?,?,NULL,?,NULL)',(study,identity(candidate),'reserved',observed))
            db.commit()
        except Exception:db.rollback();raise
        finally:db.close()
        return study

    def result(self,study,candidate):
        db=self._db()
        try:row=db.execute('SELECT status,payload FROM attempts WHERE study=? AND configuration=?',(study,identity(candidate))).fetchone()
        finally:db.close()
        if not row:raise ValueError('unregistered research configuration')
        if row[0]=='failed':raise ValueError('prior failed attempt remains recorded; investigate before a new study')
        return json.loads(row[1]) if row[0]=='completed' else None

    def record(self,study,candidate,payload,*,failed=False):
        status='failed' if failed else 'completed';raw=encoded(payload);db=self._db()
        try:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,payload FROM attempts WHERE study=? AND configuration=?',(study,identity(candidate))).fetchone()
            if not row:raise ValueError('unregistered research configuration')
            if row[0]!='reserved':
                if row!=(status,raw):raise ValueError('recorded research result is immutable')
            else:db.execute('UPDATE attempts SET status=?,payload=?,completed_at=? WHERE study=? AND configuration=?',
                (status,raw,self.clock().isoformat(),study,identity(candidate)))
            db.commit()
        except Exception:db.rollback();raise
        finally:db.close()


    def budget_usage(self,protocol_id):
        db=self._db()
        try:manifests=[json.loads(row[0]) for row in db.execute('SELECT payload FROM studies WHERE protocol=?',(protocol_id,))]
        finally:db.close()
        families={}
        for manifest in manifests:
            for candidate in manifest['grid']:
                families.setdefault(candidate['family'],set()).add(budget_key(candidate,manifest))
        return {family:len(keys) for family,keys in families.items()}
