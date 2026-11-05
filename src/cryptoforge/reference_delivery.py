"""Bounded single-writer reference history and at-least-once delivery to 3 roles.

Source event identities are retained; an old physical SQLite file is not adopted
under a newer hash. Acknowledgement records a consumer receipt, not a trade.
"""
from contextlib import contextmanager
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from decimal import Context,Decimal,localcontext
from pathlib import Path
from time import monotonic
import fcntl
import os
import shutil
import sqlite3

from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync
from cryptoforge.reference_source_ledger import (
    FLAGS,ReferenceLedger,ReferencePolicy,audit_reference_ledger,file_sha,_file_identity,
    _guard_db,_database as source_database,_environment,_artifact,_sources_ready,_event_time,
    runtime_hashes as source_runtime_hashes,SCHEMA as SOURCE_SCHEMA,
)
from cryptoforge.reference_source_reader import ROLES
from cryptoforge.reference_sources import MANDATORY,source_pairs
from cryptoforge.reference_delivery_source import SourceReplay

SCHEMA='reference-delivery-v1'
SQL={
 'state':'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,head TEXT NOT NULL,source_seq INTEGER NOT NULL,source_head TEXT NOT NULL)',
 'source_events':'CREATE TABLE source_events (seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload BLOB NOT NULL,previous TEXT NOT NULL,sha TEXT NOT NULL)',
 'batches':'CREATE TABLE batches (seq INTEGER PRIMARY KEY,payload BLOB NOT NULL,sha TEXT UNIQUE NOT NULL,event_seq INTEGER NOT NULL)',
 'events':'CREATE TABLE events (seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,payload BLOB NOT NULL,previous TEXT NOT NULL,sha TEXT NOT NULL)',
 'cursors':'CREATE TABLE cursors (role TEXT PRIMARY KEY,cursor INTEGER NOT NULL,pending_seq INTEGER,delivery_id TEXT,offered_at TEXT) WITHOUT ROWID',
 'acks':'CREATE TABLE acks (role TEXT NOT NULL,batch_seq INTEGER NOT NULL,delivery_id TEXT UNIQUE NOT NULL,payload BLOB NOT NULL,event_seq INTEGER NOT NULL,PRIMARY KEY(role,batch_seq)) WITHOUT ROWID',
}
for table in ('source_events','batches','events','acks'):
    for operation in ('UPDATE','DELETE'):
        name=f'{table}_no_{operation.lower()}'
        SQL[name]=f"CREATE TRIGGER {name} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'immutable retained reference'); END"


@dataclass(frozen=True)
class DeliveryPolicy:
    maximum_database_bytes:int=4*1024**3
    maximum_scratch_database_bytes:int=256*1024**2
    maximum_ingest_seconds:int=90
    maximum_events:int=100000
    maximum_source_events:int=100000
    maximum_batches:int=10000
    maximum_source_events_per_batch:int=256
    maximum_source_bytes_per_batch:int=4*1024**2
    maximum_delivery_bytes:int=8*1024**2
    minimum_free_disk_mb:int=2048

    def __post_init__(self):
        if (any(type(v) is not int or v<1 for v in asdict(self).values())
                or not 65536<=self.maximum_database_bytes<=4*1024**3 or self.maximum_database_bytes%4096
                or not 65536<=self.maximum_scratch_database_bytes<=512*1024**2 or self.maximum_scratch_database_bytes%4096
                or self.maximum_ingest_seconds>120
                or self.maximum_events>1000000 or self.maximum_source_events>1000000 or self.maximum_batches>100000
                or not 4<=self.maximum_source_events_per_batch<=1024
                or not 4096<=self.maximum_source_bytes_per_batch<=8*1024**2
                or not 4096<=self.maximum_delivery_bytes<=16*1024**2 or self.minimum_free_disk_mb<2048):
            raise ValueError('bounded reference delivery policy required')


def _paths():
    from cryptoforge.reference_source_ledger import _runtime_paths
    paths=_runtime_paths();here=Path(__file__).parent;root=here.parents[1]
    for name in ('reference_source_reader.py','reference_delivery_source.py','reference_delivery.py'):
        paths[name]=here/name
    for name in ('read_reference_sources.py','deliver_reference_sources.py'):
        paths[name]=root/'scripts'/name
    return paths


def runtime_hashes():
    pins={name:digest(path.read_bytes()) for name,path in _paths().items()}
    if pins!=_LOADED_RUNTIME:raise ValueError('delivery runtime changed; new process/contract required')
    return pins


def _now(clock):return stamp((clock or (lambda:datetime.now(UTC)))())


