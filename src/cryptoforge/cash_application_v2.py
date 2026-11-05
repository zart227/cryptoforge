"""Prospective indexed, lossless compressed cash application receipt archive.

The frozen v1 decision/worker dispatch function is reused. Only this NEW schema
archives its own completed groups, preserving all original bytes and receipt SHA.
Normal checks inspect the committed head and at most one raw tail; full history
is streamed separately after the original end. No old v1 namespace is adopted.
"""
from contextlib import contextmanager
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from fractions import Fraction
import fcntl
import gzip
import io
import math
import os
from pathlib import Path
import shutil
import sqlite3
from time import monotonic

from cryptoforge.cash_entry_contract import FLAGS,load_cash_contract,evaluate_cash_packet,_queue_identity
from cryptoforge.cash_worker_application import CashWorkerApplication,_heartbeat,_worker_identity,_pin,runtime_hashes as v1_runtime
from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync
from cryptoforge.reference_delivery import ReferenceDelivery
from cryptoforge.reference_delivery import _connect as queue_connect
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from cryptoforge.paper_capture_v3 import _lease as capture_lease
from cryptoforge.paper_capture_state_v2 import _logical,_active

FILES=('ack.json','complete.json','input.json','prepared.json','worker-result.json')
MAGIC=b'CF-CASH-GROUP-V2\n'
SQL={
 'identity':'CREATE TABLE identity (pin TEXT NOT NULL)',
 'state':'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,group_head TEXT NOT NULL,archive_head TEXT NOT NULL,worker_after BLOB NOT NULL)',
 'groups':'CREATE TABLE groups (seq INTEGER PRIMARY KEY,previous TEXT NOT NULL,group_head TEXT NOT NULL,raw_bytes INTEGER NOT NULL,compressed_sha TEXT NOT NULL,payload BLOB NOT NULL,archive_previous TEXT NOT NULL,archive_sha TEXT UNIQUE NOT NULL)',
 'groups_no_update':"CREATE TRIGGER groups_no_update BEFORE UPDATE ON groups BEGIN SELECT RAISE(ABORT,'immutable v2 cash receipt'); END",
 'groups_no_delete':"CREATE TRIGGER groups_no_delete BEFORE DELETE ON groups BEGIN SELECT RAISE(ABORT,'immutable v2 cash receipt'); END",
}


@dataclass(frozen=True)
class CashApplicationPolicyV2:
    maximum_groups:int=2000000
    maximum_bytes:int=512*1024**2
    maximum_group_bytes:int=2*1024**2
    maximum_scan_seconds:int=15
    minimum_free_disk_mb:int=2048
    maximum_audit_seconds:int=120

    def __post_init__(self):
        if (any(type(v) is not int for v in asdict(self).values()) or not 1<=self.maximum_groups<=2000000
                or not 1024**2<=self.maximum_group_bytes<=16*1024**2
                or not self.maximum_group_bytes+1024**2<=self.maximum_bytes<=4*1024**3 or self.maximum_bytes%4096
                or not 1<=self.maximum_scan_seconds<=30 or not 1<=self.maximum_audit_seconds<=600
                or self.minimum_free_disk_mb<2048):raise ValueError('explicit bounded v2 receipt archive required')


