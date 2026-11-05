"""Checkpointed three-role cached-source paper coordinator in a NEW namespace.

Completed operations resume from exact external checkpoints. Unknown effects stay
pending. Explicit recovery can prove a completed tick without executing it again.
This bounded profile is not a long study, economic admission or live executor.
"""
from contextlib import contextmanager
from dataclasses import asdict,dataclass
from datetime import UTC,datetime,timedelta
import fcntl
import os
from pathlib import Path
import sqlite3
from time import monotonic,sleep

from cryptoforge.backend import resolve_backend
from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new
from cryptoforge.cash_entry_contract import FLAGS,freeze_cash_contract,load_cash_contract
from cryptoforge.cash_application_v2 import CashApplicationPolicyV2,SegmentedCashApplicationV2
from cryptoforge.cached_cash_application_v3 import CachedCashApplicationV3,runtime_hashes as application_runtime
from cryptoforge.cached_reference_reader_v2 import CachedReferenceReaderV2
from cryptoforge.reference_prefix_v2 import ReferencePrefixV2,PrefixPolicyV2
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy,audit_reference_ledger
from cryptoforge.reference_delivery import ReferenceDelivery,DeliveryPolicy,ROLES
from cryptoforge.reference_sources import PublicReferenceClient,INTERVAL_MS
from cryptoforge.paired_cash_rehearsal import BoundedPaperPublicClient,_resources,_worker_ref,_runtime as public_runtime,MINIMUM_MEMORY
from cryptoforge.paper_producer_v2 import register_kernel
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2,WorkerCapturePolicyV2,audit_worker_capture
from cryptoforge.paper_capture_v3 import SegmentedLifecycle,_lease as capture_lease
from cryptoforge.paper_capture_state_v2 import _logical,_active
from cryptoforge.evidence_segments import SegmentPolicy
from cryptoforge.native_paper_archive_v2 import NativeArchivePolicy
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_wallet_replay_v2 import ReplayPolicyV2
from cryptoforge.paper_worker_replay_v2 import register_worker_replay,audit_worker_replay
from cryptoforge.paper_valuation_capture import observe_valuation_market

SQL={
 'identity':'CREATE TABLE identity (pin TEXT NOT NULL)',
 'events':'CREATE TABLE events (seq INTEGER PRIMARY KEY,at TEXT NOT NULL,phase TEXT NOT NULL,operation TEXT NOT NULL,payload BLOB NOT NULL,previous TEXT NOT NULL,sha TEXT UNIQUE NOT NULL)',
 'state':'CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1),seq INTEGER NOT NULL,head TEXT NOT NULL,pending BLOB NOT NULL,components BLOB NOT NULL,progress BLOB NOT NULL)',
 'no_update':"CREATE TRIGGER no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable paired operations'); END",
 'no_delete':"CREATE TRIGGER no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable paired operations'); END",
}


@dataclass(frozen=True)
class PairedCoordinatorPolicy:
    maximum_journal_records:int=1024
    maximum_journal_bytes:int=64*1024**2
    maximum_record_bytes:int=65536
    maximum_audit_seconds:int=120
    maximum_run_seconds:int=600

    def __post_init__(self):
        limits=dict(maximum_journal_records=(32,4096),maximum_journal_bytes=(1024**2,256*1024**2),
            maximum_record_bytes=(8192,131072),maximum_audit_seconds=(1,600),maximum_run_seconds=(60,900))
        if any(type(v) is not int or not limits[k][0]<=v<=limits[k][1] for k,v in asdict(self).items()):
            raise ValueError('explicit bounded paired coordinator policy required')
        if self.maximum_journal_bytes%4096:raise ValueError('page-aligned paired journal required')


