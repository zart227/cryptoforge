"""Explicit recovery ONLY of a durable completed paper result and its queue ack.

No worker tick, provider, source poll or exchange order is ever rerun. Missing
worker-result, changed native/head state or unknown partial actions stay blocked.
Original application/runtime/DB pins are preserved; queue recovery uses the
existing explicit known-ancestor semantic replay contract.
"""
from contextlib import contextmanager
from datetime import UTC,datetime
import fcntl
import os
from pathlib import Path
from time import monotonic

from cryptoforge.cash_entry_contract import FLAGS,load_cash_contract,evaluate_cash_packet,_queue_identity
from cryptoforge.cash_worker_application import CashWorkerApplication,CashApplicationPolicy,_heartbeat,_pin,_worker_identity,runtime_hashes as application_runtime
from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,stamp,sha,_new_root,_write_new
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2
from cryptoforge.paper_capture_v3 import _lease as capture_lease
from cryptoforge.paper_capture_state_v2 import _logical,_active
from cryptoforge.evidence_segments import _verified_frame,_guard
from cryptoforge.reference_delivery import ReferenceDelivery,_connect,_delivery_id
from cryptoforge.reference_delivery_source import SourceReplay
from cryptoforge.reference_source_ledger import FLAGS as SOURCE_FLAGS


