"""Incremental semantic replay index for a NEW cash-only reference namespace.

SourceReplay remains the exact validator. Each update feeds only new original
events into its retained projection. Physical file SHA checks and a full replay
audit remain mandatory; this is not whole-system constant-time or admission.
"""
from contextlib import contextmanager
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
import fcntl
import os
from pathlib import Path
import shutil
import sqlite3
from time import monotonic

from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy,SQL as SOURCE_SQL,FLAGS,file_sha
from cryptoforge.reference_source_ledger import _database as source_db
from cryptoforge.reference_delivery import runtime_hashes as delivery_runtime
from cryptoforge.reference_delivery_source import SourceReplay

SQL={k:v for k,v in SOURCE_SQL.items() if k not in ('state',)}
SQL['identity']='CREATE TABLE identity (pin TEXT NOT NULL)'
SQL['checkpoint']='CREATE TABLE checkpoint (id INTEGER PRIMARY KEY CHECK(id=1),payload BLOB NOT NULL,sha TEXT NOT NULL)'
FIELDS=('seq','head','pending','windows','last_windows','last_poll','latest_forecasts','last_time',
        'missing_polls','rate_pauses','version_count','forecast_count')


@dataclass(frozen=True)
class PrefixPolicyV2:
    maximum_database_bytes:int=512*1024**2
    maximum_new_events:int=64
    maximum_state_bytes:int=1024**2
    maximum_update_seconds:int=30
    maximum_audit_seconds:int=120
    minimum_free_disk_mb:int=2048

    def __post_init__(self):
        if (any(type(v) is not int for v in asdict(self).values())
                or not 1024**2<=self.maximum_database_bytes<=4*1024**3 or self.maximum_database_bytes%4096
                or not 4<=self.maximum_new_events<=256 or not 65536<=self.maximum_state_bytes<=4*1024**2
                or not 1<=self.maximum_update_seconds<=60 or not 1<=self.maximum_audit_seconds<=600
                or self.minimum_free_disk_mb<2048):raise ValueError('explicit bounded incremental source policy required')


