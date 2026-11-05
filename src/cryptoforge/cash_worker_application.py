"""Durable queue -> exact cash rule -> frozen CapturedPaperWorkerV2 receipts.

One prospective role, one whole completed poll per application. Unknown partial
operations block automatic retry; this layer never adopts or repairs them.
"""
from contextlib import contextmanager
from dataclasses import asdict,dataclass
from datetime import UTC,datetime
from fractions import Fraction
import fcntl
import math
import os
from pathlib import Path
import shutil
from time import monotonic

from cryptoforge.cash_entry_contract import FLAGS,load_cash_contract,evaluate_cash_packet,_queue_identity,runtime_hashes as cash_runtime
from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2, runtime_hashes as worker_runtime
from cryptoforge.evidence_segments import _verified_frame
from cryptoforge.reference_delivery import ReferenceDelivery


@dataclass(frozen=True)
class CashApplicationPolicy:
    maximum_groups:int=128
    maximum_bytes:int=256*1024**2
    maximum_group_bytes:int=16*1024**2
    maximum_scan_seconds:int=15
    minimum_free_disk_mb:int=2048

    def __post_init__(self):
        if (any(type(v) is not int for v in asdict(self).values()) or not 1<=self.maximum_groups<=1024
                or not 1024**2<=self.maximum_group_bytes<=16*1024**2
                or not self.maximum_group_bytes<=self.maximum_bytes<=1024**3
                or not 1<=self.maximum_scan_seconds<=30 or self.minimum_free_disk_mb<2048):
            raise ValueError('bounded immutable cash application storage required')


def _current_runtime():
    return dict(cash_runtime(),**{'worker:'+k:v for k,v in worker_runtime().items()},
        cash_worker_application=digest(Path(__file__).read_bytes()))


def runtime_hashes():
    value=_current_runtime()
    if value!=_LOADED_RUNTIME:raise ValueError('cash application runtime changed; new process/namespace required')
    return value


def _pin(path):
    import hashlib
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):h.update(block)
    return h.hexdigest()


def _free_disk(path):return shutil.disk_usage(path).free


def _heartbeat(application_pin,at):
    return dict(decisions=[],predictions=[],source_observed_at=stamp(at).isoformat(),source_sha256=digest(canonical([])),
        source_id='cash-heartbeat:'+digest(canonical(dict(application=application_pin,at=stamp(at).isoformat()))))


def _worker_identity(worker):
    if type(worker) is not CapturedPaperWorkerV2:raise ValueError('actual frozen CapturedPaperWorkerV2 required')
    worker._verify()
    return dict(root=str(worker.root),registration_sha256=worker.registration_sha256,protocol_sha256=worker.protocol_sha256)


def _prepared_tick(worker,sequence):
    """Retain the actual bounded original prepared event, without sealing its log."""
    with worker.log._lease(writer=False):
        db=worker.log._db(writer=False)
        try:
            worker.log._validate_files(db,verify_hashes=False)
            row=db.execute('SELECT ordinal,first_seq,previous FROM segments WHERE first_seq<=? AND last_seq>=?',(sequence,sequence)).fetchone()
            if row is None:raise ValueError('original prepared worker event missing')
            number,prior=row[1],row[2]
            with worker.log._path(row[0]).open('rb') as stream:
                while True:
                    raw=stream.readline(worker.log.policy.maximum_record_bytes+1)
                    if not raw or len(raw)>worker.log.policy.maximum_record_bytes:raise ValueError('bounded original worker event required')
                    record=_verified_frame(raw,number,prior)
                    if number==sequence:return record
                    number+=1;prior=record['sha256']
        finally:db.close()