def _runtime():
    value=dict(v1_runtime(),cash_application_v2=digest(Path(__file__).read_bytes()),
        cash_application_v2_cli=digest((Path(__file__).resolve().parents[2]/'scripts/audit_cash_application_v2.py').read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded v2 cash runtime changed')
    return value


def _archive_hash(sequence,previous_group,group_head,raw_bytes,compressed_sha,previous_archive):
    return digest(canonical(dict(sequence=sequence,previous_group=previous_group,group_head=group_head,
        raw_bytes=raw_bytes,compressed_sha256=compressed_sha,previous_archive=previous_archive)))


def _files(folder,policy):
    if {p.name for p in folder.iterdir()}!=set(FILES):raise ValueError('completed original v2 group required')
    values={};total=0
    for name in FILES:
        values[name]=read_file(folder/name,maximum=policy.maximum_group_bytes-total);total+=len(values[name])
    return values


def _encode(values,policy):
    target=io.BytesIO()
    with gzip.GzipFile(fileobj=target,mode='wb',filename='',mtime=0,compresslevel=6) as stream:
        stream.write(MAGIC)
        for name in FILES:
            label=name.encode();raw=values[name];stream.write(bytes([len(label)])+label+len(raw).to_bytes(8,'big'))
            for offset in range(0,len(raw),65536):stream.write(raw[offset:offset+65536])
            if target.tell()>policy.maximum_group_bytes+65536:raise ValueError('bounded v2 compressed group required')
    result=target.getvalue()
    if len(result)>policy.maximum_group_bytes+65536:raise ValueError('bounded v2 compressed group required')
    return result


def _decode(payload,raw_bytes,policy):
    if len(payload)>policy.maximum_group_bytes+65536 or not 0<=raw_bytes<=policy.maximum_group_bytes:
        raise ValueError('bounded declared v2 decompression required')
    values={};total=0
    def exact(stream,n):
        value=stream.read(n)
        if len(value)!=n:raise ValueError('truncated v2 receipt archive')
        return value
    with gzip.GzipFile(fileobj=io.BytesIO(payload),mode='rb') as stream:
        if exact(stream,len(MAGIC))!=MAGIC:raise ValueError('v2 receipt frame required')
        for name in FILES:
            n=exact(stream,1)[0]
            if n!=len(name) or exact(stream,n)!=name.encode():raise ValueError('exact v2 receipt filename required')
            size=int.from_bytes(exact(stream,8),'big');total+=size
            if total>raw_bytes:raise ValueError('v2 decompressed byte budget exhausted')
            values[name]=exact(stream,size)
        if total!=raw_bytes or stream.read(1):raise ValueError('v2 receipt byte count/trailing data differs')
    return values


class SegmentedCashApplicationV2(CashWorkerApplication):
    @classmethod
    def create(cls,root,contract_reference,queue,worker,*,policy=None,clock=None):
        clock=clock or (lambda:datetime.now(UTC));now=stamp(clock());contract=load_cash_contract(contract_reference)
        identity=_worker_identity(worker);role=worker.protocol['role'];policy=policy or CashApplicationPolicyV2()
        if (type(policy) is not CashApplicationPolicyV2 or type(queue) is not ReferenceDelivery
                or queue.manifest['mode']!='prospective' or _queue_identity(queue)!=contract['queue_identity'] or queue.receipt()['events']
                or worker.protocol['candidate_sha256']!=contract['strategies'][role]
                or worker.protocol['study_protocol_sha256']!=contract_reference['contract_sha256']
                or any(worker.protocol[k]!=contract[k] for k in ('start','end'))
                or worker.protocol['plan']['entry_cutoff']!=contract['entry_cutoff']
                or len(contract['pairs'])>worker.capture_policy.maximum_predictions_per_tick
                or not stamp(worker.registration['registered_at'])<=now<stamp(contract['start']) or worker._head()[1]!='genesis'):
            raise ValueError('new prospective v2 cash/queue/worker identity required')
        cost=math.ceil((Fraction(worker.config.entry_fee)+Fraction(worker.config.exit_fee)+2*Fraction(worker.config.slippage))*10000)
        if contract['rules'][role]['round_trip_cost_bps']<cost:raise ValueError('v2 cash cost floor below worker assumptions')
        root=_new_root(root,forbidden=(queue.root,worker.root,Path(contract_reference['root']),Path(queue.manifest['source_identity']['root'])))
        (root/'groups').mkdir(mode=0o700)
        for name in ('writer.lock','dispatch.lock'):(root/name).touch(mode=0o600)
        value=dict(schema_version='indexed-cash-worker-application-v2',root=str(root),registered_at=now.isoformat(),
            contract_reference=contract_reference,queue_identity=_queue_identity(queue),worker_identity=identity,role=role,
            initial_queue_reference=queue.receipt()['reference'],
            policy=asdict(policy),runtime=_runtime(),worker_initial_head=list(worker._head()),start=contract['start'],end=contract['end'],
            assumed_worker_cost_floor_bps=cost,archive_codec='lossless-gzip-original-group-files-v1',**FLAGS)
        pin=_write_new(root/'manifest.json',value)
        db=sqlite3.connect(root/'archive.sqlite')
        try:
            db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
            for sql in SQL.values():db.execute(sql)
            with db:
                db.execute('INSERT INTO identity VALUES (?)',(pin,))
                db.execute('INSERT INTO state VALUES (1,0,?,?,?)',(pin,pin,canonical(value['worker_initial_head'])))
        finally:db.close()
        (root/'archive.sqlite').chmod(0o600);at=stamp(clock())
        if not now<=at<stamp(contract['start']):raise ValueError('v2 setup missed original start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=at.isoformat()))
        if not at<=stamp(clock())<stamp(contract['start']):
            (root/'registered.json').unlink();_sync(root);raise ValueError('v2 durable setup missed start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,sequence=0,
            head_sha256=pin,archive_head_sha256=pin),clock=clock)

    @classmethod
    def _load(cls,reference,clock):
        if (type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','sequence','head_sha256','archive_head_sha256'}
                or type(reference['sequence']) is not int or reference['sequence']<0):raise ValueError('exact v2 external archive checkpoint required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        value=parse(raw);registered=parse(ready);contract=load_cash_contract(value['contract_reference'])
        sha(reference['head_sha256']);sha(reference['archive_head_sha256'])
        if (root.resolve()!=root or root.stat().st_uid!=os.getuid() or value['root']!=str(root)
                or digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
                or value['schema_version']!='indexed-cash-worker-application-v2' or value['runtime']!=_runtime()
                or registered['manifest_sha256']!=reference['manifest_sha256']
                or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])
                or any(value[k]!=contract[k] for k in ('start','end')) or any(value[k] is not False for k in FLAGS)):
            raise ValueError('original v2 application registration/runtime differs')
        obj=cls();obj.root=root;obj.manifest=value;obj.contract=contract;obj.reference=dict(reference)
        obj.policy=CashApplicationPolicyV2(**value['policy']);obj.clock=clock or (lambda:datetime.now(UTC))
        return obj

    @classmethod
    def open(cls,reference,*,clock=None):
        obj=cls._load(reference,clock)
        with obj._dispatch(),obj._lease():obj._scan()
        return obj

    @contextmanager
    def _dispatch(self):
        read_file(self.root/'dispatch.lock',maximum=0);fd=os.open(self.root/'dispatch.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _db(self,write=False):
        path=self.root/'archive.sqlite';info=path.lstat()
        if path.resolve()!=path or not path.is_file() or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>self.policy.maximum_bytes:
            raise ValueError('original bounded v2 archive database required')
        if any(Path(str(path)+suffix).exists() for suffix in ('-journal','-wal','-shm')):raise ValueError('v2 hot journal requires explicit investigation')
        db=sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=1)
        try:
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-128')
            if write:
                db.execute(f'PRAGMA max_page_count={self.policy.maximum_bytes//4096}');db.execute('PRAGMA synchronous=FULL')
            else:db.execute('PRAGMA query_only=ON')
            if (db.execute('PRAGMA journal_mode').fetchone()[0]!='delete' or db.execute('PRAGMA page_size').fetchone()[0]!=4096
                    or dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))!=SQL
                    or db.execute('SELECT pin FROM identity').fetchall()!=[(self.reference['manifest_sha256'],)]):
                raise ValueError('original v2 archive schema/identity differs')
            return db
        except BaseException:db.close();raise

    def _static(self):
        names={'manifest.json','registered.json','writer.lock','dispatch.lock','archive.sqlite','groups'}
        if {p.name for p in self.root.iterdir()}!=names or (self.root/'groups').resolve()!=self.root/'groups':raise ValueError('v2 archive inventory differs')
        if (parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest
                or _pin(self.root/'manifest.json')!=self.reference['manifest_sha256'] or _pin(self.root/'registered.json')!=self.reference['registration_sha256']
                or self.manifest['runtime']!=_runtime() or load_cash_contract(self.manifest['contract_reference'])!=self.contract
                or CashApplicationPolicyV2(**self.manifest['policy'])!=self.policy):raise ValueError('v2 original metadata/runtime differs')

    def _validate(self,values,sequence,previous,worker_before):
        complete=parse(values['complete.json']);original=parse(values['input.json']);prepared=parse(values['prepared.json'])
        result=parse(values['worker-result.json']);ack=parse(values['ack.json']);at=original['derived']['source_observed_at'];packet=original['packet']
        expected=(evaluate_cash_packet(self.contract,self.manifest['contract_reference']['contract_sha256'],packet,self.manifest['role'],observed_at=at)
            if packet is not None else _heartbeat(self.reference['manifest_sha256'],at))
        if (set(complete['files'])!=set(FILES)-{'complete.json'} or complete['sequence']!=sequence or complete['previous_sha256']!=previous
                or original['derived']!=expected or prepared['worker_before']!=worker_before or result['worker_before']!=worker_before
                or result['worker_identity']!=self.manifest['worker_identity'] or result['input_sha256']!=digest(values['input.json'])
                or prepared['input_sha256']!=result['input_sha256'] or complete['worker_after']!=result['worker_after']
                or complete['queue_after']!=ack['reference'] or any(complete[k] is not False or result[k] is not False for k in FLAGS)):
            raise ValueError('v2 original cash receipt linkage differs')
        for name,identity in complete['files'].items():
            if identity!=dict(bytes=len(values[name]),sha256=digest(values[name])):raise ValueError('v2 original receipt file digest differs')
        event=result['prepared_tick'];after=result['worker_after'];terminal=parse(after[2])
        from cryptoforge.evidence_segments import _verified_frame
        _verified_frame(canonical(event)+b'\n',worker_before[0]+1,worker_before[4])
        _verified_frame(canonical(dict(sequence=after[0],kind=after[1],payload=terminal,previous_sha256=after[3],sha256=after[4]))+b'\n',after[0],after[3])
        if (event['kind']!='prepared' or event['payload']['phase']!='tick' or event['payload']['inputs']!={k:expected[k] for k in ('predictions','source_id','source_observed_at','source_sha256')}
                or after[1]!='complete' or terminal['phase']!='tick' or terminal['prepared_seq']!=worker_before[0]+1 or terminal['result']!=result['result']
                or complete['delivery_id']!=expected['source_id'] or stamp(at)<stamp(parse(worker_before[2])['at'])
                or stamp(prepared['at'])!=stamp(at)
                or not stamp(at)<=stamp(event['payload']['at'])<=stamp(terminal['at'])<=stamp(result['application_completed_at'])<=stamp(complete['completed_at'])):
            raise ValueError('v2 actual prepared/completed worker proof differs')
        if packet is None:
            if ack['acknowledgement'] is not None or original['empty_queue_status'] not in ('empty','source_attestation_incomplete'):
                raise ValueError('v2 heartbeat cannot acknowledge a source delivery')
        elif (ack['acknowledgement']['worker_receipt_sha256']!=digest(values['worker-result.json'])
                or ack['acknowledgement']['delivery_id']!=expected['source_id'] or ack['acknowledgement']['role']!=self.manifest['role']):
            raise ValueError('v2 source result acknowledgement differs')
        return complete

    def _row(self,row):
        sequence,previous,head,raw_bytes,compressed_sha,payload,archive_previous,archive_sha=row
        if (digest(payload)!=compressed_sha or archive_sha!=_archive_hash(sequence,previous,head,raw_bytes,compressed_sha,archive_previous)):
            raise ValueError('v2 compressed archive commitment differs')
        values=_decode(payload,raw_bytes,self.policy)
        if digest(values['complete.json'])!=head:raise ValueError('v2 uncompressed group head differs')
        return values

    def _read_row(self,db,sequence):
        bounds=db.execute('SELECT raw_bytes,length(payload) FROM groups WHERE seq=?',(sequence,)).fetchone()
        if (bounds is None or type(bounds[0]) is not int or not 0<=bounds[0]<=self.policy.maximum_group_bytes
                or not 0<bounds[1]<=self.policy.maximum_group_bytes+65536):raise ValueError('bounded stored v2 blob required')
        return db.execute('SELECT * FROM groups WHERE seq=?',(sequence,)).fetchone()

    def _scan(self):
        started=monotonic();self._static();now=stamp(self.clock())
        if now<stamp(self.manifest['registered_at']) or now<getattr(self,'last_clock',now):raise ValueError('v2 clock moved backwards')
        self.last_clock=now;db=self._db()
        try:
            db.execute('BEGIN')
            state=db.execute('SELECT seq,group_head,archive_head,worker_after FROM state WHERE id=1').fetchone()
            sequence,group_head,archive_head,worker_raw=state;worker_head=parse(worker_raw)
            if archive_head!=self.reference['archive_head_sha256']:raise ValueError('stale v2 archive checkpoint; explicit recovery required')
            if sequence:
                row=self._read_row(db,sequence)
                if row is None:raise ValueError('v2 committed archive head missing')
                values=self._row(row);completed=parse(values['complete.json'])
                if row[2]!=group_head or row[7]!=archive_head or completed['worker_after']!=worker_head:raise ValueError('v2 head/state commitment differs')
                if stamp(completed['completed_at'])>now:raise ValueError('v2 observation clock before committed group')
            elif (group_head!=self.reference['manifest_sha256'] or worker_head!=self.manifest['worker_initial_head']):raise ValueError('v2 initial state differs')
        finally:db.close()
        paths=list((self.root/'groups').iterdir())
        if len(paths)>1:raise ValueError('v2 permits only one bounded active group')
        if paths:
            path=paths[0]
            if path.resolve()!=path or not path.is_dir() or path.name!=f'{sequence+1:08d}':raise ValueError('v2 duplicate/unknown tail needs explicit recovery')
            if not (path/'complete.json').exists():raise ValueError('v2 incomplete worker application requires investigation')
            values=_files(path,self.policy);completed=self._validate(values,sequence+1,group_head,worker_head)
            sequence+=1;group_head=digest(values['complete.json']);worker_head=completed['worker_after']
            if stamp(completed['completed_at'])>now:raise ValueError('future v2 group completion')
        if sequence!=self.reference['sequence'] or group_head!=self.reference['head_sha256']:raise ValueError('stale v2 application checkpoint; explicit recovery required')
        if sequence>self.policy.maximum_groups:raise ValueError('v2 group budget exhausted')
        if monotonic()-started>self.policy.maximum_scan_seconds:raise ValueError('v2 head scan budget exhausted')
        self.sequence=sequence;self.head=group_head;self.worker_head=worker_head;self.bytes=(self.root/'archive.sqlite').stat().st_size
        return now

    def _reserve(self):
        if self.bytes+self.policy.maximum_group_bytes+512*1024>self.policy.maximum_bytes:raise ValueError('v2 archive byte reserve exhausted before worker')
        if shutil.disk_usage(self.root).free<self.policy.minimum_free_disk_mb*1024**2+3*self.policy.maximum_group_bytes:
            raise ValueError('v2 archive disk reserve preserved')

    def _archive_tail(self):
        paths=list((self.root/'groups').iterdir())
        if not paths:return
        path=paths[0];values=_files(path,self.policy);completed=parse(values['complete.json']);sequence=completed['sequence']
        payload=_encode(values,self.policy);raw_bytes=sum(map(len,values.values()));compressed_sha=digest(payload)
        # Verify exact losslessness before any source file is removed.
        if _decode(payload,raw_bytes,self.policy)!=values:raise ValueError('v2 lossless archive verification failed')
        db=self._db(write=True)
        try:
            with db:
                current=db.execute('SELECT seq,group_head,archive_head,worker_after FROM state WHERE id=1').fetchone()
                self._validate(values,current[0]+1,current[1],parse(current[3]))
                archive_sha=_archive_hash(sequence,current[1],digest(values['complete.json']),raw_bytes,compressed_sha,current[2])
                db.execute('INSERT INTO groups VALUES (?,?,?,?,?,?,?,?)',(sequence,current[1],digest(values['complete.json']),raw_bytes,compressed_sha,payload,current[2],archive_sha))
                db.execute('UPDATE state SET seq=?,group_head=?,archive_head=?,worker_after=? WHERE id=1',
                    (sequence,digest(values['complete.json']),archive_sha,canonical(completed['worker_after'])))
            if self._row(self._read_row(db,sequence))!=values:raise ValueError('v2 committed archive readback differs')
        finally:db.close()
        # The schema is new and explicitly permits replacing only its own raw
        # active group with an exact immutable copy, never source/worker evidence.
        if _files(path,self.policy)!=values:raise ValueError('v2 active group changed after archive commit')
        shutil.rmtree(path);_sync(self.root/'groups')
        self.reference=dict(self.reference,archive_head_sha256=archive_sha)
        self._scan()

    def apply(self,queue,worker):
        with self._dispatch():
            with self._lease():self._scan();self._reserve()
            result=super().apply(queue,worker)
            with self._lease():self._archive_tail()
            return dict(result,reference=dict(self.reference),receipt_storage='indexed-lossless-gzip-v2')

    def _stream(self,db,known=None):
        head=self.reference['manifest_sha256'];archive_head=head;worker=self.manifest['worker_initial_head'];count=0;last=None;started=monotonic()
        known_ok=known is None or known['sequence']==0 and known['head_sha256']==head and known['archive_head_sha256']==head
        for (sequence,) in db.execute('SELECT seq FROM groups ORDER BY seq'):
            count+=1;row=self._read_row(db,sequence);values=self._row(row);complete=self._validate(values,count,head,worker)
            if sequence!=count or row[1]!=head or row[6]!=archive_head:raise ValueError('v2 full archive chain differs')
            if last and stamp(complete['completed_at'])<stamp(parse(last['complete.json'])['completed_at']):raise ValueError('v2 archive completion clock moved backwards')
            head=row[2];archive_head=row[7];worker=complete['worker_after'];last=values
            if known is not None and count==known['sequence']:
                known_ok=head==known['head_sha256'] and archive_head==known['archive_head_sha256']
            if monotonic()-started>self.policy.maximum_audit_seconds:raise ValueError('v2 full archive audit budget exhausted')
        if not known_ok:raise ValueError('unknown v2 archive ancestor')
        return count,head,archive_head,worker,last

    def _recovery_worker(self,complete,worker_after,values=None):
        def forbidden(*a,**k):raise AssertionError('v2 archive recovery cannot execute a worker/provider')
        worker=CapturedPaperWorkerV2.resume(self.manifest['worker_identity']['root'],
            expected_registration_sha256=self.manifest['worker_identity']['registration_sha256'],market=forbidden,clock=self.clock)
        with capture_lease(worker.root,writer=True),worker._source._lease(writer=False):
            if (_worker_identity(worker)!=self.manifest['worker_identity'] or list(worker._head())!=worker_after
                    or _logical(worker._source,_active(worker._source),worker._cache)!=parse(worker_after[2])['after']):
                raise ValueError('v2 recovery worker state advanced or differs')
        known_queue=complete['queue_after'] if complete else self.manifest['initial_queue_reference']
        recovered=ReferenceDelivery.recover(known_queue,clock=self.clock)
        queue=ReferenceDelivery.open(recovered['reference'],clock=self.clock)
        if _queue_identity(queue)!=self.manifest['queue_identity']:raise ValueError('v2 recovery queue identity differs')
        with queue._lease():
            db=queue_connect(queue.path,queue.policy)
            try:
                anchor=db.execute('SELECT seq FROM events WHERE sha=?',(known_queue['head_sha256'],)).fetchone()
                if anchor is None and known_queue['head_sha256']!=queue.reference['manifest_sha256']:
                    raise ValueError('v2 original queue checkpoint ancestor missing')
                expected=db.execute('SELECT coalesce(max(batch_seq),0) FROM acks WHERE role=? AND event_seq<=?',
                    (self.manifest['role'],anchor[0] if anchor else 0)).fetchone()[0]
                cursor=db.execute('SELECT cursor,pending_seq,delivery_id FROM cursors WHERE role=?',(self.manifest['role'],)).fetchone()
                if cursor!=(expected,None,None):raise ValueError('v2 recovery role queue advanced outside completed application')
            finally:db.close()
        if complete:
            # Complete group already has its durable ack. No source cursor is
            # ever advanced here; verify the original receipt in the queue.
            saved=parse(values['ack.json'])['acknowledgement']
            if saved is not None:
                with queue._lease():
                    db=queue_connect(queue.path,queue.policy)
                    try:row=db.execute('SELECT payload FROM acks WHERE delivery_id=?',(complete['delivery_id'],)).fetchone()
                    finally:db.close()
                if row is None or parse(row[0])!=saved:raise ValueError('v2 completed group source ack is absent or differs')
            return queue
        if queue.receipt()['role_cursors'][self.manifest['role']]['cursor']!=0:raise ValueError('v2 queue advanced without a known completed group')
        return queue

    @classmethod
    def recover(cls,known_reference,*,clock=None):
        """Explicit one-completed-group archive recovery; never retry a tick.

        A raw group without complete.json remains unknown. A completed raw group,
        committed archive row or duplicate raw copy can be proved and finished.
        """
        obj=cls._load(known_reference,clock)
        with obj._dispatch(),obj._lease():
            obj._static();now=stamp(obj.clock())
            if now<stamp(obj.manifest['registered_at']):raise ValueError('v2 recovery before original registration')
            db=obj._db()
            try:
                db.execute('BEGIN');count,head,archive_head,worker,last=obj._stream(db,known_reference)
                stored=db.execute('SELECT seq,group_head,archive_head,worker_after FROM state WHERE id=1').fetchone()
                if stored!=(count,head,archive_head,canonical(worker)):raise ValueError('v2 archive projection differs from full prefix')
            finally:db.close()
            if count not in (known_reference['sequence'],known_reference['sequence']+1):raise ValueError('v2 one-completed-group recovery scope exceeded')
            paths=list((obj.root/'groups').iterdir())
            if len(paths)>1:raise ValueError('v2 unknown recovery tail')
            obj.reference=dict(obj.reference,sequence=count,head_sha256=head,archive_head_sha256=archive_head)
            complete=parse(last['complete.json']) if last else None
            if complete and stamp(complete['completed_at'])>now:raise ValueError('v2 recovery clock before completed worker effect')
            if paths:
                path=paths[0]
                if path.resolve()!=path or not path.is_dir() or not (path/'complete.json').exists():raise ValueError('v2 incomplete worker result remains blocked')
                values=_files(path,obj.policy)
                if stamp(parse(values['complete.json'])['completed_at'])>now:raise ValueError('v2 recovery clock before completed raw group')
                if path.name==f'{count:08d}' and count:
                    if values!=last:raise ValueError('v2 duplicate active/archive bytes differ')
                    queue=obj._recovery_worker(complete,worker,last)
                    shutil.rmtree(path);_sync(obj.root/'groups')
                elif path.name==f'{count+1:08d}' and count==known_reference['sequence']:
                    complete=obj._validate(values,count+1,head,worker);queue=obj._recovery_worker(complete,complete['worker_after'],values)
                    obj.reference=dict(obj.reference,sequence=count+1,head_sha256=digest(values['complete.json']))
                    obj._archive_tail()
                else:raise ValueError('v2 unknown completed recovery group')
            else:queue=obj._recovery_worker(complete,worker,last)
            obj._scan()
            return dict(status='known_completed_v2_archive_recovered',reference=dict(obj.reference),
                queue_reference=queue.receipt()['reference'],worker_execution_repeated=False,provider_calls=0,**FLAGS)

    def audit(self):
        with self._dispatch(),self._lease():
            self._static();now=stamp(self.clock())
            if now<stamp(self.manifest['registered_at']):raise ValueError('v2 inspection before registration')
            # Calendar first: inspection must not decode unfinished outcome payloads.
            if now<stamp(self.manifest['end']):
                db=self._db()
                try:state=db.execute('SELECT seq,group_head,archive_head FROM state WHERE id=1').fetchone()
                finally:db.close()
                if state!=(self.reference['sequence'],self.reference['head_sha256'],self.reference['archive_head_sha256']):
                    raise ValueError('v2 metadata checkpoint differs')
                return dict(reference=self.reference,completed_applications=state[0],archive_database_bytes=(self.root/'archive.sqlite').stat().st_size,
                    active_raw_groups=len(list((self.root/'groups').iterdir())),full_history_integrity_pass=False,
                    status='metadata_only_until_original_end',performance_hidden=True,**FLAGS)
            self._scan()
            output=dict(reference=self.reference,completed_applications=self.sequence,archive_database_bytes=self.bytes,
                active_raw_groups=len(list((self.root/'groups').iterdir())),full_history_integrity_pass=False,
                scope='v2_compressed_cash_receipts_not_worker_or_economic_qualification',**FLAGS)
            if list((self.root/'groups').iterdir()):raise ValueError('v2 completed tail must be archived before full audit')
            db=self._db()
            try:
                db.execute('BEGIN')
                count,head,archive_head,_,_=self._stream(db)
            finally:db.close()
            if count!=self.sequence or head!=self.head or archive_head!=self.reference['archive_head_sha256']:raise ValueError('v2 archive prefix incomplete')
            return dict(output,status='original_compressed_groups_replayed',performance_hidden=False,full_history_integrity_pass=True)

    @classmethod
    def audit_reference(cls,reference,*,clock=None):
        return cls._load(reference,clock).audit()

    def read_group(self,sequence):
        if type(sequence) is not int or sequence<1:raise ValueError('positive v2 group sequence required')
        if stamp(self.clock())<stamp(self.manifest['end']):raise ValueError('v2 group payload sealed until original end')
        if not self.audit()['full_history_integrity_pass']:raise ValueError('full v2 archive audit required')
        with self._dispatch(),self._lease():
            self._scan();db=self._db()
            try:
                db.execute('BEGIN');return self._row(self._read_row(db,sequence))
            finally:db.close()


_LOADED=_runtime()