def runtime_hashes():
    value=dict(delivery_runtime(),reference_prefix_v2=digest(Path(__file__).read_bytes()),
        reference_prefix_v2_cli=digest((Path(__file__).resolve().parents[2]/'scripts/audit_reference_prefix_v2.py').read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded reference prefix v2 runtime changed')
    return value


def _snapshot(replay):
    if replay.pending is not None:raise ValueError('incremental checkpoint cannot end inside a source poll')
    value={k:getattr(replay,k) for k in FIELDS};value['last_time']=replay.last_time.isoformat()
    return value


def _restore(db,manifest,snapshot,seconds):
    if set(snapshot)!=set(FIELDS) or snapshot['pending'] is not None:raise ValueError('exact completed source replay checkpoint required')
    replay=object.__new__(SourceReplay);replay.manifest=manifest;replay.artifact=None;replay.db=db
    for key,value in snapshot.items():setattr(replay,key,value)
    replay.last_time=stamp(snapshot['last_time']);replay.started=monotonic();replay.maximum_seconds=seconds
    return replay


class ReferencePrefixV2:
    @classmethod
    def create(cls,root,source_reference,*,policy=None,clock=None):
        clock=clock or (lambda:datetime.now(UTC));now=stamp(clock());source=ReferenceLedger.open(source_reference,clock=clock)
        policy=policy or PrefixPolicyV2()
        if (type(policy) is not PrefixPolicyV2 or source.manifest['mode']!='prospective'
                or source.manifest['artifact_sha256'] is not None or source.receipt()['events']
                or not stamp(source.manifest['registered_at'])<=now<stamp(source.manifest['start'])):
            raise ValueError('empty prospective cash-only source required before original start')
        root=_new_root(root,forbidden=(source.root,));(root/'writer.lock').touch(mode=0o600)
        manifest=dict(schema_version='incremental-reference-prefix-v2',root=str(root),registered_at=now.isoformat(),
            source_reference=source_reference,source_manifest=source.manifest,policy=asdict(policy),runtime=runtime_hashes(),
            start=source.manifest['start'],end=source.manifest['end'],**FLAGS)
        pin=_write_new(root/'manifest.json',manifest)
        with SourceReplay(source.manifest,None,parent=root,maximum_database_bytes=policy.maximum_database_bytes) as replay:
            checkpoint=dict(source_reference=source_reference,snapshot=_snapshot(replay),source_view=replay.view())
        db=sqlite3.connect(root/'index.sqlite')
        try:
            db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
            for sql in SQL.values():db.execute(sql)
            with db:
                db.execute('INSERT INTO identity VALUES (?)',(pin,))
                raw=canonical(checkpoint)
                if len(raw)>policy.maximum_state_bytes:raise ValueError('initial prefix state byte budget exhausted')
                db.execute('INSERT INTO checkpoint VALUES (1,?,?)',(raw,digest(raw)))
        finally:db.close()
        (root/'index.sqlite').chmod(0o600);at=stamp(clock())
        if not now<=at<stamp(manifest['start']):raise ValueError('prefix setup missed prospective start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=at.isoformat()))
        if not at<=stamp(clock())<stamp(manifest['start']):
            (root/'registered.json').unlink();_sync(root);raise ValueError('prefix durable setup missed start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,
            database_sha256=file_sha(root/'index.sqlite',policy.maximum_database_bytes),head_sha256=digest(raw)),clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None):
        if type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','database_sha256','head_sha256'}:
            raise ValueError('exact external incremental prefix checkpoint required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        manifest=parse(raw);registered=parse(ready)
        if (root.resolve()!=root or manifest['root']!=str(root) or root.stat().st_uid!=os.getuid()
                or digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
                or raw!=canonical(manifest) or manifest['schema_version']!='incremental-reference-prefix-v2'
                or registered['manifest_sha256']!=reference['manifest_sha256'] or manifest['runtime']!=runtime_hashes()
                or not stamp(manifest['registered_at'])<=stamp(registered['registered_at'])<stamp(manifest['start'])
                or manifest['source_manifest']['mode']!='prospective' or manifest['source_manifest']['artifact_sha256'] is not None
                or any(manifest[k]!=manifest['source_manifest'][k] for k in ('start','end'))
                or manifest['source_reference']['manifest_sha256']!=digest(canonical(manifest['source_manifest']))
                or manifest['source_reference']['head_sha256']!=manifest['source_reference']['manifest_sha256']
                or any(manifest[k] is not False for k in FLAGS)):
            raise ValueError('original incremental source registration differs')
        ReferencePolicy(**manifest['source_manifest']['policy'])
        obj=cls();obj.root=root;obj.path=root/'index.sqlite';obj.manifest=manifest;obj.reference=dict(reference)
        obj.policy=PrefixPolicyV2(**manifest['policy']);obj.clock=clock or (lambda:datetime.now(UTC))
        with obj._lease():obj._check()
        return obj

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock',maximum=0);fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _db(self,write=False):
        if any(Path(str(self.path)+s).exists() for s in ('-journal','-wal','-shm')):raise ValueError('prefix hot journal requires investigation')
        db=sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=1)
        try:
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-128')
            if write:db.execute(f'PRAGMA max_page_count={self.policy.maximum_database_bytes//4096}');db.execute('PRAGMA synchronous=FULL')
            else:db.execute('PRAGMA query_only=ON')
            if (db.execute('PRAGMA journal_mode').fetchone()[0]!='delete' or db.execute('PRAGMA page_size').fetchone()[0]!=4096
                    or dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))!=SQL
                    or db.execute('SELECT pin FROM identity').fetchall()!=[(self.reference['manifest_sha256'],)]):
                raise ValueError('original prefix database schema differs')
            return db
        except BaseException:db.close();raise

    def _checkpoint(self,db):
        lengths=db.execute('SELECT length(payload) FROM checkpoint').fetchmany(2)
        if len(lengths)!=1 or not 0<lengths[0][0]<=self.policy.maximum_state_bytes:raise ValueError('bounded prefix state required')
        raw,pin=db.execute('SELECT payload,sha FROM checkpoint WHERE id=1').fetchone()
        if digest(raw)!=pin or pin!=self.reference['head_sha256']:raise ValueError('incremental prefix state commitment differs')
        value=parse(raw)
        if raw!=canonical(value) or set(value)!={'source_reference','snapshot','source_view'}:raise ValueError('canonical prefix state required')
        return value

    def _check(self):
        if (self.root.resolve()!=self.root or self.path!=self.root/'index.sqlite'
                or self.manifest['root']!=str(self.root) or self.reference['root']!=str(self.root)
                or {p.name for p in self.root.iterdir()}!={'manifest.json','registered.json','writer.lock','index.sqlite'}
                or digest(read_file(self.root/'manifest.json',maximum=131072))!=self.reference['manifest_sha256']
                or digest(read_file(self.root/'registered.json',maximum=4096))!=self.reference['registration_sha256']
                or parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest
                or PrefixPolicyV2(**self.manifest['policy'])!=self.policy or self.manifest['runtime']!=runtime_hashes()):
            raise ValueError('original prefix metadata/runtime differs')
        info=self.path.lstat()
        if info.st_uid!=os.getuid() or file_sha(self.path,self.policy.maximum_database_bytes)!=sha(self.reference['database_sha256']):
            raise ValueError('stale or changed prefix database; unknown commit cannot be adopted')
        now=stamp(self.clock())
        if now<stamp(self.manifest['registered_at']) or now<getattr(self,'last_clock',now):raise ValueError('prefix clock moved backwards')
        db=self._db()
        try:
            checkpoint=self._checkpoint(db)
            if stamp(checkpoint['snapshot']['last_time'])>now:raise ValueError('prefix checkpoint observed in the future')
        finally:db.close()
        self.last_clock=now;return now,checkpoint

    def view(self):
        with self._lease():
            _,checkpoint=self._check()
            return dict(reference=dict(self.reference),source_reference=checkpoint['source_reference'],source_view=checkpoint['source_view'],
                scope='cached_closed_reference_input_view_not_predictions_or_outcomes',**FLAGS)

    def ingest(self,source_reference):
        with self._lease():
            started=monotonic();now,checkpoint=self._check()
            if not stamp(self.manifest['start'])<=now<=stamp(self.manifest['end']):raise ValueError('prefix update outside original window')
            old_source=self.manifest['source_reference']
            if any(source_reference[k]!=old_source[k] for k in ('root','manifest_sha256','registration_sha256')):
                raise ValueError('prefix original source identity differs')
            source=ReferenceLedger.open(source_reference,clock=self.clock)
            if source.manifest!=self.manifest['source_manifest']:raise ValueError('prefix source registration changed')
            with source._lease():
                source._check(active=False);original=source_db(source.path,source.policy,readonly=True)
                db=None
                try:
                    original.execute('BEGIN');last,head,pending=original.execute('SELECT seq,head,pending FROM state WHERE id=1').fetchone()
                    previous=checkpoint['snapshot'];delta=last-previous['seq']
                    anchor=(original.execute('SELECT sha FROM events WHERE seq=?',(previous['seq'],)).fetchone()
                        if previous['seq'] else (old_source['manifest_sha256'],))
                    if pending is not None or anchor!=(previous['head'],) or delta<0 or delta>self.policy.maximum_new_events:
                        raise ValueError('complete bounded original source extension required')
                    if head!=source_reference['head_sha256']:raise ValueError('prefix source head differs')
                    if delta==0:
                        if source_reference!=checkpoint['source_reference']:raise ValueError('same source head has changed physical bytes')
                        return dict(reference=dict(self.reference),new_source_events=0,semantic_prefix_reprocessed=False,**FLAGS)
                    reserve=self.policy.maximum_state_bytes+delta*source.policy.maximum_event_bytes*3+1024**2
                    if self.path.stat().st_size+reserve>self.policy.maximum_database_bytes:raise ValueError('prefix byte reserve exhausted before update')
                    if shutil.disk_usage(self.root).free<self.policy.minimum_free_disk_mb*1024**2+reserve:
                        raise ValueError('prefix disk reserve preserved')
                    db=self._db(write=True);db.execute('BEGIN IMMEDIATE')
                    replay=_restore(db,source.manifest,previous,self.policy.maximum_update_seconds)
                    for seq,kind,size,prior,event_head in original.execute('SELECT seq,kind,length(payload),previous,sha FROM events WHERE seq>? ORDER BY seq',(previous['seq'],)):
                        if not 0<size<=source.policy.maximum_event_bytes:raise ValueError('bounded original source event required')
                        raw=original.execute('SELECT payload FROM events WHERE seq=?',(seq,)).fetchone()[0]
                        replay.feed((seq,kind,raw,prior,event_head))
                        db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(seq,kind,raw,prior,event_head))
                    if replay.seq!=last or replay.head!=head or replay.last_time>stamp(self.clock()):raise ValueError('prefix extension completeness/clock differs')
                    value=dict(source_reference=source_reference,snapshot=_snapshot(replay),source_view=replay.view());raw=canonical(value)
                    if len(raw)>self.policy.maximum_state_bytes:raise ValueError('prefix state byte budget exhausted')
                    if monotonic()-started>self.policy.maximum_update_seconds:raise ValueError('prefix whole update budget exhausted')
                    db.execute('UPDATE checkpoint SET payload=?,sha=? WHERE id=1',(raw,digest(raw)));db.commit()
                except BaseException:
                    if db is not None:db.rollback()
                    raise
                finally:
                    if db is not None:db.close()
                    original.close()
            self.reference=dict(self.reference,database_sha256=file_sha(self.path,self.policy.maximum_database_bytes),head_sha256=digest(raw))
            self._check()
            return dict(reference=dict(self.reference),new_source_events=delta,source_sequence=last,
                semantic_prefix_reprocessed=False,physical_sha_still_reads_whole_database=True,**FLAGS)

    def audit(self,*,scratch_parent):
        parent=Path(scratch_parent).absolute()
        if parent.resolve()!=parent or self.root==parent or self.root in parent.parents:raise ValueError('audit scratch must stay outside prefix namespace')
        with self._lease():
            _,checkpoint=self._check();db=self._db();started=monotonic()
            try:
                db.execute('BEGIN')
                with SourceReplay(self.manifest['source_manifest'],None,parent=parent,
                        maximum_database_bytes=self.policy.maximum_database_bytes,maximum_seconds=self.policy.maximum_audit_seconds) as replay:
                    for seq,kind,size,prior,head in db.execute('SELECT seq,kind,length(payload),previous,sha FROM events ORDER BY seq'):
                        if not 0<size<=self.manifest['source_manifest']['policy']['maximum_event_bytes']:raise ValueError('bounded retained source event required')
                        raw=db.execute('SELECT payload FROM events WHERE seq=?',(seq,)).fetchone()[0];replay.feed((seq,kind,raw,prior,head))
                    if canonical(_snapshot(replay))!=canonical(checkpoint['snapshot']) or canonical(replay.view())!=canonical(checkpoint['source_view']):
                        raise ValueError('incremental prefix projection differs from full original replay')
                    original=self.manifest['source_reference'];current=checkpoint['source_reference']
                    if current['head_sha256']!=replay.head or any(current[k]!=original[k] for k in ('root','manifest_sha256','registration_sha256')):
                        raise ValueError('retained prefix source checkpoint linkage differs')
                    for table,order in [('versions','source_id,version'),('forecasts','id')]:
                        left=iter(db.execute(f'SELECT * FROM {table} ORDER BY {order}'));right=iter(replay.db.execute(f'SELECT * FROM {table} ORDER BY {order}'))
                        while True:
                            a=next(left,None);b=next(right,None)
                            if a!=b:raise ValueError('incremental prefix index differs from full replay')
                            if a is None:break
                            if monotonic()-started>self.policy.maximum_audit_seconds:raise ValueError('prefix full audit budget exhausted')
            finally:db.close()
            return dict(reference=dict(self.reference),source_events=checkpoint['snapshot']['seq'],
                prefix_semantic_integrity_pass=True,source_view_sha256=digest(canonical(checkpoint['source_view'])),
                scope='incremental_cash_source_index_not_delivery_or_worker_qualification',**FLAGS)


_LOADED=runtime_hashes()
