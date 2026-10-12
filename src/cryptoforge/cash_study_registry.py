"""Actually observed prospective collection protocols, independent of model fits."""
from datetime import UTC,datetime,timedelta
import hashlib,json,sqlite3
from cryptoforge.live_learning_protocol import time,validate_protocol


class CashStudyRegistry:
    def __init__(self,path,*,clock=None):
        self.path=path;self.clock=clock or (lambda:datetime.now(UTC))

    def by_version(self,version):
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'collection_freezes'}:raise ValueError('isolated collection protocol registry required')
            row=db.execute('SELECT id FROM collection_freezes WHERE version=?',(version,)).fetchone() if tables else None
        finally:db.close()
        return self.get(row[0]) if row else None

    def get(self,sha):
        if not self.path.exists():return None
        db=sqlite3.connect('file:'+str(self.path.resolve())+'?mode=ro',uri=True)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'collection_freezes'}:raise ValueError('isolated collection protocol registry required')
            row=db.execute('SELECT payload FROM collection_freezes WHERE id=?',(sha,)).fetchone() if tables else None
        finally:db.close()
        if row is None:return None
        receipt=json.loads(row[0]);raw=receipt['protocol_payload'].encode()
        if hashlib.sha256(raw).hexdigest()!=sha or receipt['protocol_sha256']!=sha:
            raise ValueError('collection protocol receipt checksum mismatch')
        protocol=json.loads(raw);validate_protocol(protocol)
        if 'initial_snapshot_payload' in receipt and hashlib.sha256(receipt['initial_snapshot_payload'].encode()).hexdigest()!=protocol['development_snapshot_sha256']:
            raise ValueError('initial collection snapshot checksum mismatch')
        observed=time(receipt['observed_at']);frozen=time(protocol['frozen_at'])
        if not timedelta(0)<=observed-frozen<=timedelta(seconds=5):raise ValueError('collection protocol was not prospectively observed')
        return receipt

    def freeze(self,raw,*,initial_snapshot=None):
        sha=hashlib.sha256(raw).hexdigest();old=self.get(sha)
        if old:return old
        protocol=json.loads(raw);validate_protocol(protocol);now=self.clock()
        if now.tzinfo is None or not timedelta(0)<=now-time(protocol['frozen_at'])<=timedelta(seconds=5):
            raise ValueError('collection protocol cannot be frozen retrospectively')
        receipt={'schema_version':'observed-collection-protocol-v1','protocol_sha256':sha,
            'protocol_payload':raw.decode(),'observed_at':now.isoformat(),'live_promotion_allowed':False}
        if initial_snapshot is not None:
            if hashlib.sha256(initial_snapshot).hexdigest()!=protocol['development_snapshot_sha256']:
                raise ValueError('initial collection snapshot differs from protocol')
            receipt['initial_snapshot_payload']=initial_snapshot.decode()
        self.path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path,timeout=5)
        try:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables-{'collection_freezes'}:raise ValueError('isolated collection protocol registry required')
            db.execute('CREATE TABLE IF NOT EXISTS collection_freezes (id TEXT PRIMARY KEY,version TEXT UNIQUE,payload TEXT) WITHOUT ROWID')
            with db:db.execute('INSERT INTO collection_freezes VALUES (?,?,?)',
                (sha,protocol['protocol_version'],json.dumps(receipt,sort_keys=True)))
            self.path.chmod(0o600)
        except sqlite3.IntegrityError as exc:raise ValueError('collection protocol version already frozen') from exc
        finally:db.close()
        return receipt


def require_collection_freeze(study,*,registry_path=None):
    from pathlib import Path
    from cryptoforge.cash_study_paths import LEGACY_PROTOCOL_SHA256
    if study.protocol_sha256==LEGACY_PROTOCOL_SHA256:return 'previously_frozen_legacy_protocol'
    registry=CashStudyRegistry(registry_path or Path('.local/state/cash-study-registry.sqlite'))
    if registry.get(study.protocol_sha256) is None:raise ValueError('collection protocol has no observed prospective freeze')
    return 'observed_prospective_collection_freeze'