class CashWorkerApplication:
    @classmethod
    def create(cls,root,contract_reference,queue,worker,*,policy=None,clock=None):
        before=stamp((clock or (lambda:datetime.now(UTC)))());contract=load_cash_contract(contract_reference)
        identity=_worker_identity(worker);role=worker.protocol['role'];policy=policy or CashApplicationPolicy()
        if (type(queue) is not ReferenceDelivery or _queue_identity(queue)!=contract['queue_identity']
                or queue.manifest['mode']!='prospective' or queue.receipt()['events']
                or worker.protocol['candidate_sha256']!=contract['strategies'][role]
                or worker.protocol['study_protocol_sha256']!=contract_reference['contract_sha256']
                or any(worker.protocol[k]!=contract[k] for k in ('start','end'))
                or worker.protocol['plan']['entry_cutoff']!=contract['entry_cutoff']
                or not stamp(worker.registration['registered_at'])<=before<stamp(contract['start'])
                or worker._head()[1]!='genesis'):
            raise ValueError('empty original queue and prospective role worker/cash contract required')
        assumed=math.ceil((Fraction(worker.config.entry_fee)+Fraction(worker.config.exit_fee)+2*Fraction(worker.config.slippage))*10000)
        if contract['rules'][role]['round_trip_cost_bps']<assumed:
            raise ValueError('cash rule cost floor below frozen worker fee/slippage assumptions')
        root=_new_root(root,forbidden=(queue.root,worker.root,Path(contract_reference['root']),Path(queue.manifest['source_identity']['root'])))
        (root/'groups').mkdir(mode=0o700);(root/'writer.lock').touch(mode=0o600)
        value=dict(schema_version='cash-worker-application-v1',root=str(root),registered_at=before.isoformat(),
            contract_reference=contract_reference,queue_identity=_queue_identity(queue),worker_identity=identity,
            role=role,policy=asdict(policy),runtime=runtime_hashes(),worker_initial_head=list(worker._head()),
            start=contract['start'],end=contract['end'],assumed_worker_cost_floor_bps=assumed,**FLAGS)
        pin=_write_new(root/'manifest.json',value);at=stamp((clock or (lambda:datetime.now(UTC)))())
        if not before<=at<stamp(contract['start']):raise ValueError('cash application missed prospective start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=at.isoformat()))
        if not at<=stamp((clock or (lambda:datetime.now(UTC)))())<stamp(contract['start']):
            (root/'registered.json').unlink();_sync(root);raise ValueError('cash application durable completion missed start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,sequence=0,head_sha256=pin),clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None):
        if (type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','sequence','head_sha256'}
                or type(reference['sequence']) is not int or reference['sequence']<0):
            raise ValueError('original cash application external checkpoint required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        value=parse(raw);registered=parse(ready);contract=load_cash_contract(value['contract_reference'])
        if (root.resolve()!=root or root.stat().st_uid!=os.getuid() or value['root']!=str(root)
                or digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
                or value['schema_version']!='cash-worker-application-v1' or value['runtime']!=runtime_hashes()
                or registered['manifest_sha256']!=reference['manifest_sha256']
                or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])
                or any(value[k]!=contract[k] for k in ('start','end')) or any(value[k] is not False for k in FLAGS)):
            raise ValueError('original cash application contract/runtime differs')
        obj=cls();obj.root=root;obj.manifest=value;obj.contract=contract;obj.reference=dict(reference)
        obj.policy=CashApplicationPolicy(**value['policy']);obj.clock=clock or (lambda:datetime.now(UTC))
        with obj._lease():obj._scan()
        return obj

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock',maximum=0)
        fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _scan(self):
        started=monotonic();now=stamp(self.clock())
        if now<stamp(self.manifest['registered_at']) or now<getattr(self,'last_clock',now):raise ValueError('cash application clock moved backwards')
        self.last_clock=now
        if {p.name for p in self.root.iterdir()}!={'manifest.json','registered.json','writer.lock','groups'} or (self.root/'groups').is_symlink():
            raise ValueError('cash application inventory differs')
        for name,key in [('manifest.json','manifest_sha256'),('registered.json','registration_sha256')]:
            if _pin(self.root/name)!=self.reference[key]:raise ValueError('cash application static registration changed')
        if (parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest
                or load_cash_contract(self.manifest['contract_reference'])!=self.contract
                or CashApplicationPolicy(**self.manifest['policy'])!=self.policy):
            raise ValueError('in-memory cash contract/policy differs from original')
        if self.manifest['runtime']!=runtime_hashes():raise ValueError('cash application runtime changed')
        groups=sorted((self.root/'groups').iterdir());total=0;head=self.reference['manifest_sha256']
        last_worker=self.manifest['worker_initial_head'];last_time=stamp(self.manifest['registered_at'])
        if len(groups)>self.policy.maximum_groups:raise ValueError('cash application group budget exhausted')
        for index,path in enumerate(groups,1):
            if path.is_symlink() or not path.is_dir() or path.name!=f'{index:08d}':raise ValueError('original cash application sequence required')
            if not (path/'complete.json').exists():raise ValueError('incomplete cash application requires explicit investigation; no retry')
            completed=parse(read_file(path/'complete.json',maximum=65536));names={p.name for p in path.iterdir()}
            if (names!={'input.json','prepared.json','worker-result.json','ack.json','complete.json'}
                    or set(completed['files'])!=names-{'complete.json'}):raise ValueError('cash application group inventory differs')
            size=0
            for name in names:
                p=path/name;info=p.lstat()
                if p.is_symlink() or not p.is_file() or info.st_nlink!=1 or info.st_size>self.policy.maximum_group_bytes:raise ValueError('bounded original cash file required')
                size+=info.st_size
                if name!='complete.json' and completed['files'][name]!=dict(bytes=info.st_size,sha256=_pin(p)):
                    raise ValueError('cash application receipt/files differ')
            if (size>self.policy.maximum_group_bytes or completed['sequence']!=index or completed['previous_sha256']!=head
                    or not last_time<=stamp(completed['completed_at'])<=now):raise ValueError('cash application chain/clock/bytes differ')
            original=parse(read_file(path/'input.json',maximum=self.policy.maximum_group_bytes))
            prepared=parse(read_file(path/'prepared.json',maximum=65536))
            result=parse(read_file(path/'worker-result.json',maximum=512*1024));ack=parse(read_file(path/'ack.json',maximum=65536))
            packet=original['packet'];at=original['derived']['source_observed_at']
            expected=(evaluate_cash_packet(self.contract,self.manifest['contract_reference']['contract_sha256'],packet,self.manifest['role'],observed_at=at)
                if packet is not None else _heartbeat(self.reference['manifest_sha256'],at))
            event=result['prepared_tick'];after=result['worker_after'];terminal=parse(after[2])
            inputs={k:expected[k] for k in ('predictions','source_id','source_observed_at','source_sha256')}
            if (original['derived']!=expected or prepared['input_sha256']!=_pin(path/'input.json')
                    or result['input_sha256']!=prepared['input_sha256'] or result['worker_identity']!=self.manifest['worker_identity']
                    or prepared['worker_before']!=last_worker or result['worker_before']!=last_worker or completed['worker_after']!=after
                    or after[1]!='complete' or terminal['phase']!='tick' or terminal['prepared_seq']!=last_worker[0]+1
                    or terminal['result']!=result['result'] or event['kind']!='prepared' or event['payload']['inputs']!=inputs
                    or not stamp(at)<=stamp(event['payload']['at'])<=stamp(terminal['at'])<=stamp(result['application_completed_at'])<=stamp(completed['completed_at'])
                    or ack['reference']!=completed['queue_after'] or any(result[k] is not False for k in FLAGS)):
                raise ValueError('original cash derivation/application result linkage differs')
            _verified_frame(canonical(event)+b'\n',last_worker[0]+1,last_worker[4])
            _verified_frame(canonical(dict(sequence=after[0],kind=after[1],payload=terminal,previous_sha256=after[3],sha256=after[4]))+b'\n',after[0],after[3])
            if packet is None:
                if ack['acknowledgement'] is not None or original['empty_queue_status'] not in ('empty','source_attestation_incomplete'):
                    raise ValueError('heartbeat cannot acknowledge a source delivery')
            elif (ack['acknowledgement']['worker_receipt_sha256']!=_pin(path/'worker-result.json')
                    or ack['acknowledgement']['delivery_id']!=expected['source_id'] or ack['acknowledgement']['role']!=self.manifest['role']):
                raise ValueError('original cash worker receipt/acknowledgement differs')
            head=_pin(path/'complete.json');total+=size;last_worker=completed['worker_after'];last_time=stamp(completed['completed_at'])
            if total>self.policy.maximum_bytes or monotonic()-started>self.policy.maximum_scan_seconds:raise ValueError('cash application scan/total byte budget exhausted')
        if len(groups)!=self.reference['sequence'] or head!=sha(self.reference['head_sha256']):raise ValueError('stale cash checkpoint; explicit recovery required')
        self.sequence=len(groups);self.head=head;self.bytes=total;self.worker_head=last_worker
        return now

    def apply(self,queue,worker):
        with self._lease():
            now=self._scan()
            if (type(queue) is not ReferenceDelivery or _queue_identity(queue)!=self.manifest['queue_identity']
                    or _worker_identity(worker)!=self.manifest['worker_identity'] or list(worker._head())!=self.worker_head):
                raise ValueError('registered cash queue/worker head differs')
            if not stamp(self.manifest['start'])<=now<stamp(self.manifest['end']):raise ValueError('cash application outside frozen window')
            if self.sequence>=self.policy.maximum_groups or self.bytes+self.policy.maximum_group_bytes>self.policy.maximum_bytes:
                raise ValueError('cash application storage budget exhausted before next delivery')
            if _free_disk(self.root)<self.policy.minimum_free_disk_mb*1024**2+self.policy.maximum_group_bytes:
                raise ValueError('cash application disk reserve preserved')
            offered=queue.next(self.manifest['role'])
            packet=queue.read(self.manifest['role'],offered['delivery']['delivery_id']) if offered['delivery'] else None
            at=stamp(self.clock())
            if packet is None:
                # Worker cadence remains independent of 5m source polling. Empty
                # ticks execute pending intents, marks and exits with fresh I/O.
                # They create no strategy opportunities or queue acknowledgements.
                derived=_heartbeat(self.reference['manifest_sha256'],at)
            else:derived=evaluate_cash_packet(self.contract,self.manifest['contract_reference']['contract_sha256'],packet,self.manifest['role'],observed_at=at)
            input_value=dict(packet=packet,empty_queue_status=offered['status'] if packet is None else None,derived=derived);raw=canonical(input_value)
            if len(raw)+512*1024>self.policy.maximum_group_bytes:raise ValueError('bounded full cash input/result reserve required')
            worker_before=list(worker._head());folder=self.root/'groups'/f'{self.sequence+1:08d}';folder.mkdir(mode=0o700)
            _sync(self.root/'groups')
            input_pin=_write_new(folder/'input.json',input_value)
            _write_new(folder/'prepared.json',dict(at=at.isoformat(),input_sha256=input_pin,queue_before=offered['reference'],worker_before=worker_before))
            try:
                result=worker.tick(derived['predictions'],source_id=derived['source_id'],source_observed_at=stamp(derived['source_observed_at']),expected_source_sha256=derived['source_sha256'])
                after=list(worker._head());complete_event=parse(after[2]);prepared=_prepared_tick(worker,worker_before[0]+1)
                expected_inputs={k:derived[k] for k in ('predictions','source_id','source_observed_at','source_sha256')}
                if (after[0]<=worker_before[0] or after[1]!='complete' or complete_event['phase']!='tick'
                        or complete_event['prepared_seq']!=worker_before[0]+1 or complete_event['result']!=result
                        or prepared['kind']!='prepared' or prepared['previous_sha256']!=worker_before[4]
                        or prepared['payload']['phase']!='tick' or prepared['payload']['inputs']!=expected_inputs):
                    raise ValueError('actual prepared/completed worker cash application differs')
                worker_receipt=dict(schema_version='actual-captured-paper-worker-cash-result-v1',input_sha256=input_pin,
                    worker_identity=self.manifest['worker_identity'],worker_before=worker_before,worker_after=after,
                    prepared_tick=prepared,result=result,application_completed_at=stamp(self.clock()).isoformat(),**FLAGS)
                result_pin=_write_new(folder/'worker-result.json',worker_receipt)
            except BaseException as exc:
                _write_new(folder/'worker-error.json',dict(error_type=type(exc).__name__,worker_receipt_available=False));raise
            ack=(queue.acknowledge(self.manifest['role'],derived['source_id'],worker_receipt_sha256=result_pin) if packet is not None
                else dict(acknowledgement=None,reference=queue.receipt()['reference'],scope='heartbeat_no_source_delivery_acknowledged'))
            _write_new(folder/'ack.json',ack)
            files={p.name:dict(bytes=p.stat().st_size,sha256=_pin(p)) for p in folder.iterdir()}
            completed=dict(sequence=self.sequence+1,previous_sha256=self.head,completed_at=stamp(self.clock()).isoformat(),
                files=files,worker_after=after,delivery_id=derived['source_id'],queue_after=ack['reference'],**FLAGS)
            completion_pin=_write_new(folder/'complete.json',completed)
            if sum(p.stat().st_size for p in folder.iterdir())>self.policy.maximum_group_bytes:raise ValueError('completed cash group byte cap exceeded')
            self.reference=dict(self.reference,sequence=self.sequence+1,head_sha256=completion_pin);self._scan()
            return dict(status='actual_worker_application_completed' if packet is not None else 'actual_worker_heartbeat_completed',reference=self.reference,role=self.manifest['role'],
                opportunity_count=len(derived['decisions']),positive_decisions=sum(v['would_enter'] for v in derived['decisions']),
                worker_receipt_sha256=result_pin,worker_result=result,queue_reference=ack['reference'],**FLAGS)

    def audit(self):
        with self._lease():
            self._scan()
            return dict(reference=self.reference,completed_applications=self.sequence,bytes=self.bytes,
                role=self.manifest['role'],scope='cash_derivation_application_receipts_not_independent_worker_or_economic_replay',**FLAGS)


_LOADED_RUNTIME=_current_runtime()
