"""Observed, immutable selections for future walk-forward windows."""
from dataclasses import asdict
from datetime import UTC,datetime
import hashlib,json,sqlite3

from cryptoforge.live_learning_protocol import time


def fold_payload(fold):
    values=asdict(fold)
    if any(value.tzinfo is None for value in values.values() if isinstance(value,datetime)):
        raise ValueError('aware fold boundaries required')
    return {key:value.astimezone(UTC).isoformat() if isinstance(value,datetime) else value.total_seconds() for key,value in values.items()}


class FoldSelections:
    def __init__(self,path,*,clock=None):
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))

    def freeze(self,protocol_sha,fold,artifact_raw):
        if len(protocol_sha)!=64 or any(c not in '0123456789abcdef' for c in protocol_sha):raise ValueError('protocol SHA256 required')
        fold_data=fold_payload(fold)
        if not fold.train_start<fold.train_end==fold.validation_start<fold.validation_end==fold.test_start<fold.test_end:
            raise ValueError('invalid contiguous fold boundaries')
        artifact=json.loads(artifact_raw)
        key=hashlib.sha256(json.dumps({'protocol':protocol_sha,'fold':fold_data},sort_keys=True).encode()).hexdigest()
        existing=self.get(key)
        sha=hashlib.sha256(artifact_raw).hexdigest()
        if existing:
            if existing['artifact_sha256']!=sha or existing['artifact_payload']!=artifact_raw.decode():
                raise ValueError('fold selection cannot change after observed freeze')
            return existing
        now=self.clock()
        if now.tzinfo is None or not fold.test_start<=now<fold.test_start+fold.embargo:
            raise ValueError('select after validation end and before eligible test starts')
        information_end=time(artifact['config']['fit_information_end'])
        trained=time(artifact['trained_at'])
        if not information_end<=trained<=now or information_end>=fold.test_start-fold.embargo:
            raise ValueError('selection contains unavailable or unpurged information')
        if artifact.get('live_eligible') is not False:raise ValueError('research-only fold selection required')
        payload={'schema_version':'observed-fold-selection-v1','fold_sha256':key,'protocol_sha256':protocol_sha,
                 'artifact_sha256':sha,'artifact_payload':artifact_raw.decode(),'observed_at':now.isoformat(),
                 'fold':fold_data,'live_promotion_allowed':False}
        self.path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path,timeout=5)
        try:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'fold_selections'}:raise ValueError('fold selection needs isolated database')
            db.execute('CREATE TABLE IF NOT EXISTS fold_selections (id TEXT PRIMARY KEY,protocol TEXT,test_start TEXT,test_end TEXT,payload TEXT,UNIQUE(protocol,test_start,test_end)) WITHOUT ROWID')
            with db:db.execute('INSERT INTO fold_selections VALUES (?,?,?,?,?)',
                (key,protocol_sha,fold_data['test_start'],fold_data['test_end'],json.dumps(payload,sort_keys=True)))
            self.path.chmod(0o600)
        except sqlite3.IntegrityError as exc:
            raise ValueError('one selection already frozen for this test interval') from exc
        finally:db.close()
        return payload

    def get(self,key):
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'fold_selections'}:raise ValueError('fold selection needs isolated database')
            row=db.execute('SELECT payload FROM fold_selections WHERE id=?',(key,)).fetchone() if tables else None
        finally:db.close()
        if row is None:return None
        payload=json.loads(row[0])
        recomputed=hashlib.sha256(json.dumps({'protocol':payload['protocol_sha256'],'fold':payload['fold']},sort_keys=True).encode()).hexdigest()
        if recomputed!=key or payload['fold_sha256']!=key or hashlib.sha256(payload['artifact_payload'].encode()).hexdigest()!=payload['artifact_sha256']:
            raise ValueError('corrupt fold selection')
        observed=time(payload['observed_at']);start=time(payload['fold']['test_start'])
        from datetime import timedelta
        if not start<=observed<start+timedelta(seconds=payload['fold']['embargo']):raise ValueError('unobserved prospective fold selection')
        return payload