def _copy(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    _sync(path.parent)


def _disk(path,policy):
    path=Path(path)
    while not path.exists():path=path.parent
    reserve=policy.minimum_free_disk_mb*1024**2+policy.maximum_scratch_database_bytes+3*(policy.maximum_source_bytes_per_batch+policy.maximum_delivery_bytes)
    if shutil.disk_usage(path).free<reserve:raise ValueError('delivery disk reserve preserved')


def _connect(path,policy,*,write=False):
    _guard_db(path,policy)
    db=sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=1)
    try:
        if write:db.execute(f'PRAGMA max_page_count={policy.maximum_database_bytes//4096}')
        else:db.execute('PRAGMA query_only=ON')
        if (db.execute('PRAGMA page_size').fetchone()[0]!=4096 or db.execute('PRAGMA journal_mode').fetchone()[0]!='delete'
                or {n:s for n,s in db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}!=SQL):
            raise ValueError('original reference delivery schema differs')
        for table,limit in [('events',policy.maximum_events),('source_events',policy.maximum_source_events),('batches',policy.maximum_batches),('acks',3*policy.maximum_batches)]:
            if db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]>limit:raise ValueError('delivery row budget exceeded')
        return db
    except BaseException:db.close();raise


def _source_descriptor(value,identity):
    if type(value) is not dict or set(value)!={'root','manifest_sha256','registration_sha256','database_sha256','head_sha256'}:
        raise ValueError('original source descriptor required')
    if any(value[k]!=identity[k] for k in ('root','manifest_sha256','registration_sha256')):
        raise ValueError('delivery cannot substitute its source namespace')
    for name in ('manifest_sha256','registration_sha256','database_sha256','head_sha256'):sha(value[name])


def _delivery_id(manifest_pin,role,batch_seq,batch_sha):
    return digest(canonical(dict(manifest_sha256=manifest_pin,role=role,batch_sequence=batch_seq,batch_sha256=batch_sha)))


