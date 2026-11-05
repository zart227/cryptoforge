"""Registered read-only binding of a verified cached source view to a v1 offer.

Only the current whole poll is accepted. A lagging batch is blocked, never
silently reinterpreted with fresher data. Existing queue/cash/worker code is not
modified or monkey-patched. Full queue attachment and physical SHA remain costly.
"""
from datetime import UTC,datetime
from pathlib import Path
from time import monotonic

from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,sha,stamp,_new_root,_write_new,_sync
from cryptoforge.reference_prefix_v2 import ReferencePrefixV2,runtime_hashes as prefix_runtime
from cryptoforge.reference_delivery import ReferenceDelivery,ROLES,FLAGS,_connect,_delivery_id
from cryptoforge.reference_source_ledger import _sources_ready


def runtime_hashes():
    value=dict(prefix_runtime(),cached_reference_reader_v2=digest(Path(__file__).read_bytes()))
    if '_LOADED' in globals() and value!=_LOADED:raise ValueError('loaded cached reader runtime changed')
    return value


def _identity(obj):
    return {k:obj.reference[k] for k in ('root','manifest_sha256','registration_sha256')}


class CachedReferenceReaderV2:
    @classmethod
    def create(cls,root,queue,prefix,*,clock=None,maximum_read_seconds=10):
        clock=clock or (lambda:datetime.now(UTC));before=stamp(clock())
        if (type(queue) is not ReferenceDelivery or type(prefix) is not ReferencePrefixV2
                or type(maximum_read_seconds) is not int or not 1<=maximum_read_seconds<=30):
            raise ValueError('original queue and separately registered prefix required')
        view=prefix.view();source=prefix.manifest['source_reference'];q=queue.receipt()
        if (q['events'] or view['source_view']['source_sequence'] or queue.manifest['mode']!='prospective'
                or prefix.manifest['source_manifest']!=queue.source_manifest or queue.artifact is not None
                or any(queue.manifest['source_identity'][k]!=source[k] for k in ('root','manifest_sha256','registration_sha256'))
                or queue.policy.maximum_source_events_per_batch!=len(queue.source_manifest['pairs'])+2
                or not max(stamp(prefix.manifest['registered_at']),stamp(queue.manifest['registered_at']))<=before<stamp(queue.manifest['start'])):
            raise ValueError('new empty prospective one-poll source/queue/prefix binding required')
        root=_new_root(root,forbidden=(queue.root,prefix.root,Path(source['root'])))
        manifest=dict(schema_version='cached-reference-offer-reader-v2',root=str(root),registered_at=before.isoformat(),
            queue_identity=_identity(queue),prefix_identity=_identity(prefix),source_identity=source,
            start=queue.manifest['start'],end=queue.manifest['end'],runtime=runtime_hashes(),
            maximum_packet_bytes=queue.policy.maximum_delivery_bytes,maximum_read_seconds=maximum_read_seconds,
            backlog_policy='block_without_skipping_or_retiming',**FLAGS)
        pin=_write_new(root/'manifest.json',manifest);at=stamp(clock())
        if not before<=at<stamp(manifest['start']):raise ValueError('cached reader setup missed start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=pin,registered_at=at.isoformat()))
        if not at<=stamp(clock())<stamp(manifest['start']):
            (root/'registered.json').unlink();_sync(root);raise ValueError('cached reader durable setup missed start')
        return cls.open(dict(root=str(root),manifest_sha256=pin,registration_sha256=ready),clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None):
        if type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256'}:
            raise ValueError('original cached reader registration required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        manifest=parse(raw);registered=parse(ready)
        if (root.resolve()!=root or manifest['root']!=str(root) or digest(raw)!=sha(reference['manifest_sha256'])
                or digest(ready)!=sha(reference['registration_sha256']) or raw!=canonical(manifest)
                or registered['manifest_sha256']!=reference['manifest_sha256'] or manifest['schema_version']!='cached-reference-offer-reader-v2'
                or manifest['runtime']!=runtime_hashes() or manifest['backlog_policy']!='block_without_skipping_or_retiming'
                or not stamp(manifest['registered_at'])<=stamp(registered['registered_at'])<stamp(manifest['start'])
                or type(manifest['maximum_read_seconds']) is not int or not 1<=manifest['maximum_read_seconds']<=30
                or type(manifest['maximum_packet_bytes']) is not int or not 4096<=manifest['maximum_packet_bytes']<=16*1024**2
                or any(manifest[k] is not False for k in FLAGS)):
            raise ValueError('original cached reader contract differs')
        obj=cls();obj.root=root;obj.reference=dict(reference);obj.manifest=manifest;obj.clock=clock or (lambda:datetime.now(UTC))
        obj._check();return obj

    def _check(self):
        if (self.root.resolve()!=self.root or self.manifest['root']!=str(self.root) or self.reference['root']!=str(self.root)
                or {p.name for p in self.root.iterdir()}!={'manifest.json','registered.json'}
                or digest(read_file(self.root/'manifest.json',maximum=131072))!=self.reference['manifest_sha256']
                or digest(read_file(self.root/'registered.json',maximum=4096))!=self.reference['registration_sha256']
                or parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest or self.manifest['runtime']!=runtime_hashes()):
            raise ValueError('cached reader metadata/runtime changed')
        at=stamp(self.clock())
        if at<stamp(self.manifest['registered_at']) or at<getattr(self,'last_clock',at):raise ValueError('cached reader clock moved backwards')
        self.last_clock=at;return at

    def read(self,queue,prefix_reference,role,delivery_id):
        started=monotonic();self._check()
        if type(queue) is not ReferenceDelivery or _identity(queue)!=self.manifest['queue_identity'] or role not in ROLES:
            raise ValueError('registered cached reader queue/role required')
        sha(delivery_id);prefix=ReferencePrefixV2.open(prefix_reference,clock=self.clock)
        if _identity(prefix)!=self.manifest['prefix_identity'] or prefix.manifest['source_manifest']!=queue.source_manifest:
            raise ValueError('registered cached source prefix differs')
        with prefix._lease(),queue._lease():
            _,checkpoint=prefix._check();now=queue._check();at=self._check();view=checkpoint['source_view']
            db=_connect(queue.path,queue.policy);index=prefix._db()
            try:
                db.execute('BEGIN');index.execute('BEGIN')
                cursor,seq,identity,offered=db.execute('SELECT cursor,pending_seq,delivery_id,offered_at FROM cursors WHERE role=?',(role,)).fetchone()
                if seq!=cursor+1 or identity!=delivery_id or not stamp(offered)<=min(now,at):raise ValueError('original pending cached role delivery required')
                raw,batch_sha=db.execute('SELECT payload,sha FROM batches WHERE seq=?',(seq,)).fetchone();batch=parse(raw)
                if (raw!=canonical(batch) or digest(raw)!=batch_sha or batch['batch_sequence']!=seq
                        or delivery_id!=_delivery_id(queue.reference['manifest_sha256'],role,seq,batch_sha)
                        or not queue._resolved(db,batch)):
                    raise ValueError('cached reader original batch/offer differs')
                if (view['source_sequence']!=batch['source_to'] or view['source_head_sha256']!=batch['source_end_head']
                        or checkpoint['source_reference']!=batch['source_reference']):
                    raise ValueError('cached view is not the original pending prefix; backlog blocked')
                expected=len(queue.source_manifest['pairs'])+2
                if batch['source_to']-batch['source_from']+1!=expected:raise ValueError('cached reader requires one whole cash poll')
                events=[];size=0;previous=batch['source_previous_head']
                for event_seq,kind,length,prior,head in db.execute('SELECT seq,kind,length(payload),previous,sha FROM source_events WHERE seq BETWEEN ? AND ? ORDER BY seq',
                        (batch['source_from'],batch['source_to'])):
                    if not 0<length<=queue.source_manifest['policy']['maximum_event_bytes']:raise ValueError('bounded cached original source event required')
                    payload=db.execute('SELECT payload FROM source_events WHERE seq=?',(event_seq,)).fetchone()[0]
                    retained=index.execute('SELECT * FROM events WHERE seq=?',(event_seq,)).fetchone()
                    if retained!=(event_seq,kind,payload,prior,head) or prior!=previous:raise ValueError('cached source/index event bytes differ')
                    events.append(dict(sequence=event_seq,kind=kind,payload=parse(payload),previous_sha256=prior,sha256=head))
                    previous=head;size+=length
                    if size>queue.policy.maximum_source_bytes_per_batch:raise ValueError('cached source batch bytes exhausted')
                if len(events)!=expected or events[0]['kind']!='poll_prepared' or events[-1]['kind']!='poll_complete' or previous!=view['source_head_sha256']:
                    raise ValueError('cached original whole-poll event interval differs')
                packet=dict(delivery=dict(role=role,batch_sequence=seq,delivery_id=identity,batch_sha256=batch_sha,offered_at=offered),
                    batch=batch,source_events=events,source_view=view,
                    closed_candles_ready=stamp(queue.manifest['start'])<=now<=stamp(queue.manifest['end']) and _sources_ready(view['windows'],now),
                    worker_prediction_batch_available=False,**FLAGS)
                raw=canonical(packet)
                if len(raw)>self.manifest['maximum_packet_bytes']:raise ValueError('cached original packet byte budget exhausted')
                if monotonic()-started>self.manifest['maximum_read_seconds']:raise ValueError('cached read wall budget exhausted')
                return dict(packet=packet,packet_sha256=digest(raw),reader_reference=dict(self.reference),prefix_reference=dict(prefix_reference),
                    source_semantic_prefix_replayed=False,scope='read_only_cached_packet_binding_not_worker_execution',**FLAGS)
            finally:index.close();db.close()


_LOADED=runtime_hashes()
