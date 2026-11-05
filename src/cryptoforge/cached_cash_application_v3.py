"""NEW registered cached-reader -> actual paper worker -> v2 receipt archive.

No old application is patched. Reader proof is committed in the original input
file and thus in the actual worker-result SHA acknowledged by the queue.
Unknown partial effects block; parent/whole-runner recovery is not supplied.
"""
from contextlib import contextmanager
from datetime import UTC,datetime
import fcntl
import os
from pathlib import Path
from time import monotonic

from cryptoforge.cash_application_v2 import SegmentedCashApplicationV2,_runtime as archive_runtime
from cryptoforge.cached_reference_reader_v2 import CachedReferenceReaderV2,runtime_hashes as reader_runtime
from cryptoforge.cash_worker_application import _worker_identity,_prepared_tick,_heartbeat,_pin
from cryptoforge.cash_entry_contract import FLAGS,evaluate_cash_packet,_queue_identity
from cryptoforge.reference_delivery import ReferenceDelivery,_connect,SourceReplay
from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync


def runtime_hashes():
    value=dict(archive_runtime(),**{'reader:'+k:v for k,v in reader_runtime().items()},
        cached_cash_application_v3=digest(Path(__file__).read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded cached cash application runtime changed')
    return value


class CachedCashApplicationV3:
    @classmethod
    def create(cls,root,contract_reference,queue,worker,reader,*,policy=None,clock=None):
        clock=clock or (lambda:datetime.now(UTC));now=stamp(clock())
        if type(reader) is not CachedReferenceReaderV2 or type(queue) is not ReferenceDelivery:
            raise ValueError('actual registered cached reader and original queue required')
        reader._check()
        if reader.manifest['queue_identity']!=_queue_identity(queue):raise ValueError('cached cash reader/queue identity differs')
        root=_new_root(root,forbidden=(queue.root,worker.root,reader.root,Path(contract_reference['root']),
            Path(reader.manifest['prefix_identity']['root']),Path(queue.manifest['source_identity']['root'])))
        (root/'writer.lock').touch(mode=0o600)
        app=SegmentedCashApplicationV2.create(root/'application',contract_reference,queue,worker,policy=policy,clock=clock)
        value=dict(schema_version='cached-cash-worker-application-v3',root=str(root),registered_at=now.isoformat(),
            application_initial_reference=app.reference,reader_reference=reader.reference,role=app.manifest['role'],
            start=app.manifest['start'],end=app.manifest['end'],runtime=runtime_hashes(),**FLAGS)
        pin=_write_new(root/'manifest.json',value);at=stamp(clock())
        if not now<=at<stamp(value['start']):raise ValueError('cached cash setup missed prospective start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=at.isoformat()))
        if not at<=stamp(clock())<stamp(value['start']):
            (root/'registered.json').unlink();_sync(root);raise ValueError('cached cash durable setup missed start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready,application_reference=app.reference),clock=clock)

    @classmethod
    def _load(cls,reference,clock):
        if type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','application_reference'}:
            raise ValueError('original cached cash external checkpoint required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        value=parse(raw);registered=parse(ready);initial=value['application_initial_reference'];current=reference['application_reference']
        if (root.resolve()!=root or value['root']!=str(root) or raw!=canonical(value) or digest(raw)!=sha(reference['manifest_sha256'])
                or digest(ready)!=sha(reference['registration_sha256']) or registered['manifest_sha256']!=reference['manifest_sha256']
                or value['schema_version']!='cached-cash-worker-application-v3' or value['runtime']!=runtime_hashes()
                or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])
                or initial['root']!=str(root/'application') or any(current[k]!=initial[k] for k in ('root','manifest_sha256','registration_sha256'))
                or any(value[k] is not False for k in FLAGS)):
            raise ValueError('original cached cash registration/runtime differs')
        obj=cls();obj.root=root;obj.reference=dict(reference);obj.manifest=value;obj.clock=clock or (lambda:datetime.now(UTC))
        obj.reader=CachedReferenceReaderV2.open(value['reader_reference'],clock=obj.clock);obj._static();return obj

    @classmethod
    def open(cls,reference,*,clock=None):
        obj=cls._load(reference,clock);obj.application=SegmentedCashApplicationV2.open(reference['application_reference'],clock=obj.clock)
        with obj._lease():obj._check();obj._head_proof()
        return obj

    @contextmanager
    def _lease(self):
        read_file(self.root/'writer.lock',maximum=0);fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
        finally:os.close(fd)

    def _static(self):
        if (self.root.resolve()!=self.root or self.manifest['root']!=str(self.root) or self.reference['root']!=str(self.root)
                or {p.name for p in self.root.iterdir()}!={'manifest.json','registered.json','writer.lock','application'}
                or digest(read_file(self.root/'manifest.json',maximum=131072))!=self.reference['manifest_sha256']
                or digest(read_file(self.root/'registered.json',maximum=4096))!=self.reference['registration_sha256']
                or parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest or self.manifest['runtime']!=runtime_hashes()):
            raise ValueError('cached cash original metadata/runtime differs')
        self.reader._check()
        if self.reader.reference!=self.manifest['reader_reference']:raise ValueError('cached cash reader registration changed')

    def _check(self):
        self._static();app=self.application
        if (app.reference!=self.reference['application_reference'] or app.manifest['role']!=self.manifest['role']
                or any(app.manifest[k]!=self.manifest[k] for k in ('start','end'))
                or app.manifest['queue_identity']!=self.reader.manifest['queue_identity']):raise ValueError('cached cash application binding differs')

    def _proof(self,values):
        value=parse(values['input.json']);proof=value['cached_reader_proof'];packet=value['packet']
        if proof['application_manifest_sha256']!=self.reference['manifest_sha256'] or proof['reader_reference']!=self.manifest['reader_reference']:
            raise ValueError('cached cash input parent/reader proof differs')
        if packet is None:
            if proof!={'application_manifest_sha256':self.reference['manifest_sha256'],'reader_reference':self.manifest['reader_reference'],
                    'scope':'heartbeat_no_cached_packet'}:raise ValueError('cached cash heartbeat proof differs')
        else:
            prefix=proof['prefix_reference'];expected=self.reader.manifest['prefix_identity']
            if (proof['packet_sha256']!=digest(canonical(packet)) or any(prefix[k]!=expected[k] for k in ('root','manifest_sha256','registration_sha256'))
                    or proof['source_semantic_prefix_replayed'] is not False or proof['scope']!='read_only_cached_packet_binding_not_worker_execution'
                    or any(proof[k] is not False for k in FLAGS)):
                raise ValueError('cached cash original packet proof differs')
        return value

    def _head_proof(self):
        app=self.application
        if app.reference['sequence']:
            db=app._db()
            try:self._proof(app._row(app._read_row(db,app.reference['sequence'])))
            finally:db.close()

    def apply(self,queue,worker,prefix_reference):
        with self._lease():
            self._check();app=self.application
            with app._dispatch(),app._lease():
                now=app._scan();app._reserve();self._head_proof()
                if (type(queue) is not ReferenceDelivery or _queue_identity(queue)!=app.manifest['queue_identity']
                        or _worker_identity(worker)!=app.manifest['worker_identity'] or list(worker._head())!=app.worker_head):
                    raise ValueError('cached cash actual queue/worker head differs')
                if not stamp(app.manifest['start'])<=now<stamp(app.manifest['end']):raise ValueError('cached cash outside frozen window')
                if app.sequence>=app.policy.maximum_groups:raise ValueError('cached cash group budget exhausted before offer')
                offered=queue.next(app.manifest['role']);packet=None
                proof=dict(application_manifest_sha256=self.reference['manifest_sha256'],reader_reference=self.reader.reference,scope='heartbeat_no_cached_packet')
                if offered['delivery']:
                    read=self.reader.read(queue,prefix_reference,app.manifest['role'],offered['delivery']['delivery_id'])
                    packet=read.pop('packet');proof=dict(read,application_manifest_sha256=self.reference['manifest_sha256'])
                at=stamp(self.clock())
                if not stamp(app.manifest['start'])<=at<stamp(app.manifest['end']):raise ValueError('cached cash input completed outside frozen window')
                derived=(_heartbeat(app.reference['manifest_sha256'],at) if packet is None else
                    evaluate_cash_packet(app.contract,app.manifest['contract_reference']['contract_sha256'],packet,app.manifest['role'],observed_at=at))
                original=dict(packet=packet,empty_queue_status=offered['status'] if packet is None else None,derived=derived,cached_reader_proof=proof)
                if len(canonical(original))+512*1024>app.policy.maximum_group_bytes:raise ValueError('bounded cached cash input/result reserve required')
                before=list(worker._head());folder=app.root/'groups'/f'{app.sequence+1:08d}';folder.mkdir(mode=0o700);_sync(app.root/'groups')
                input_pin=_write_new(folder/'input.json',original)
                _write_new(folder/'prepared.json',dict(at=at.isoformat(),input_sha256=input_pin,queue_before=offered['reference'],worker_before=before))
                try:
                    result=worker.tick(derived['predictions'],source_id=derived['source_id'],source_observed_at=stamp(derived['source_observed_at']),expected_source_sha256=derived['source_sha256'])
                    after=list(worker._head());terminal=parse(after[2]);prepared=_prepared_tick(worker,before[0]+1)
                    if (after[0]<=before[0] or after[1]!='complete' or terminal['phase']!='tick' or terminal['prepared_seq']!=before[0]+1
                            or terminal['result']!=result or prepared['kind']!='prepared' or prepared['previous_sha256']!=before[4]
                            or prepared['payload']['phase']!='tick' or prepared['payload']['inputs']!={k:derived[k] for k in ('predictions','source_id','source_observed_at','source_sha256')}):
                        raise ValueError('cached cash actual worker prepared/completed differs')
                    receipt=dict(schema_version='actual-captured-paper-worker-cash-result-v1',input_sha256=input_pin,
                        worker_identity=app.manifest['worker_identity'],worker_before=before,worker_after=after,prepared_tick=prepared,result=result,
                        application_completed_at=stamp(self.clock()).isoformat(),**FLAGS)
                    result_pin=_write_new(folder/'worker-result.json',receipt)
                except BaseException as exc:
                    _write_new(folder/'worker-error.json',dict(error_type=type(exc).__name__,worker_receipt_available=False));raise
                ack=(queue.acknowledge(app.manifest['role'],derived['source_id'],worker_receipt_sha256=result_pin) if packet is not None else
                    dict(acknowledgement=None,reference=queue.receipt()['reference'],scope='heartbeat_no_source_delivery_acknowledged'))
                _write_new(folder/'ack.json',ack)
                completed=dict(sequence=app.sequence+1,previous_sha256=app.head,completed_at=stamp(self.clock()).isoformat(),
                    files={p.name:dict(bytes=p.stat().st_size,sha256=_pin(p)) for p in folder.iterdir()},worker_after=after,delivery_id=derived['source_id'],queue_after=ack['reference'],**FLAGS)
                complete_pin=_write_new(folder/'complete.json',completed)
                app.reference=dict(app.reference,sequence=app.sequence+1,head_sha256=complete_pin);app._scan();app._archive_tail();self._head_proof()
                self.reference=dict(self.reference,application_reference=dict(app.reference))
                return dict(status='actual_cached_worker_application_completed' if packet is not None else 'actual_cached_worker_heartbeat_completed',
                    reference=self.reference,role=app.manifest['role'],opportunity_count=len(derived['decisions']),positive_decisions=sum(v['would_enter'] for v in derived['decisions']),
                    worker_receipt_sha256=result_pin,worker_result=result,queue_reference=ack['reference'],**FLAGS)

    def audit(self,queue):
        with self._lease():
            self._check();app=self.application;result=app.audit()
            if result['performance_hidden']:return dict(application_audit=result,reader_proof_full_audit_pass=False,performance_hidden=True,**FLAGS)
            if type(queue) is not ReferenceDelivery or _queue_identity(queue)!=app.manifest['queue_identity']:raise ValueError('original queue required for cached cash proof audit')
            queue.audit();started=monotonic();count=0
            with app._dispatch(),app._lease(),queue._lease():
                app._scan();db=app._db();qdb=_connect(queue.path,queue.policy)
                try:
                    db.execute('BEGIN');qdb.execute('BEGIN')
                    for (seq,) in db.execute('SELECT seq FROM groups ORDER BY seq'):
                        values=app._row(app._read_row(db,seq));original=self._proof(values);packet=original['packet']
                        if packet is not None:
                            delivery=packet['delivery'];batch=packet['batch']
                            stored=qdb.execute('SELECT payload,sha FROM batches WHERE seq=?',(delivery['batch_sequence'],)).fetchone()
                            ack=qdb.execute('SELECT payload FROM acks WHERE delivery_id=?',(delivery['delivery_id'],)).fetchone()
                            if stored!=(canonical(batch),delivery['batch_sha256']) or ack is None or parse(ack[0])['worker_receipt_sha256']!=digest(values['worker-result.json']):
                                raise ValueError('cached cash original source batch/result ack differs')
                            with SourceReplay(queue.source_manifest,None,parent=self.root.parent,maximum_database_bytes=queue.policy.maximum_scratch_database_bytes,
                                    maximum_seconds=app.policy.maximum_audit_seconds) as replay:
                                for row in qdb.execute('SELECT * FROM source_events WHERE seq<=? ORDER BY seq',(batch['source_to'],)):replay.feed(row)
                                if replay.view()!=packet['source_view']:raise ValueError('cached cash retained packet/full source replay differs')
                        count+=1
                        if monotonic()-started>app.policy.maximum_audit_seconds:raise ValueError('cached cash full proof audit budget exhausted')
                finally:qdb.close();db.close()
            return dict(application_audit=result,reader_proof_full_audit_pass=True,groups_checked=count,performance_hidden=False,
                scope='cached_reader_actual_paper_result_proof_not_economic_or_long_host_admission',**FLAGS)


_LOADED=runtime_hashes()