class ReferenceDelivery:
    @classmethod
    def create(cls,root,source_reference,*,policy=None,diagnostic=False,clock=None):
        policy=policy or DeliveryPolicy();before=_now(clock)
        source=ReferenceLedger.open(source_reference,clock=clock)
        with source._lease():
            source._check(active=False);receipt=source._receipt()
            if not diagnostic and (source.manifest['mode']!='prospective' or receipt['events'] or not before<stamp(source.manifest['start'])):
                raise ValueError('new empty prospective source and pre-start delivery registration required')
            manifest_raw=read_file(source.root/'manifest.json',maximum=65536)
            registered_raw=read_file(source.root/'registered.json',maximum=65536)
            if before<stamp(parse(registered_raw)['registered_at']):raise ValueError('source registration is not yet available')
            artifact=read_file(source.root/'artifact.json',maximum=65536) if source.manifest['artifact_sha256'] else None
            value=dict(schema_version=SCHEMA,root=str(Path(root).absolute()),registered_at=before.isoformat(),
                mode='diagnostic' if diagnostic else 'prospective',start=source.manifest['start'],end=source.manifest['end'],
                source_identity=source_reference,source_manifest_sha256=digest(manifest_raw),source_registration_sha256=digest(registered_raw),
                artifact_sha256=source.manifest['artifact_sha256'],roles=list(ROLES),policy=asdict(policy),
                runtime=runtime_hashes(),environment=_environment(),scope='retained_source_events_and_receipt_delivery_only',**FLAGS)
            _disk(root,policy);root=_new_root(root,forbidden=(source.root,))
            pin=_write_new(root/'manifest.json',value)
            _copy(root/'source-manifest.json',manifest_raw);_copy(root/'source-registered.json',registered_raw)
            if artifact is not None:_copy(root/'artifact.json',artifact)
            db=sqlite3.connect(root/'delivery.sqlite')
            try:
                db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
                for sql in SQL.values():db.execute(sql)
                with db:
                    db.execute('INSERT INTO state VALUES (1,0,?,0,?)',(pin,value['source_manifest_sha256']))
                    db.executemany('INSERT INTO cursors VALUES (?,0,NULL,NULL,NULL)',[(r,) for r in ROLES])
            finally:db.close()
            (root/'delivery.sqlite').chmod(0o600);(root/'writer.lock').touch(mode=0o600,exist_ok=False);_sync(root)
            completed=_now(clock)
            if completed<before or not diagnostic and completed>=stamp(value['start']):
                raise ValueError('delivery registration missed original start')
            ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=completed.isoformat()))
            final=_now(clock)
            if final<completed or not diagnostic and final>=stamp(value['start']):
                (root/'registered.json').unlink();_sync(root);raise ValueError('delivery durable completion missed original start')
        reference=dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,
            database_sha256=file_sha(root/'delivery.sqlite',policy.maximum_database_bytes),head_sha256=pin)
        return cls.open(reference,clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None,_recover=False):
        if type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','database_sha256','head_sha256'}:
            raise ValueError('original external delivery pins required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=65536)
        sha(reference['database_sha256'])
        ready=read_file(root/'registered.json',maximum=65536)
        if digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256']):
            raise ValueError('original delivery registration changed')
        value,registered=parse(raw),parse(ready);policy=DeliveryPolicy(**value['policy'])
        _guard_db(root/'delivery.sqlite',policy)
        expected={'manifest.json','registered.json','source-manifest.json','source-registered.json','delivery.sqlite','writer.lock'}
        if value['artifact_sha256']:expected.add('artifact.json')
        keys={'schema_version','root','registered_at','mode','start','end','source_identity','source_manifest_sha256',
            'source_registration_sha256','artifact_sha256','roles','policy','runtime','environment','scope'}|set(FLAGS)
        if (set(value)!=keys or set(registered)!={'manifest_sha256','registered_at'}
                or root.resolve()!=root or {p.name for p in root.iterdir()}!=expected or raw!=canonical(value) or ready!=canonical(registered)
                or value['root']!=str(root) or value['schema_version']!=SCHEMA or value['runtime']!=runtime_hashes()
                or value['environment']!=_environment() or value['roles']!=list(ROLES) or value['mode'] not in ('diagnostic','prospective')
                or value['scope']!='retained_source_events_and_receipt_delivery_only'
                or registered['manifest_sha256']!=reference['manifest_sha256']
                or not stamp(value['registered_at'])<=stamp(registered['registered_at'])
                or value['mode']=='prospective' and not stamp(registered['registered_at'])<stamp(value['start'])
                or any(value.get(k) is not False for k in FLAGS)):
            raise ValueError('original retained delivery scope/runtime differs')
        source_raw=read_file(root/'source-manifest.json',maximum=65536)
        source_ready=read_file(root/'source-registered.json',maximum=65536)
        if digest(source_raw)!=value['source_manifest_sha256'] or digest(source_ready)!=value['source_registration_sha256']:
            raise ValueError('retained original source registration differs')
        source_manifest=parse(source_raw);source_registered=parse(source_ready)
        _source_descriptor(value['source_identity'],value['source_identity']);ReferencePolicy(**source_manifest['policy'])
        if (source_raw!=canonical(source_manifest) or source_ready!=canonical(source_registered)
                or set(source_registered)!={'manifest_sha256','registered_at'}
                or source_manifest['schema_version']!=SOURCE_SCHEMA or source_manifest['runtime']!=source_runtime_hashes()
                or source_manifest['environment']!=_environment() or any(source_manifest.get(k) is not False for k in FLAGS)
                or source_manifest['mode'] not in ('diagnostic','prospective')
                or source_manifest['mandatory_pairs']!=list(MANDATORY)
                or source_manifest['pairs']!=source_pairs([p for p in source_manifest['pairs'] if p not in MANDATORY])
                or source_manifest['root']!=value['source_identity']['root']
                or value['source_identity']['manifest_sha256']!=value['source_manifest_sha256']
                or value['source_identity']['registration_sha256']!=value['source_registration_sha256']
                or source_registered['manifest_sha256']!=value['source_manifest_sha256']
                or source_manifest['artifact_sha256']!=value['artifact_sha256']
                or value['start']!=source_manifest['start'] or value['end']!=source_manifest['end']
                or not stamp(value['start'])<stamp(value['end'])
                or not stamp(source_manifest['registered_at'])<=stamp(source_registered['registered_at'])<=stamp(value['registered_at'])
                or source_manifest['mode']=='prospective' and not stamp(source_registered['registered_at'])<stamp(source_manifest['start'])
                or value['mode']=='prospective' and value['source_identity']['head_sha256']!=value['source_manifest_sha256']
                or value['mode']=='prospective' and source_manifest['mode']!='prospective'):
            raise ValueError('retained source identity/window differs')
        artifact=read_file(root/'artifact.json',maximum=65536) if value['artifact_sha256'] else None
        if artifact is not None:
            _artifact(artifact)
            if digest(artifact)!=value['artifact_sha256']:raise ValueError('retained source artifact changed')
        obj=cls();obj.root=root;obj.path=root/'delivery.sqlite';obj.manifest=value;obj.policy=policy
        obj.reference=dict(reference);obj.clock=clock;obj.source_manifest=source_manifest;obj.artifact=artifact
        with obj._lease():
            actual_sha=file_sha(obj.path,policy.maximum_database_bytes)
            if not _recover and actual_sha!=sha(reference['database_sha256']):raise ValueError('original delivery database pin differs')
            db=_connect(obj.path,policy)
            try:
                head=db.execute('SELECT head FROM state WHERE id=1').fetchone()[0]
                anchor=sha(reference['head_sha256'])
                if _recover:
                    if anchor!=reference['manifest_sha256'] and not db.execute('SELECT 1 FROM events WHERE sha=?',(anchor,)).fetchone():
                        raise ValueError('known external delivery head is not an ancestor')
                    obj.reference.update(database_sha256=actual_sha,head_sha256=head)
                elif head!=anchor:raise ValueError('original delivery head differs')
            finally:db.close()
        obj.identity=_file_identity(obj.path)
        obj.audit()
        return obj

    @classmethod
    def recover(cls,known_reference,*,clock=None):
        """Explicit read-only recovery from a known ancestor after a lost receipt.

        The entire current history/projections must replay. This issues a NEW
        checkpoint and never claims that the ancestor's DB bytes are current.
        """
        queue=cls.open(known_reference,clock=clock,_recover=True)
        result=queue.receipt()
        result['recovery']=dict(known_ancestor_head_sha256=known_reference['head_sha256'],
            recovered_head_sha256=result['reference']['head_sha256'],
            prior_database_bytes_reproduced=known_reference['database_sha256']==result['reference']['database_sha256'],
            semantic_extension_replay_pass=True,new_checkpoint_required=True)
        return result

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock',maximum=0);fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _check(self,*,active=False):
        if self.manifest['runtime']!=runtime_hashes() or self.identity!=_file_identity(self.path):
            raise ValueError('delivery runtime/database changed outside this writer')
        for name,pin in [('manifest.json',self.reference['manifest_sha256']),('source-manifest.json',self.manifest['source_manifest_sha256']),
                ('source-registered.json',self.manifest['source_registration_sha256'])]:
            if digest(read_file(self.root/name,maximum=65536))!=pin:raise ValueError('original delivery source/manifest changed')
        if self.artifact is not None and digest(read_file(self.root/'artifact.json',maximum=65536))!=self.manifest['artifact_sha256']:
            raise ValueError('retained original artifact changed')
        now=_now(self.clock)
        if getattr(self,'_last_clock',now)>now:raise ValueError('delivery clock moved backwards')
        db=_connect(self.path,self.policy)
        try:last=db.execute('SELECT payload FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        finally:db.close()
        observed=stamp(parse(last[0])['at']) if last else stamp(parse(read_file(self.root/'registered.json'))['registered_at'])
        if now<observed:raise ValueError('delivery clock before durable event observation')
        self._last_clock=now
        if active and self.manifest['mode']=='prospective' and not stamp(self.manifest['start'])<=now<=stamp(self.manifest['end']):
            raise ValueError('original delivery window is not open')
        _disk(self.root,self.policy);return now

    def _commit(self,kind,payload,apply):
        now=self._check();raw=canonical(payload)
        if len(raw)>65536:raise ValueError('bounded delivery event required')
        db=_connect(self.path,self.policy,write=True)
        try:
            db.execute('BEGIN IMMEDIATE')
            seq,previous,_,_=db.execute('SELECT seq,head,source_seq,source_head FROM state WHERE id=1').fetchone()
            prior=db.execute('SELECT payload FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            last=stamp(parse(prior[0])['at']) if prior else stamp(parse(read_file(self.root/'registered.json'))['registered_at'])
            if not last<=stamp(payload['at'])<=now:raise ValueError('delivery event clock moved backwards')
            if seq>=self.policy.maximum_events:raise ValueError('delivery event budget exhausted')
            seq+=1;head=digest(canonical(dict(sequence=seq,kind=kind,payload=payload,previous_sha256=previous)))
            db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(seq,kind,raw,previous,head));apply(db,seq)
            db.execute('UPDATE state SET seq=?,head=? WHERE id=1',(seq,head));db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
        self.identity=_file_identity(self.path)

    def _receipt(self):
        db=_connect(self.path,self.policy)
        try:
            seq,head,source_seq,source_head=db.execute('SELECT seq,head,source_seq,source_head FROM state WHERE id=1').fetchone()
            return dict(reference=dict(self.reference,database_sha256=file_sha(self.path,self.policy.maximum_database_bytes),head_sha256=head),
                events=seq,source_events=source_seq,source_head_sha256=source_head,batches=db.execute('SELECT count(*) FROM batches').fetchone()[0],
                role_cursors={r:dict(cursor=c,pending_sequence=p,delivery_id=d) for r,c,p,d in db.execute('SELECT role,cursor,pending_seq,delivery_id FROM cursors')},
                source_sqlite_bytes_retained=False,worker_execution_qualified=False,**FLAGS)
        finally:db.close()

    def receipt(self):
        with self._lease():self._check();return self._receipt()

    def ingest(self,source_reference):
        with self._lease():
            started=monotonic();self._check(active=True);_source_descriptor(source_reference,self.manifest['source_identity'])
            audit_reference_ledger(source_reference,clock=self.clock)
            source=ReferenceLedger.open(source_reference,clock=self.clock)
            with source._lease():
                source._check(active=False);original=source_database(source.path,source.policy,readonly=True)
                db=_connect(self.path,self.policy)
                try:
                    _,_,cursor,previous=db.execute('SELECT seq,head,source_seq,source_head FROM state WHERE id=1').fetchone()
                    batch_seq=db.execute('SELECT count(*) FROM batches').fetchone()[0]+1
                    total,original_head,pending=original.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
                    tail=original.execute('SELECT kind,payload FROM events ORDER BY seq DESC LIMIT 1').fetchone()
                    information_end=_event_time(tail[0],parse(tail[1])) if tail else stamp(source.manifest['registered_at'])
                    prefix=self.manifest['source_manifest_sha256'] if cursor==0 else original.execute('SELECT sha FROM events WHERE seq=?',(cursor,)).fetchone()
                    if cursor:prefix=prefix[0] if prefix else None
                    if pending is not None or cursor>total or prefix!=previous:raise ValueError('source checkpoint rewound or divergent')
                    if cursor==total:return dict(**self._receipt(),ingested=False)
                    if batch_seq>self.policy.maximum_batches:raise ValueError('delivery batch budget exhausted')
                    rows=[];size=0;boundary=0;in_poll=False
                    for row in original.execute('SELECT seq,kind,payload,previous,sha FROM events WHERE seq>? ORDER BY seq',(cursor,)):
                        if len(rows)>=self.policy.maximum_source_events_per_batch or size+len(row[2])>self.policy.maximum_source_bytes_per_batch:break
                        rows.append(row);size+=len(row[2])
                        if row[1]=='poll_prepared':in_poll=True
                        elif row[1]=='poll_complete':in_poll=False
                        if not in_poll:boundary=len(rows)
                    rows=rows[:boundary]
                    if not rows:raise ValueError('complete original source operation exceeds batch budget')
                    end=rows[-1][0]
                    if end>self.policy.maximum_source_events:raise ValueError('retained source event budget exhausted')
                    with SourceReplay(self.source_manifest,self.artifact,parent=self.root.parent,maximum_database_bytes=self.policy.maximum_scratch_database_bytes) as replay:
                        for row in db.execute('SELECT * FROM source_events ORDER BY seq'):replay.feed(row)
                        for row in rows:replay.feed(row)
                        if replay.pending is not None or replay.seq!=end or replay.head!=rows[-1][4]:
                            raise ValueError('new source prefix cannot be replayed within the retained contract')
                    if monotonic()-started>self.policy.maximum_ingest_seconds:raise ValueError('delivery ingest wall budget exhausted')
                    at=self._check(active=True)
                    if at<information_end:raise ValueError('future original source attestation unavailable')
                    batch=dict(schema_version=SCHEMA,batch_sequence=batch_seq,source_from=cursor+1,source_to=end,
                        source_previous_head=previous,source_end_head=rows[-1][4],source_reference=source_reference,
                        attested_source_sequence=total,source_information_end=information_end.isoformat(),queued_at=at.isoformat())
                    batch_sha=digest(canonical(batch));payload=dict(at=at.isoformat(),batch=batch,batch_sha256=batch_sha)
                    def apply(write,event_seq):
                        write.executemany('INSERT INTO source_events VALUES (?,?,?,?,?)',rows)
                        write.execute('INSERT INTO batches VALUES (?,?,?,?)',(batch_seq,canonical(batch),batch_sha,event_seq))
                        write.execute('UPDATE state SET source_seq=?,source_head=? WHERE id=1',(end,rows[-1][4]))
                    self._commit('ingest',payload,apply)
                    source._check(active=False)
                finally:db.close();original.close()
            return dict(**self._receipt(),ingested=True)

    def _resolved(self,db,batch):
        row=db.execute('SELECT sha FROM source_events WHERE seq=?',(batch['attested_source_sequence'],)).fetchone()
        return row is not None and row[0]==batch['source_reference']['head_sha256']

    def next(self,role):
        if role not in ROLES:raise ValueError('declared reference delivery role required')
        with self._lease():
            now=self._check(active=True);db=_connect(self.path,self.policy)
            try:
                cursor,pending,identity,offered=db.execute('SELECT cursor,pending_seq,delivery_id,offered_at FROM cursors WHERE role=?',(role,)).fetchone()
                seq=pending or cursor+1;row=db.execute('SELECT payload,sha FROM batches WHERE seq=?',(seq,)).fetchone()
                if row is None:return dict(**self._receipt(),delivery=None,status='empty')
                batch,batch_sha=parse(row[0]),row[1]
                if not self._resolved(db,batch):return dict(**self._receipt(),delivery=None,status='source_attestation_incomplete')
                if pending:
                    if now<stamp(offered):raise ValueError('delivery consumer clock moved backwards')
                    delivery=dict(role=role,batch_sequence=seq,batch_sha256=batch_sha,delivery_id=identity,offered_at=offered)
                else:
                    delivery=dict(role=role,batch_sequence=seq,batch_sha256=batch_sha,
                        delivery_id=_delivery_id(self.reference['manifest_sha256'],role,seq,batch_sha),offered_at=now.isoformat())
                    def apply(write,event_seq):
                        write.execute('UPDATE cursors SET pending_seq=?,delivery_id=?,offered_at=? WHERE role=?',
                            (seq,delivery['delivery_id'],delivery['offered_at'],role))
                    self._commit('offer',dict(at=now.isoformat(),delivery=delivery),apply)
            finally:db.close()
            return dict(**self._receipt(),delivery=delivery,status='offered',redelivered=pending is not None)

    def acknowledge(self,role,delivery_id,*,worker_receipt_sha256):
        if role not in ROLES:raise ValueError('declared reference delivery role required')
        sha(delivery_id);sha(worker_receipt_sha256)
        with self._lease():
            now=self._check();db=_connect(self.path,self.policy)
            try:
                old=db.execute('SELECT payload FROM acks WHERE delivery_id=?',(delivery_id,)).fetchone()
                if old:
                    ack=parse(old[0])
                    if ack['role']!=role or ack['worker_receipt_sha256']!=worker_receipt_sha256:
                        raise ValueError('conflicting repeated delivery acknowledgement')
                    return dict(**self._receipt(),acknowledgement=ack,stored=False)
                cursor,pending,identity,offered=db.execute('SELECT cursor,pending_seq,delivery_id,offered_at FROM cursors WHERE role=?',(role,)).fetchone()
                if identity!=delivery_id or pending!=cursor+1 or now<stamp(offered):raise ValueError('out-of-order or wrong-role delivery acknowledgement')
                ack=dict(role=role,batch_sequence=pending,delivery_id=delivery_id,worker_receipt_sha256=worker_receipt_sha256,acknowledged_at=now.isoformat())
                def apply(write,event_seq):
                    write.execute('INSERT INTO acks VALUES (?,?,?,?,?)',(role,pending,delivery_id,canonical(ack),event_seq))
                    write.execute('UPDATE cursors SET cursor=?,pending_seq=NULL,delivery_id=NULL,offered_at=NULL WHERE role=?',(pending,role))
                self._commit('ack',dict(at=now.isoformat(),acknowledgement=ack),apply)
            finally:db.close()
            return dict(**self._receipt(),acknowledgement=ack,stored=True)

    def read(self,role,delivery_id):
        if role not in ROLES:raise ValueError('declared reference delivery role required')
        with self._lease():
            now=self._check();db=_connect(self.path,self.policy)
            try:
                _,seq,identity,offered=db.execute('SELECT cursor,pending_seq,delivery_id,offered_at FROM cursors WHERE role=?',(role,)).fetchone()
                if identity!=delivery_id or seq is None or now<stamp(offered):raise ValueError('original pending role delivery required')
                raw,batch_sha=db.execute('SELECT payload,sha FROM batches WHERE seq=?',(seq,)).fetchone();batch=parse(raw)
                if not self._resolved(db,batch):raise ValueError('unresolved original source attestation')
                with SourceReplay(self.source_manifest,self.artifact,parent=self.root.parent,maximum_database_bytes=self.policy.maximum_scratch_database_bytes) as replay:
                    for row in db.execute('SELECT seq,kind,payload,previous,sha FROM source_events WHERE seq<=? ORDER BY seq',(batch['source_to'],)):replay.feed(row)
                    view=replay.view()
                events=[dict(sequence=s,kind=k,payload=parse(p),previous_sha256=prior,sha256=h)
                    for s,k,p,prior,h in db.execute('SELECT * FROM source_events WHERE seq BETWEEN ? AND ? ORDER BY seq',(batch['source_from'],batch['source_to']))]
                ready=stamp(self.manifest['start'])<=now<=stamp(self.manifest['end']) and _sources_ready(view['windows'],now)
                result=dict(delivery=dict(role=role,batch_sequence=seq,delivery_id=identity,batch_sha256=batch_sha,offered_at=offered),
                    batch=batch,source_events=events,source_view=view,closed_candles_ready=ready,
                    worker_prediction_batch_available=False,**FLAGS)
                if len(canonical(result))>self.policy.maximum_delivery_bytes:raise ValueError('delivery payload budget exhausted')
                return result
            finally:db.close()

    def audit(self):
        with self._lease():
            self._check();db=_connect(self.path,self.policy)
            try:return _audit(self,db)
            finally:db.close()


def _audit(queue,db):
    previous=queue.reference['manifest_sha256'];count=0;batches=0
    last=stamp(parse(read_file(queue.root/'registered.json'))['registered_at'])
    cursors={r:[0,None,None,None] for r in ROLES};attestations={};started=monotonic()
    with SourceReplay(queue.source_manifest,queue.artifact,parent=queue.root.parent,maximum_database_bytes=queue.policy.maximum_scratch_database_bytes) as replay:
        replay.db.execute(SQL['acks'])
        for seq,kind,raw,prior,head in db.execute('SELECT * FROM events ORDER BY seq'):
            if monotonic()-started>60:raise ValueError('delivery audit wall budget exhausted')
            if len(raw)>65536:raise ValueError('delivery audit metadata budget exceeded')
            p=parse(raw);at=stamp(p['at'])
            keys={'ingest':{'at','batch','batch_sha256'},'offer':{'at','delivery'},'ack':{'at','acknowledgement'}}
            if kind not in keys or set(p)!=keys[kind]:raise ValueError('original delivery event schema differs')
            expected=digest(canonical(dict(sequence=seq,kind=kind,payload=p,previous_sha256=previous)))
            if seq!=count+1 or prior!=previous or head!=expected or raw!=canonical(p) or at<last:
                raise ValueError('original delivery event chain/clock differs')
            if kind=='ingest':
                b=p['batch'];pin=digest(canonical(b));batches+=1
                batch_keys={'schema_version','batch_sequence','source_from','source_to','source_previous_head','source_end_head',
                    'source_reference','attested_source_sequence','source_information_end','queued_at'}
                if (set(b)!=batch_keys or any(type(b[k]) is not int for k in ('batch_sequence','source_from','source_to','attested_source_sequence'))):
                    raise ValueError('typed original delivery batch required')
                _source_descriptor(b['source_reference'],queue.manifest['source_identity'])
                if (b['schema_version']!=SCHEMA or b['batch_sequence']!=batches or pin!=p['batch_sha256']
                        or b['source_from']!=replay.seq+1 or b['source_previous_head']!=replay.head
                        or not b['source_from']<=b['source_to']<=b['attested_source_sequence']
                        or b['source_to']-b['source_from']+1>queue.policy.maximum_source_events_per_batch
                        or stamp(b['queued_at'])!=at
                        or stamp(b['source_information_end'])>at
                        or queue.manifest['mode']=='prospective' and not stamp(queue.manifest['start'])<=at<=stamp(queue.manifest['end'])):
                    raise ValueError('original delivery batch ordering/scope differs')
                actual=db.execute('SELECT payload,sha,event_seq FROM batches WHERE seq=?',(batches,)).fetchone()
                if actual!=(canonical(b),pin,seq):raise ValueError('retained batch projection differs')
                size=0
                for row in db.execute('SELECT * FROM source_events WHERE seq BETWEEN ? AND ? ORDER BY seq',(b['source_from'],b['source_to'])):
                    size+=len(row[2]);replay.feed(row)
                if (replay.seq!=b['source_to'] or replay.head!=b['source_end_head'] or replay.pending is not None
                        or replay.last_time>at or size>queue.policy.maximum_source_bytes_per_batch):
                    raise ValueError('retained source batch prefix differs')
                target=b['attested_source_sequence'];binding=(b['source_reference']['head_sha256'],b['source_information_end'])
                if target in attestations and attestations[target]!=binding:raise ValueError('conflicting original source attestation')
                attestations[target]=binding
            elif kind=='offer':
                d=p['delivery'];role=d['role']
                if (set(d)!={'role','batch_sequence','batch_sha256','delivery_id','offered_at'} or type(d['batch_sequence']) is not int):
                    raise ValueError('typed original role delivery required')
                if role not in cursors:raise ValueError('unknown delivery role')
                cursor,pending,_,_=cursors[role]
                row=db.execute('SELECT payload,sha FROM batches WHERE seq=?',(d['batch_sequence'],)).fetchone()
                if row is None:raise ValueError('offered batch missing')
                b=parse(row[0])
                if (pending is not None or d['batch_sequence']!=cursor+1 or d['batch_sequence']>batches
                        or b['attested_source_sequence']>replay.seq or not queue._resolved(db,b)
                        or d['batch_sha256']!=row[1] or stamp(d['offered_at'])!=at
                        or d['delivery_id']!=_delivery_id(queue.reference['manifest_sha256'],role,d['batch_sequence'],row[1])):
                    raise ValueError('original offered role/cursor/source differs')
                if queue.manifest['mode']=='prospective' and not stamp(queue.manifest['start'])<=at<=stamp(queue.manifest['end']):
                    raise ValueError('original role offer outside delivery window')
                cursors[role]=[cursor,d['batch_sequence'],d['delivery_id'],d['offered_at']]
            elif kind=='ack':
                a=p['acknowledgement'];role=a['role']
                if set(a)!={'role','batch_sequence','delivery_id','worker_receipt_sha256','acknowledged_at'} or type(a['batch_sequence']) is not int:
                    raise ValueError('typed original acknowledgement required')
                if role not in cursors:raise ValueError('unknown acknowledgement role')
                cursor,pending,identity,offered=cursors[role];sha(a['worker_receipt_sha256'])
                if (pending!=cursor+1 or a['batch_sequence']!=pending or a['delivery_id']!=identity
                        or stamp(a['acknowledged_at'])!=at or at<stamp(offered)):
                    raise ValueError('original acknowledgement order differs')
                replay.db.execute('INSERT INTO acks VALUES (?,?,?,?,?)',(role,pending,identity,canonical(a),seq))
                cursors[role]=[pending,None,None,None]
            else:raise ValueError('unknown retained delivery event')
            previous=head;count+=1;last=at
        if db.execute('SELECT seq,head,source_seq,source_head FROM state WHERE id=1').fetchone()!=(count,previous,replay.seq,replay.head):
            raise ValueError('retained delivery state projection differs')
        if db.execute('SELECT count(*) FROM batches').fetchone()[0]!=batches or db.execute('SELECT count(*) FROM source_events').fetchone()[0]!=replay.seq:
            raise ValueError('orphan retained source/batch rows')
        if {r:[c,p,d,o] for r,c,p,d,o in db.execute('SELECT * FROM cursors')}!=cursors:
            raise ValueError('retained role cursor projection differs')
        actual=db.execute('SELECT * FROM acks ORDER BY role,batch_seq');expected=replay.db.execute('SELECT * FROM acks ORDER BY role,batch_seq')
        while True:
            a,b=actual.fetchmany(128),expected.fetchmany(128)
            if a!=b:raise ValueError('retained acknowledgement projection differs')
            if not a:break
        unresolved=0
        for seq,(head,information_end) in attestations.items():
            row=db.execute('SELECT sha,kind,payload FROM source_events WHERE seq=?',(seq,)).fetchone()
            if row is None:unresolved+=1
            elif row[0]!=head or _event_time(row[1],parse(row[2]))!=stamp(information_end):raise ValueError('original retained source anchor differs')
        queue._check()
        return dict(queue_events_checked=count,source_events_checked=replay.seq,batches_checked=batches,
            retained_source_integrity_pass=unresolved==0,retained_source_chain_integrity_pass=True,ordered_role_delivery_integrity_pass=True,
            unresolved_source_attestations=unresolved,missing_source_poll_slots=replay.missing_polls,
            explicit_rate_pause_slots=replay.rate_pauses,acknowledged_by_role={r:s[0] for r,s in cursors.items()},
            all_current_batches_acknowledged=batches>0 and all(s[0]==batches for s in cursors.values()) and unresolved==0,
            source_information_end=replay.last_time.isoformat(),
            scope=queue.manifest['mode'],source_sqlite_bytes_retained=False,worker_execution_qualified=False,**FLAGS)


class DeliveredReferenceReader:
    """Immutable role input; availability never becomes a cash-entry permission."""
    @classmethod
    def open(cls,queue,role,delivery_id,*,clock=None):
        packet=queue.read(role,delivery_id)
        obj=cls();obj._raw=canonical(packet);obj._manifest=canonical(queue.source_manifest)
        obj.clock=clock;obj._last_clock=_now(clock)
        if obj._last_clock<stamp(packet['delivery']['offered_at']):raise ValueError('future original role delivery')
        obj._runtime=runtime_hashes();return obj

    def _input(self):
        if runtime_hashes()!=self._runtime:raise ValueError('delivered reader runtime changed')
        now=_now(self.clock)
        packet=parse(self._raw);manifest=parse(self._manifest)
        if now<self._last_clock or now<stamp(packet['delivery']['offered_at']):raise ValueError('delivered reader clock moved backwards')
        self._last_clock=now
        ready=stamp(manifest['start'])<=now<=stamp(manifest['end']) and _sources_ready(packet['source_view']['windows'],now)
        return packet,now,ready

    def status(self):
        p,_,ready=self._input()
        return dict(batch_sha256=p['delivery']['batch_sha256'],delivery_id=p['delivery']['delivery_id'],
            role=p['delivery']['role'],source_sequence=p['source_view']['source_sequence'],
            closed_candles_ready=ready,available_to_role_at=p['delivery']['offered_at'],
            original_source_observed_at=p['source_view']['original_source_observed_at'],
            missing_source_poll_slots=p['source_view']['missing_source_poll_slots'],
            worker_prediction_batch_available=False,worker_execution_qualified=False,**FLAGS)

    def source_events(self):return self._input()[0]['source_events']

    def read_candles(self,pair,*,timeframe='5m',limit=120):
        from cryptoforge.supabase_executor import CandleRow
        p,_,ready=self._input();windows=p['source_view']['windows']
        if timeframe!='5m' or type(limit) is not int or limit!=120 or pair not in windows:
            raise ValueError('original delivered closed5m/bounded120 pair required')
        if not ready:raise ValueError('missing/failed/stale original delivered reference inputs')
        return [CandleRow(pair,pair.replace('/',''),datetime.fromtimestamp(r['open_ms']/1000,UTC),
            *[Decimal(v) for v in r['raw_row'][1:6]],cache_observed_at=stamp(r['known_at']))
            for r in windows[pair]['derived']['rows']]

    def features(self,pair):
        from cryptoforge.model_training import extract_features
        candles=self.read_candles(pair)
        with localcontext(Context(prec=28)):return extract_features(candles,[r.volume for r in candles])

    def original_forecasts(self):
        p,now,ready=self._input();windows=p['source_view']['windows'];events=p['source_events']
        expected={(pair,w['event_seq']) for pair,w in windows.items()}
        result=[]
        for event in events:
            if event['kind']!='forecast':continue
            value=event['payload'];payload=value['payload']
            same={(s['pair'],s['event_sequence']) for s in payload['sources']}==expected
            result.append(dict(original=value,usable_price_input_now=ready and same and now<stamp(payload['target_information_end']),
                entry_decision_available=False))
        return result


_LOADED_RUNTIME={name:digest(path.read_bytes()) for name,path in _paths().items()}