def _runtime():
    value=dict(application_runtime(),cash_ack_recovery=digest(Path(__file__).read_bytes()),
        cash_ack_recovery_cli=digest((Path(__file__).resolve().parents[2]/'scripts/recover_cash_ack.py').read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded ack recovery runtime changed')
    return value


@contextmanager
def _application_lease(root):
    read_file(root/'writer.lock',maximum=0);fd=os.open(root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
    finally:os.close(fd)


def _prefix(reference):
    if (type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256','sequence','head_sha256'}
            or type(reference['sequence']) is not int or reference['sequence']<0):raise ValueError('known external application checkpoint required')
    root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
    value=parse(raw);registered=parse(ready);contract=load_cash_contract(value['contract_reference']);policy=CashApplicationPolicy(**value['policy'])
    if (root.resolve()!=root or root.stat().st_uid!=os.getuid() or value['root']!=str(root)
            or digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
            or value['schema_version']!='cash-worker-application-v1' or value['runtime']!=application_runtime()
            or registered['manifest_sha256']!=reference['manifest_sha256']
            or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])
            or any(value[k] is not False for k in FLAGS) or value['queue_identity']!=contract['queue_identity']
            or {p.name for p in root.iterdir()}!={'manifest.json','registered.json','writer.lock','groups'}
            or (root/'groups').resolve()!=root/'groups'):
        raise ValueError('original application registration/runtime differs')
    paths=sorted((root/'groups').iterdir());expected=reference['sequence']+1
    if len(paths)!=expected or expected>policy.maximum_groups:raise ValueError('exact known completed prefix plus one pending group required')
    head=reference['manifest_sha256'];worker_head=value['worker_initial_head'];started=monotonic();total=0
    for sequence,path in enumerate(paths,1):
        if path.resolve()!=path or not path.is_dir() or path.name!=f'{sequence:08d}':raise ValueError('original application sequence required')
        if sequence==expected:
            if (path/'complete.json').exists():raise ValueError('target already completed; no ack recovery needed')
            break
        complete=parse(read_file(path/'complete.json',maximum=65536))
        if (set(p.name for p in path.iterdir())!=set(complete['files'])|{'complete.json'}
                or complete['sequence']!=sequence or complete['previous_sha256']!=head):raise ValueError('known application prefix differs')
        group_bytes=0
        for name,pin in complete['files'].items():
            if name not in ('input.json','prepared.json','worker-result.json','ack.json'):raise ValueError('unknown completed cash file')
            p=path/name;read_file(p,maximum=policy.maximum_group_bytes);group_bytes+=p.stat().st_size
            if pin!=dict(bytes=p.stat().st_size,sha256=_pin(p)):raise ValueError('known application prefix source changed')
        if group_bytes>policy.maximum_group_bytes:raise ValueError('bounded completed cash prefix required')
        total+=group_bytes;head=_pin(path/'complete.json');worker_head=complete['worker_after']
        if total>policy.maximum_bytes or monotonic()-started>policy.maximum_scan_seconds:raise ValueError('recovery prefix budget exhausted')
    if head!=sha(reference['head_sha256']):raise ValueError('unknown external application ancestor')
    folder=paths[-1];names={p.name for p in folder.iterdir()}
    if names not in ({'input.json','prepared.json','worker-result.json'},{'input.json','prepared.json','worker-result.json','ack.json'}):
        raise ValueError('durable worker-result required; unknown/missing worker completion stays blocked')
    original=parse(read_file(folder/'input.json',maximum=policy.maximum_group_bytes));prepared=parse(read_file(folder/'prepared.json',maximum=65536))
    result=parse(read_file(folder/'worker-result.json',maximum=512*1024));at=original['derived']['source_observed_at'];packet=original['packet']
    derived=(evaluate_cash_packet(contract,value['contract_reference']['contract_sha256'],packet,value['role'],observed_at=at)
        if packet is not None else _heartbeat(reference['manifest_sha256'],at))
    if (original['derived']!=derived or result['input_sha256']!=_pin(folder/'input.json') or prepared['input_sha256']!=result['input_sha256']
            or prepared['worker_before']!=worker_head or result['worker_before']!=worker_head
            or result['worker_identity']!=value['worker_identity'] or any(result[k] is not False for k in FLAGS)):
        raise ValueError('original durable cash inputs/result linkage differs')
    # This recovery handles a real delivered poll result. Heartbeat has no ack.
    if packet is None:raise ValueError('heartbeat has no source acknowledgement to recover')
    if prepared['queue_before']['root']!=value['queue_identity']['root']:raise ValueError('original known queue ancestor required')
    return root,folder,value,contract,policy,original,prepared,result


def _original_packet(queue,saved):
    delivery=saved['delivery'];role=delivery['role'];sequence=delivery['batch_sequence']
    with queue._lease():
        queue._check();db=_connect(queue.path,queue.policy)
        try:
            row=db.execute('SELECT payload,sha FROM batches WHERE seq=?',(sequence,)).fetchone()
            if row is None:raise ValueError('original delivered source batch missing')
            batch=parse(row[0])
            if (delivery['batch_sha256']!=row[1] or digest(canonical(batch))!=row[1]
                    or delivery['delivery_id']!=_delivery_id(queue.reference['manifest_sha256'],role,sequence,row[1])):
                raise ValueError('original cash delivery identity differs')
            offers=[parse(raw)['delivery'] for (raw,) in db.execute("SELECT payload FROM events WHERE kind='offer'")
                if parse(raw)['delivery']['delivery_id']==delivery['delivery_id']]
            if offers!=[delivery]:raise ValueError('original role offer changed')
            with SourceReplay(queue.source_manifest,queue.artifact,parent=queue.root.parent,maximum_database_bytes=queue.policy.maximum_scratch_database_bytes) as replay:
                for row in db.execute('SELECT * FROM source_events WHERE seq<=? ORDER BY seq',(batch['source_to'],)):replay.feed(row)
                view=replay.view()
            events=[dict(sequence=s,kind=k,payload=parse(raw),previous_sha256=prior,sha256=h)
                for s,k,raw,prior,h in db.execute('SELECT * FROM source_events WHERE seq BETWEEN ? AND ? ORDER BY seq',(batch['source_from'],batch['source_to']))]
            # Freshness at the earlier read is observational; cash decisions are
            # independently rederived at their original decision timestamp.
            expected=dict(delivery=delivery,batch=batch,source_events=events,source_view=view,
                closed_candles_ready=saved['closed_candles_ready'],worker_prediction_batch_available=False,**SOURCE_FLAGS)
            if type(saved['closed_candles_ready']) is not bool or saved!=expected:raise ValueError('retained original cash source packet differs')
            cursor=db.execute('SELECT cursor,pending_seq,delivery_id FROM cursors WHERE role=?',(role,)).fetchone()
            if cursor not in ((sequence-1,sequence,delivery['delivery_id']),(sequence,None,None)):
                raise ValueError('cash role advanced beyond target or pending delivery changed')
        finally:db.close()


def _worker_prefix(worker,result,derived):
    expected=result['worker_after'];before=result['worker_before']
    if list(worker._head())!=expected:raise ValueError('worker advanced beyond durable result; no recovery')
    sequence=0;previous=worker.log.manifest_sha256;found_before=None;found_prepared=None;last=None;started=monotonic()
    with worker.log._lease(writer=False):
        db=worker.log._db(writer=False)
        try:
            worker.log._validate_files(db,verify_hashes=True)
            for (ordinal,) in db.execute('SELECT ordinal FROM segments ORDER BY ordinal'):
                path=worker.log._path(ordinal);info=_guard(path,limit=worker.log.policy.maximum_segment_bytes)
                with path.open('rb') as stream:
                    while True:
                        raw=stream.readline(worker.log.policy.maximum_record_bytes+1)
                        if not raw:break
                        if len(raw)>worker.log.policy.maximum_record_bytes:raise ValueError('bounded original worker frame required')
                        last=_verified_frame(raw,sequence+1,previous);sequence+=1;previous=last['sha256']
                        if sequence==before[0]:found_before=last
                        if sequence==before[0]+1:found_prepared=last
                        if monotonic()-started>15:raise ValueError('worker recovery stream wall budget exhausted')
                after=_guard(path,limit=worker.log.policy.maximum_segment_bytes)
                if (info.st_dev,info.st_ino,info.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_mtime_ns):raise ValueError('worker source changed during recovery read')
        finally:db.close()
    inputs={k:derived[k] for k in ('predictions','source_id','source_observed_at','source_sha256')}
    if (sequence!=expected[0] or previous!=expected[4] or found_before is None or found_prepared!=result['prepared_tick']
            or found_before['sha256']!=before[4] or canonical(found_before['payload']).decode()!=before[2]
            or found_prepared['kind']!='prepared' or found_prepared['payload']['inputs']!=inputs
            or last['kind']!='complete' or last['payload']['phase']!='tick' or last['payload']['prepared_seq']!=before[0]+1
            or last['payload']['result']!=result['result']):raise ValueError('full original worker prefix/result differs')
    return dict(frames_checked=sequence,original_worker_head_sha256=previous)


def recover_cash_ack(known_reference,recovery_root,*,apply=False,clock=None):
    if type(apply) is not bool:raise ValueError('explicit paper ack mode required')
    clock=clock or (lambda:datetime.now(UTC));root=Path(known_reference['root']).absolute()
    with _application_lease(root):
        root,folder,manifest,contract,policy,original,prepared,result=_prefix(known_reference)
        def forbidden(*a,**k):raise AssertionError('recovery must never call a provider or worker tick')
        worker=CapturedPaperWorkerV2.resume(manifest['worker_identity']['root'],
            expected_registration_sha256=manifest['worker_identity']['registration_sha256'],market=forbidden,clock=clock)
        with capture_lease(worker.root,writer=True):
            if _worker_identity(worker)!=manifest['worker_identity']:raise ValueError('original worker registration differs')
            with worker._source._lease(writer=False):
                if _logical(worker._source,_active(worker._source),worker._cache)!=parse(result['worker_after'][2])['after']:
                    raise ValueError('worker native state differs from durable result')
            proof=_worker_prefix(worker,result,original['derived'])
            recovered=ReferenceDelivery.recover(prepared['queue_before'],clock=clock)
            queue=ReferenceDelivery.open(recovered['reference'],clock=clock)
            if _queue_identity(queue)!=manifest['queue_identity']:raise ValueError('original queue identity differs')
            _original_packet(queue,original['packet'])
            pin=_pin(folder/'worker-result.json');expected_files={p.name:_pin(p) for p in folder.iterdir()}
            now=stamp(clock())
            if now<stamp(result['application_completed_at']):raise ValueError('recovery clock before original worker result')
            containers=[p.parent for p in (root,queue.root,worker.root) if (p.parent/'manifest.json').exists() or (p.parent/'registered.json').exists()]
            recovery_root=_new_root(recovery_root,forbidden=(root,queue.root,worker.root,Path(manifest['contract_reference']['root']),
                Path(queue.manifest['source_identity']['root']),*containers))
            proposal=dict(schema_version='explicit-known-paper-result-ack-recovery-v1',observed_at=now.isoformat(),
                known_application_reference=known_reference,pending_group=str(folder),original_file_pins=expected_files,
                worker_result_sha256=pin,worker_prefix=proof,known_queue_ancestor=prepared['queue_before'],
                verified_current_queue_reference=recovered['reference'],runtime=_runtime(),worker_or_provider_reexecution_permitted=False,**FLAGS)
            proposal_pin=_write_new(recovery_root/'proposal.json',proposal)
            if not apply:
                value=dict(status='read_only_recovery_plan',proposal_sha256=proposal_pin,application_or_queue_changed=False,**FLAGS)
                _write_new(recovery_root/'plan-only.json',value);return value
            last_clock=now
            def observed_clock():
                nonlocal last_clock
                at=stamp(clock())
                if at<last_clock:raise ValueError('recovery clock moved backwards')
                last_clock=at;return at
            _write_new(recovery_root/'prepared.json',dict(proposal_sha256=proposal_pin,at=observed_clock().isoformat()))
            if expected_files!={p.name:_pin(p) for p in folder.iterdir()} or list(worker._head())!=result['worker_after']:
                raise ValueError('recovery source changed before acknowledgement')
            ack=queue.acknowledge(manifest['role'],original['derived']['source_id'],worker_receipt_sha256=pin)
            observed_clock()
            if (folder/'ack.json').exists():
                saved=parse(read_file(folder/'ack.json',maximum=65536))
                if saved['acknowledgement']!=ack['acknowledgement']:raise ValueError('existing original acknowledgement conflicts')
                ReferenceDelivery.recover(saved['reference'],clock=clock)
            else:_write_new(folder/'ack.json',ack);saved=ack
            files={p.name:dict(bytes=p.stat().st_size,sha256=_pin(p)) for p in folder.iterdir()}
            complete=dict(sequence=known_reference['sequence']+1,previous_sha256=known_reference['head_sha256'],
                completed_at=observed_clock().isoformat(),files=files,worker_after=result['worker_after'],
                delivery_id=original['derived']['source_id'],queue_after=saved['reference'],**FLAGS)
            completion=_write_new(folder/'complete.json',complete)
            new_reference=dict(known_reference,sequence=complete['sequence'],head_sha256=completion)
    audit=CashWorkerApplication.open(new_reference,clock=clock).audit()
    value=dict(status='known_worker_result_acknowledgement_recovered',proposal_sha256=proposal_pin,
        application_reference=new_reference,current_queue_reference=ack['reference'],original_worker_result_sha256=pin,
        worker_execution_repeated=False,provider_calls=0,application_audit=audit,completed_at=stamp(clock()).isoformat(),**FLAGS)
    _write_new(recovery_root/'completed.json',value);return value


_LOADED=_runtime()