def runtime_hashes():
    value=dict(application_runtime(),**{'public:'+k:v for k,v in public_runtime().items()},
        paired_cached_coordinator=digest(Path(__file__).read_bytes()),
        paired_cached_coordinator_cli=digest((Path(__file__).resolve().parents[2]/'scripts/coordinate_cached_paper.py').read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded cached coordinator runtime changed')
    return value


def _us(value):
    delta=stamp(value)-datetime(1970,1,1,tzinfo=UTC)
    return (delta.days*86400+delta.seconds)*1000000+delta.microseconds


def _event(seq,at,phase,operation,payload,previous):
    return digest(canonical(dict(sequence=seq,at=at,phase=phase,operation=operation,payload=payload,previous_sha256=previous)))


def _copy(value):return parse(canonical(value))


class PairedCachedCoordinator:
    @classmethod
    def create(cls,root,*,start,end,rules,configs,worker_policy,closeout_seconds,backend_env,policy=None,clock=None,market=None):
        clock=clock or (lambda:datetime.now(UTC));now=stamp(clock());start=stamp(start);end=stamp(end);duration=_us(end)-_us(start)
        policy=policy or PairedCoordinatorPolicy();slots=(duration+4999999)//5000000
        required_records=2*(3*((duration+299999999)//300000000+1)+3*slots+7)
        if (type(policy) is not PairedCoordinatorPolicy or resolve_backend(backend_env).name!='local'
                or not now<start or not 20000000<=duration<=300000000 or (start-now).total_seconds()>60
                or set(configs)!=set(ROLES) or worker_policy.get('exits',{}).get('shared_exit_signal') is not False
                or required_records>policy.maximum_journal_records
                or required_records*(policy.maximum_record_bytes+512)+512*1024>policy.maximum_journal_bytes):
            raise ValueError('new bounded prospective local paired coordinator profile required')
        measured=_resources(root);root=_new_root(root);(root/'writer.lock').touch(mode=0o600);(root/'results').mkdir(mode=0o700)
        public=BoundedPaperPublicClient();market=market or (lambda pair:observe_valuation_market(public,pair))
        source=ReferenceLedger.create(root/'source',start=start,end=end,clock=clock,
            policy=ReferencePolicy(maximum_database_bytes=16*1024**2,maximum_events=200,maximum_versions=2000,maximum_forecasts=1))
        source_ref=source.receipt()['reference']
        queue=ReferenceDelivery.create(root/'delivery',source_ref,clock=clock,
            policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_scratch_database_bytes=32*1024**2,
                maximum_events=200,maximum_source_events=200,maximum_batches=20,maximum_source_events_per_batch=4))
        prefix=ReferencePrefixV2.create(root/'prefix',source_ref,clock=clock,
            policy=PrefixPolicyV2(maximum_database_bytes=32*1024**2))
        reader=CachedReferenceReaderV2.create(root/'reader',queue,prefix,clock=clock)
        cash=freeze_cash_contract(root/'cash-contract',queue,rules=rules,closeout_seconds=closeout_seconds,clock=clock)
        contract=load_cash_contract(cash);apps={};workers={};replays={};groups=slots+2
        lifecycle=SegmentedLifecycle(poll_seconds=5,maximum_operations_per_poll=1,estimated_bytes_per_operation=8192,
            maximum_mark_gap_seconds=10,maximum_endpoint_gap_seconds=20,minimum_known_time_fraction='.9',
            closeout_seconds=closeout_seconds,finalization_grace_seconds=30,maximum_operation_wall_seconds=5,
            maximum_storage_bytes=64*1024**2,minimum_free_disk_bytes=2048*1024**2,minimum_available_memory_bytes=MINIMUM_MEMORY)
        storage=SegmentPolicy(maximum_events=8192,maximum_segments=128,maximum_segment_events=256,maximum_segment_bytes=2*1024**2,
            maximum_record_bytes=32768,maximum_total_bytes=16*1024**2)
        native=NativeArchivePolicy(shards=4,maximum_shard_bytes=2*1024**2,maximum_active_bytes=1024**2,maximum_active_rows=64,
            maximum_records=10000,maximum_row_bytes=16384,maximum_batch_bytes=65536,maximum_total_bytes=32*1024**2,
            minimum_free_disk_bytes=2048*1024**2,minimum_available_memory_bytes=MINIMUM_MEMORY)
        capture=WorkerCapturePolicyV2(maximum_predictions_per_tick=2,maximum_actions_per_tick=24,
            maximum_clock_calls_per_tick=64,maximum_market_requests_per_tick=2,maximum_exit_requests_per_tick=2)
        replay_policy=ReplayPolicyV2(maximum_scratch_bytes=16*1024**2,maximum_state_rows=10000,maximum_active_rows=128,
            maximum_active_bytes=1024**2,maximum_wall_seconds=30,minimum_available_memory_bytes=MINIMUM_MEMORY,minimum_free_disk_bytes=2048*1024**2)
        for role in ROLES:
            config=configs[role] if type(configs[role]) is PaperConfig else PaperConfig(**configs[role])
            kernel=register_kernel(root/('kernel-'+role),candidate_sha=contract['strategies'][role],study_protocol_sha256=cash['contract_sha256'],
                role=role,config=config,worker_policy=worker_policy,start=start,end=end,closeout_seconds=closeout_seconds,backend_env=backend_env,clock=clock)
            worker=CapturedPaperWorkerV2.create(root/('worker-'+role),kernel_root=kernel['root'],expected_kernel_contract_sha256=kernel['contract_sha256'],
                expected_kernel_registration_sha256=kernel['registration_sha256'],lifecycle=lifecycle,storage_policy=storage,native_policy=native,
                capture_policy=capture,market=market,clock=clock)
            app=CachedCashApplicationV3.create(root/('application-'+role),cash,queue,worker,reader,clock=clock,
                policy=CashApplicationPolicyV2(maximum_groups=groups,maximum_bytes=groups*2*1024**2))
            apps[role]=app.reference;workers[role]=_worker_ref(worker)
            replays[role]=register_worker_replay(root/('replay-'+role),capture_root=worker.root,expected_registration_sha256=worker.registration_sha256,
                policy=replay_policy,backend_env=backend_env,clock=clock)
        components=dict(source=source_ref,queue=queue.receipt()['reference'],prefix=prefix.reference,applications=apps)
        progress=dict(source_anchor=None,source_work=None,market_pause_until=None,role_slots={r:-1 for r in ROLES},ticks={r:0 for r in ROLES},
            missed_slots={r:0 for r in ROLES},seals={},replays={},proof=None,done=False)
        manifest=dict(schema_version='checkpointed-cached-paired-coordinator-v1',root=str(root),registered_at=now.isoformat(),
            start=start.isoformat(),end=end.isoformat(),policy=asdict(policy),runtime=runtime_hashes(),initial_components=components,
            initial_progress=progress,workers=workers,replays=replays,reader_reference=reader.reference,cash_contract_reference=cash,
            required_journal_records_envelope=required_records,registration_resources=measured,
            scope='bounded_20_to_300_second_paper_coordination_not_long_study_or_live_admission',**FLAGS)
        pin=_write_new(root/'manifest.json',manifest);db=sqlite3.connect(root/'journal.sqlite')
        try:
            db.execute('PRAGMA page_size=4096');db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
            for statement in SQL.values():db.execute(statement)
            with db:
                db.execute('INSERT INTO identity VALUES (?)',(pin,))
                db.execute('INSERT INTO state VALUES (1,0,?,?,?,?)',(pin,canonical(None),canonical(components),canonical(progress)))
        finally:db.close()
        (root/'journal.sqlite').chmod(0o600);at=stamp(clock())
        if not now<=at<start:raise ValueError('paired coordinator setup missed original start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=at.isoformat()))
        if not at<=stamp(clock())<start:
            (root/'registered.json').unlink();raise ValueError('paired coordinator durable setup missed start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,sequence=0,head_sha256=pin),clock=clock)

    @classmethod
    def _load(cls,reference,clock=None):
        if (type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','sequence','head_sha256'}
                or type(reference['sequence']) is not int or reference['sequence']<0):raise ValueError('exact paired external checkpoint required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        value=parse(raw);registered=parse(ready)
        if (root.resolve()!=root or root.stat().st_uid!=os.getuid() or value['root']!=str(root) or raw!=canonical(value)
                or digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
                or registered['manifest_sha256']!=reference['manifest_sha256'] or value['schema_version']!='checkpointed-cached-paired-coordinator-v1'
                or value['runtime']!=runtime_hashes() or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])<stamp(value['end'])
                or any(value[k] is not False for k in FLAGS)):raise ValueError('original paired coordinator registration differs')
        obj=cls();obj.root=root;obj.reference=dict(reference);obj.manifest=value;obj.clock=clock or (lambda:datetime.now(UTC))
        obj.policy=PairedCoordinatorPolicy(**value['policy']);obj._static();return obj

    @classmethod
    def open(cls,reference,*,clock=None):
        obj=cls._load(reference,clock)
        with obj._lease():obj._scan()
        return obj

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock',maximum=0);fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _static(self):
        names={'manifest.json','registered.json','writer.lock','journal.sqlite','results','source','delivery','prefix','reader','cash-contract'}
        names|={p+r for p in ('kernel-','worker-','application-','replay-') for r in ROLES}
        if (self.root.resolve()!=self.root or self.manifest['root']!=str(self.root) or self.reference['root']!=str(self.root)
                or {p.name for p in self.root.iterdir()}!=names or (self.root/'results').resolve()!=self.root/'results'
                or parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest
                or digest(read_file(self.root/'manifest.json',maximum=131072))!=self.reference['manifest_sha256']
                or digest(read_file(self.root/'registered.json',maximum=4096))!=self.reference['registration_sha256']
                or PairedCoordinatorPolicy(**self.manifest['policy'])!=self.policy or self.manifest['runtime']!=runtime_hashes()):
            raise ValueError('paired coordinator metadata/runtime/inventory changed')
        allowed={'final-proof.json'}|{'replay-'+r+'.json' for r in ROLES}
        if any(p.name not in allowed or p.is_symlink() for p in (self.root/'results').iterdir()):raise ValueError('paired result inventory differs')

    def _db(self,write=False):
        path=self.root/'journal.sqlite';info=path.lstat()
        if path.resolve()!=path or not path.is_file() or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_size>self.policy.maximum_journal_bytes:
            raise ValueError('original bounded paired journal required')
        if any(Path(str(path)+s).exists() for s in ('-journal','-wal','-shm')):raise ValueError('paired hot journal requires investigation')
        db=sqlite3.connect(path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=1)
        try:
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA cache_size=-128')
            if write:db.execute(f'PRAGMA max_page_count={self.policy.maximum_journal_bytes//4096}');db.execute('PRAGMA synchronous=FULL')
            else:db.execute('PRAGMA query_only=ON')
            if (db.execute('PRAGMA journal_mode').fetchone()[0]!='delete' or db.execute('PRAGMA page_size').fetchone()[0]!=4096
                    or dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))!=SQL
                    or db.execute('SELECT pin FROM identity').fetchall()!=[(self.reference['manifest_sha256'],)]):raise ValueError('paired journal schema differs')
            return db
        except BaseException:db.close();raise

    def _row(self,db,seq):
        size=db.execute('SELECT length(payload) FROM events WHERE seq=?',(seq,)).fetchone()
        if size is None or not 0<size[0]<=self.policy.maximum_record_bytes:raise ValueError('bounded paired operation payload required')
        row=db.execute('SELECT * FROM events WHERE seq=?',(seq,)).fetchone();n,at,phase,op,raw,previous,head=row;payload=parse(raw)
        if raw!=canonical(payload) or head!=_event(n,at,phase,op,payload,previous):raise ValueError('paired operation commitment differs')
        return row,payload

    def _components(self,value):
        original=self.manifest['initial_components']
        if set(value)!=set(original) or set(value['applications'])!=set(ROLES):raise ValueError('paired component set differs')
        for key in ('source','queue','prefix'):
            ref=value[key];initial=original[key]
            if set(ref)!=set(initial) or any(ref[k]!=initial[k] for k in ('root','manifest_sha256','registration_sha256')):
                raise ValueError('paired component identity differs')
            for k in set(ref)-{'root'}:sha(ref[k])
        for role in ROLES:
            ref=value['applications'][role];initial=original['applications'][role]
            if set(ref)!=set(initial) or any(ref[k]!=initial[k] for k in ('root','manifest_sha256','registration_sha256')):
                raise ValueError('paired role application identity differs')
            child=ref['application_reference'];start=initial['application_reference']
            if (set(child)!=set(start) or any(child[k]!=start[k] for k in ('root','manifest_sha256','registration_sha256'))
                    or type(child['sequence']) is not int or child['sequence']<0):raise ValueError('paired role archive checkpoint differs')
            for k in set(child)-{'root','sequence'}:sha(child[k])

    def _scan(self):
        self._static();now=stamp(self.clock());db=self._db()
        try:
            db.execute('BEGIN')
            sizes=db.execute('SELECT length(pending),length(components),length(progress) FROM state WHERE id=1').fetchone()
            if sizes is None or any(not 0<n<=self.policy.maximum_record_bytes for n in sizes):raise ValueError('bounded paired projection required')
            row=db.execute('SELECT seq,head,pending,components,progress FROM state WHERE id=1').fetchone()
            seq,head,pending_raw,components_raw,progress_raw=row
            if any(len(v)>self.policy.maximum_record_bytes for v in (pending_raw,components_raw,progress_raw)):raise ValueError('bounded paired projection required')
            pending,components,progress=map(parse,(pending_raw,components_raw,progress_raw));self._components(components)
            if seq!=self.reference['sequence'] or head!=self.reference['head_sha256']:raise ValueError('stale paired checkpoint; explicit recovery required')
            last_at=stamp(self.manifest['registered_at'])
            if seq:
                last,payload=self._row(db,seq);last_at=stamp(last[1])
                if last[2] not in ('prepared','completed'):raise ValueError('paired journal phase differs')
                if last[6]!=head or payload['state_sha256']!=digest(components_raw) or payload['progress_sha256']!=digest(progress_raw):
                    raise ValueError('paired head/projection commitment differs')
                if (last[2]=='prepared')!=(pending is not None):raise ValueError('paired pending operation differs')
                if pending is not None and pending!=dict(sequence=seq,operation=last[3],at=last[1],args=payload['args']):raise ValueError('paired preparation differs')
            elif (head!=self.reference['manifest_sha256'] or pending is not None or components!=self.manifest['initial_components'] or progress!=self.manifest['initial_progress']):
                raise ValueError('paired initial state differs')
            if seq>self.policy.maximum_journal_records or now<last_at or now<getattr(self,'last_clock',now):raise ValueError('paired clock/journal budget differs')
        finally:db.close()
        self.last_clock=now;self.pending=pending;self.components=components;self.progress=progress;return now

    def _transition(self,components,progress,op,args,result,prepared_at):
        state=_copy(components);next_progress=_copy(progress);now=stamp(prepared_at);start=stamp(self.manifest['start']);end=stamp(self.manifest['end'])
        if op in ('source_poll','prefix_ingest','queue_ingest','tick'):
            if not start<=now<end:raise ValueError('paired mutating operation outside original window')
        elif now<end:raise ValueError('paired finalization/replay before original end')
        if op=='source_poll':
            if set(args)!={'anchor'} or type(args['anchor']) is not int or args['anchor']!=_us(now)//300000000 or progress['source_work'] is not None:
                raise ValueError('paired original poll schedule differs')
            if progress['source_anchor'] is not None and args['anchor']<=progress['source_anchor']:raise ValueError('paired source anchor moved backwards')
            state['source']=result['reference'];next_progress.update(source_anchor=args['anchor'],source_work='prefix')
        elif op=='prefix_ingest':
            if args or progress['source_work']!='prefix':raise ValueError('paired prefix phase differs')
            state['prefix']=result['reference'];next_progress['source_work']='queue'
        elif op=='queue_ingest':
            if args or progress['source_work']!='queue':raise ValueError('paired queue phase differs')
            state['queue']=result['reference'];next_progress['source_work']=None
        elif op=='tick':
            role=args['role'];slot=args['slot'];old=components['applications'][role]['application_reference']
            actual_slot=(_us(result['worker_started_at'])-_us(start))//5000000
            if (set(args)!={'role','slot'} or role not in ROLES or type(slot) is not int or slot<0 or slot<=progress['role_slots'][role]
                    or slot!=(_us(now)-_us(start))//5000000 or progress['source_work'] is not None
                    or not now<=stamp(result['worker_started_at'])<end or actual_slot<slot
                    or stamp(result['worker_completed_at'])<stamp(result['worker_started_at'])
                    or result['reference']['application_reference']['sequence']!=old['sequence']+1):raise ValueError('paired original role slot/result differs')
            state['applications'][role]=result['reference'];state['queue']=result['queue_reference']
            next_progress['missed_slots'][role]+=actual_slot-progress['role_slots'][role]-1
            next_progress['role_slots'][role]=actual_slot;next_progress['ticks'][role]+=1
            next_progress['market_pause_until']=result['market_pause_until']
        elif op=='finalize':
            role=args['role']
            if set(args)!={'role'} or role not in ROLES or role in progress['seals'] or progress['source_work'] is not None:raise ValueError('paired finalization phase differs')
            next_progress['seals'][role]=result['seal'];next_progress['market_pause_until']=result['market_pause_until']
        elif op=='replay':
            role=args['role']
            if set(args)!={'role'} or role not in progress['seals'] or role in progress['replays']:raise ValueError('paired replay phase differs')
            next_progress['replays'][role]=result
        elif op=='proof':
            if args or set(progress['replays'])!=set(ROLES) or progress['proof'] is not None:raise ValueError('paired proof phase differs')
            next_progress.update(proof=result,done=True)
        else:raise ValueError('unknown paired operation')
        self._components(state);return state,next_progress

    def _append(self,phase,op,args=None,result=None,recovery=None):
        now=self._scan();seq=self.reference['sequence']+1
        if phase=='prepared':
            if self.pending is not None:raise ValueError('unknown pending paired effect cannot be retried')
            args=dict(args)
            if op in ('source_poll','prefix_ingest','queue_ingest','tick') and not stamp(self.manifest['start'])<=now<stamp(self.manifest['end']):
                raise ValueError('paired operation preparation outside original window')
            if op not in ('source_poll','prefix_ingest','queue_ingest','tick') and now<stamp(self.manifest['end']):
                raise ValueError('paired final preparation before original end')
            if op=='tick':args['slot']=(_us(now)-_us(self.manifest['start']))//5000000
            if op=='source_poll':args['anchor']=_us(now)//300000000
            if seq+1>self.policy.maximum_journal_records or (self.root/'journal.sqlite').stat().st_size+2*self.policy.maximum_record_bytes+512*1024>self.policy.maximum_journal_bytes:
                raise ValueError('paired journal reserve exhausted before operation')
            components=self.components;progress=self.progress;pending=dict(sequence=seq,operation=op,at=now.isoformat(),args=args)
            payload=dict(args=args,state_sha256=digest(canonical(components)),progress_sha256=digest(canonical(progress)))
        else:
            if self.pending is None or op!=self.pending['operation']:raise ValueError('paired operation completion lacks original preparation')
            components,progress=self._transition(self.components,self.progress,op,self.pending['args'],result,self.pending['at']);pending=None
            payload=dict(prepared_sequence=self.pending['sequence'],result=result,state_sha256=digest(canonical(components)),progress_sha256=digest(canonical(progress)),recovery=recovery)
        raw=canonical(payload)
        if len(raw)>self.policy.maximum_record_bytes:raise ValueError('paired operation payload byte budget exhausted')
        head=_event(seq,now.isoformat(),phase,op,payload,self.reference['head_sha256']);db=self._db(write=True)
        try:
            with db:
                db.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?)',(seq,now.isoformat(),phase,op,raw,self.reference['head_sha256'],head))
                db.execute('UPDATE state SET seq=?,head=?,pending=?,components=?,progress=? WHERE id=1',
                    (seq,head,canonical(pending),canonical(components),canonical(progress)))
        finally:db.close()
        self.reference=dict(self.reference,sequence=seq,head_sha256=head);self._scan()

    def _context(self,market):
        state=self.components
        return dict(source=ReferenceLedger.open(state['source'],clock=self.clock),queue=ReferenceDelivery.open(state['queue'],clock=self.clock),
            prefix=ReferencePrefixV2.open(state['prefix'],clock=self.clock),
            applications={r:CachedCashApplicationV3.open(v,clock=self.clock) for r,v in state['applications'].items()},
            workers={r:CapturedPaperWorkerV2.resume(v['root'],expected_registration_sha256=v['registration_sha256'],market=market,clock=self.clock)
                for r,v in self.manifest['workers'].items() if r not in self.progress['seals']})

    def _next(self,now,context):
        if self.progress['done'] or now<stamp(self.manifest['start']):return None
        p=self.progress
        if now<stamp(self.manifest['end']):
            if p['source_work'] is not None:return ('prefix_ingest' if p['source_work']=='prefix' else 'queue_ingest',{})
            anchor=_us(now)//300000000
            if p['source_anchor']!=anchor:
                receipt=context['queue'].receipt()
                if all(v['cursor']==receipt['batches'] and v['pending_sequence'] is None for v in receipt['role_cursors'].values()):
                    return 'source_poll',dict(anchor=anchor)
            slot=(_us(now)-_us(self.manifest['start']))//5000000
            for role in ROLES:
                if p['role_slots'][role]<slot:return 'tick',dict(role=role,slot=slot)
            return None
        if p['source_work'] is not None:raise ValueError('source pipeline incomplete at original end; no silent completion')
        for role in ROLES:
            if role not in p['seals']:return 'finalize',dict(role=role)
        for role in ROLES:
            if role not in p['replays']:return 'replay',dict(role=role)
        return 'proof',{}

    def _result_file(self,name,value):
        raw=canonical(value)
        if len(raw)>512*1024:raise ValueError('paired proof output byte budget exhausted')
        pin=_write_new(self.root/'results'/name,value)
        return dict(name=name,sha256=pin,bytes=len(raw))

    def _call(self,op,args,context,client,market):
        if op=='source_poll':
            value=context['source'].poll(client)
            return dict(reference=value['reference'],events=value['events'],versions=value['versions'],reused=value['reused_original_observation'])
        if op=='prefix_ingest':return context['prefix'].ingest(self.components['source'])
        if op=='queue_ingest':
            value=context['queue'].ingest(self.components['source']);return dict(reference=value['reference'],batches=value['batches'])
        if op=='tick':
            app=context['applications'][args['role']]
            value=app.apply(context['queue'],context['workers'][args['role']],self.components['prefix'])
            result={k:value[k] for k in ('reference','queue_reference','status','opportunity_count','positive_decisions','worker_receipt_sha256')}
            db=app.application._db()
            try:raw=app.application._row(app.application._read_row(db,app.application.reference['sequence']))
            finally:db.close()
            worker_result=parse(raw['worker-result.json']);result.update(worker_started_at=worker_result['prepared_tick']['payload']['at'],
                worker_completed_at=worker_result['application_completed_at'])
            result['market_pause_until']=self._market_pause();return result
        if op=='finalize':
            worker=context['workers'][args['role']];quotes={};filters={}
            for pair in sorted({v['pair'] for v in worker._source.wallet.snapshot()['open_lots']}):quotes[pair],filters[pair]=market(pair)
            worker.mark_endpoint(quotes,filters);worker.terminate('completed');return dict(seal=worker.finalize(),market_pause_until=self._market_pause())
        if op=='replay':
            role=args['role'];worker=self.manifest['workers'][role];reg=self.manifest['replays'][role]
            value=audit_worker_replay(worker['root'],expected_registration_sha256=worker['registration_sha256'],expected_seal_sha256=self.progress['seals'][role]['seal_sha256'],
                replay_root=reg['root'],expected_replay_registration_sha256=reg['replay_registration_sha256'],scratch_parent=self.root.parent,clock=self.clock)
            return self._result_file('replay-'+role+'.json',value)
        if op=='proof':
            value=dict(source=audit_reference_ledger(self.components['source'],clock=self.clock),prefix=context['prefix'].audit(scratch_parent=self.root.parent),
                queue=context['queue'].audit(),applications={r:context['applications'][r].audit(context['queue']) for r in ROLES},**FLAGS)
            return self._result_file('final-proof.json',value)
        raise ValueError('unknown paired operation')

    def step(self,*,client=None,market=None,maximum_operations=1):
        if type(maximum_operations) is not int or not 1<=maximum_operations<=64:raise ValueError('bounded operation count required')
        client=client or PublicReferenceClient()
        with self._lease():
            now=self._scan()
            if self.pending is not None:raise ValueError('unknown pending paired effect cannot be retried')
            if now<stamp(self.manifest['start']) or self.progress['done']:return self._inspection()
            if market is None:
                if not hasattr(self,'public'):self.public=BoundedPaperPublicClient()
                pause=self.progress['market_pause_until']
                if pause is not None:
                    self.public.paused_until=max(self.public.paused_until,monotonic()+max(0,(stamp(pause)-now).total_seconds()))
                market=lambda pair:observe_valuation_market(self.public,pair)
            context=self._context(market)
            for _ in range(maximum_operations):
                now=self._scan();next_op=self._next(now,context)
                if next_op is None:break
                op,args=next_op;_resources(self.root);self._append('prepared',op,args=args)
                result=self._call(op,args,context,client,market);self._append('completed',op,result=result)
            return self._inspection()

    def _market_pause(self):
        pause=self.progress['market_pause_until']
        remaining=max(0,getattr(getattr(self,'public',None),'paused_until',0)-monotonic())
        if remaining:
            value=(stamp(self.clock())+timedelta(seconds=remaining+1)).isoformat()
            pause=max(pause,value) if pause is not None else value
        return pause

    def _inspection(self):
        return dict(reference=dict(self.reference),status='completed' if self.progress['done'] else 'pending' if self.pending else 'ready',
            pending_operation=self.pending['operation'] if self.pending else None,components=_copy(self.components),
            ticks_by_role=self.progress['ticks'],missed_slots_by_role=self.progress['missed_slots'],
            results=_copy(self.progress['replays']) if stamp(self.clock())>=stamp(self.manifest['end']) else {},
            proof=self.progress['proof'] if self.progress['done'] else None,performance_hidden=stamp(self.clock())<stamp(self.manifest['end']),**FLAGS)

    def inspect(self):
        with self._lease():self._scan();return self._inspection()

    def run(self,*,client=None,market=None,sleeper=None):
        sleeper=sleeper or sleep;deadline=monotonic()+self.policy.maximum_run_seconds
        while True:
            if monotonic()>deadline:raise ValueError('paired coordinator run wall budget exhausted')
            value=self.step(client=client,market=market,maximum_operations=64)
            if value['status']=='completed':return value
            now=stamp(self.clock())
            if now>=stamp(self.manifest['start']):
                slot=(_us(now)-_us(self.manifest['start']))//5000000
                if now>=stamp(self.manifest['end']) or self.progress['source_work'] is not None or any(v<slot for v in self.progress['role_slots'].values()):continue
            target=(stamp(self.manifest['start']) if now<stamp(self.manifest['start']) else
                min(stamp(self.manifest['end']),stamp(self.manifest['start'])+timedelta(seconds=5*((_us(now)-_us(self.manifest['start']))//5000000+1))))
            delay=max(0,(target-now).total_seconds())
            if delay:sleeper(min(5,delay))

    def _full(self,known_reference):
        self._static();db=self._db();started=monotonic();state=_copy(self.manifest['initial_components']);progress=_copy(self.manifest['initial_progress'])
        head=self.reference['manifest_sha256'];pending=None;last_at=stamp(self.manifest['registered_at']);count=0
        known=known_reference['sequence']==0 and known_reference['head_sha256']==head
        try:
            db.execute('BEGIN')
            for (seq,) in db.execute('SELECT seq FROM events ORDER BY seq'):
                count+=1;row,payload=self._row(db,seq);_,at,phase,op,_,previous,current=row
                if seq!=count or count>self.policy.maximum_journal_records or previous!=head or not last_at<=stamp(at)<=stamp(self.clock()):
                    raise ValueError('paired full journal sequence/clock/chain differs')
                if phase=='prepared':
                    if pending is not None:raise ValueError('paired journal contains overlapping effects')
                    pending=dict(sequence=seq,operation=op,at=at,args=payload['args'])
                elif phase=='completed':
                    if pending is None or pending['operation']!=op or payload['prepared_sequence']!=pending['sequence']:
                        raise ValueError('paired journal completion/preparation differs')
                    state,progress=self._transition(state,progress,op,pending['args'],payload['result'],pending['at']);pending=None
                else:raise ValueError('paired journal phase differs')
                if payload['state_sha256']!=digest(canonical(state)) or payload['progress_sha256']!=digest(canonical(progress)):
                    raise ValueError('paired journal transition/projection differs')
                head=current;last_at=stamp(at)
                if seq==known_reference['sequence']:known=head==known_reference['head_sha256']
                if monotonic()-started>self.policy.maximum_audit_seconds:raise ValueError('paired full journal audit budget exhausted')
            sizes=db.execute('SELECT length(pending),length(components),length(progress) FROM state WHERE id=1').fetchone()
            if sizes is None or any(not 0<n<=self.policy.maximum_record_bytes for n in sizes):raise ValueError('bounded paired projection required')
            stored=db.execute('SELECT seq,head,pending,components,progress FROM state WHERE id=1').fetchone()
            if stored!=(count,head,canonical(pending),canonical(state),canonical(progress)):raise ValueError('paired stored projection differs from full journal')
            if not known:raise ValueError('unknown paired external ancestor')
        finally:db.close()
        return dict(self.reference,sequence=count,head_sha256=head),pending,state,progress

    def _validate_components(self):
        state=self.components
        ReferenceLedger.open(state['source'],clock=self.clock);ReferencePrefixV2.open(state['prefix'],clock=self.clock)
        queue=ReferenceDelivery.open(state['queue'],clock=self.clock)
        def forbidden(*a,**k):raise AssertionError('paired reconciliation cannot execute a worker or provider')
        for role,reference in state['applications'].items():
            app=CachedCashApplicationV3.open(reference,clock=self.clock)
            if role in self.progress['seals']:
                worker=self.manifest['workers'][role]
                audit_worker_capture(worker['root'],expected_registration_sha256=worker['registration_sha256'],
                    expected_seal_sha256=self.progress['seals'][role]['seal_sha256'],clock=self.clock)
            else:
                worker=self.manifest['workers'][role]
                live=CapturedPaperWorkerV2.resume(worker['root'],expected_registration_sha256=worker['registration_sha256'],market=forbidden,clock=self.clock)
                with capture_lease(live.root,writer=True),live._source._lease(writer=False):
                    if (list(live._head())!=app.application.worker_head
                            or _logical(live._source,_active(live._source),live._cache)!=parse(app.application.worker_head[2])['after']):
                        raise ValueError('paired worker/native state advanced outside known operation')
        for result in [*self.progress['replays'].values(),*([self.progress['proof']] if self.progress['proof'] else [])]:
            raw=read_file(self.root/'results'/result['name'],maximum=512*1024)
            if len(raw)!=result['bytes'] or digest(raw)!=result['sha256']:raise ValueError('paired retained result bytes differ')
        return queue

    @classmethod
    def inspect_reference(cls,known_reference,*,clock=None):
        obj=cls._load(known_reference,clock)
        with obj._lease():
            current,pending,_,progress=obj._full(known_reference)
            return dict(known_reference=known_reference,observed_checkpoint=current,pending_operation=pending['operation'] if pending else None,
                ticks_by_role=progress['ticks'],missed_slots_by_role=progress['missed_slots'],completed=progress['done'],
                read_only=True,checkpoint_adopted=False,performance_hidden=stamp(obj.clock())<stamp(obj.manifest['end']),**FLAGS)

    @classmethod
    def recover(cls,known_reference,*,clock=None):
        obj=cls._load(known_reference,clock)
        with obj._lease():
            current,pending,_,_=obj._full(known_reference);obj.reference=current;obj._scan()
            if pending is None:
                obj._validate_components()
                return dict(reference=obj.reference,recovery='completed_journal_checkpoint_proved',worker_execution_repeated=False,provider_calls=0,**FLAGS)
            if pending['operation']!='tick':raise ValueError('unknown pending source/prefix/queue/finalization/replay effect remains blocked')
            role=pending['args']['role'];old=obj.components['applications'][role];old_child=old['application_reference']
            recovered=SegmentedCashApplicationV2.recover(old_child,clock=obj.clock);new_child=recovered['reference']
            if new_child['sequence']!=old_child['sequence']+1:raise ValueError('pending tick has no one durable completed worker result')
            new_parent=dict(old,application_reference=new_child);app=CachedCashApplicationV3.open(new_parent,clock=obj.clock)
            db=app.application._db()
            try:values=app.application._row(app.application._read_row(db,new_child['sequence']))
            finally:db.close()
            original=app._proof(values);result=parse(values['worker-result.json']);proof=original['cached_reader_proof']
            if (stamp(original['derived']['source_observed_at'])<stamp(pending['at'])
                    or original['packet'] is not None and proof['prefix_reference']!=obj.components['prefix']):
                raise ValueError('known completed tick does not match pending source preparation')
            prior_state=_copy(obj.components);obj.components['applications'][role]=new_parent;obj.components['queue']=recovered['queue_reference']
            obj._validate_components();obj.components=prior_state
            summary=dict(reference=new_parent,queue_reference=recovered['queue_reference'],
                status='actual_cached_worker_application_completed' if original['packet'] is not None else 'actual_cached_worker_heartbeat_completed',
                opportunity_count=len(original['derived']['decisions']),positive_decisions=sum(v['would_enter'] for v in original['derived']['decisions']),
                worker_receipt_sha256=digest(values['worker-result.json']),
                worker_started_at=result['prepared_tick']['payload']['at'],worker_completed_at=result['application_completed_at'],
                market_pause_until=(stamp(obj.clock())+timedelta(seconds=600)).isoformat())
            obj._append('completed','tick',result=summary,recovery=dict(mode='known_durable_worker_result',worker_completed_at=result['application_completed_at'],
                worker_execution_repeated=False,provider_calls=0,conservative_market_pause_seconds=600))
            return dict(reference=obj.reference,recovery='pending_completed_tick_proved',worker_execution_repeated=False,provider_calls=0,**FLAGS)

    def audit(self):
        with self._lease():
            self._scan()
            if stamp(self.clock())<stamp(self.manifest['end']):return dict(reference=self.reference,status='metadata_only_until_original_end',performance_hidden=True,full_journal_integrity_pass=False,**FLAGS)
            current,pending,_,_=self._full(self.reference)
            if pending is not None:raise ValueError('pending paired effect requires explicit reconciliation')
            self._validate_components()
            return dict(reference=current,full_journal_integrity_pass=True,procedure_completed=self.progress['done'],performance_hidden=False,**FLAGS)


_LOADED=runtime_hashes()
