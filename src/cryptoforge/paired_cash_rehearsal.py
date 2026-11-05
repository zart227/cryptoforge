"""One bounded prospective three-role paper rehearsal, never a live executor.

Registration is offline. Explicit run uses public GETs and isolated local files.
It is single-use: any interrupted component operation blocks automatic retry.
"""
from dataclasses import asdict
from datetime import UTC,datetime,timedelta
import fcntl
import math
import os
from pathlib import Path
import sys
from time import monotonic,sleep
from urllib.parse import urlencode
from urllib.request import Request,build_opener,HTTPRedirectHandler

from cryptoforge.backend import resolve_backend
from cryptoforge.cash_entry_contract import FLAGS,freeze_cash_contract,load_cash_contract
from cryptoforge.cash_worker_application import CashWorkerApplication,CashApplicationPolicy,runtime_hashes as cash_runtime
from cryptoforge.local_source_provenance import canonical,digest,parse,read_file,stamp,sha,_new_root,_write_new,_sync
from cryptoforge.local_source_observer import bounded_process
from cryptoforge.reference_source_ledger import ReferenceLedger,ReferencePolicy
from cryptoforge.reference_sources import PublicReferenceClient,INTERVAL_MS
from cryptoforge.reference_delivery import ReferenceDelivery,DeliveryPolicy,ROLES
from cryptoforge.paper_producer_v2 import register_kernel
from cryptoforge.paper_worker_capture_v2 import CapturedPaperWorkerV2,WorkerCapturePolicyV2
from cryptoforge.paper_capture_v3 import SegmentedLifecycle
from cryptoforge.evidence_segments import SegmentPolicy
from cryptoforge.native_paper_archive_v2 import NativeArchivePolicy
from cryptoforge.paper_wallet import PaperConfig
from cryptoforge.paper_lifecycle import measure_resources
from cryptoforge.paper_worker_replay_v2 import register_worker_replay,audit_worker_replay,runtime_hashes as replay_runtime
from cryptoforge.paper_wallet_replay_v2 import ReplayPolicyV2
from cryptoforge.paper_valuation_capture import observe_valuation_market

MAXIMUM_SECONDS=120
MAXIMUM_RUN_SECONDS=320
MINIMUM_MEMORY=128*1024**2
DISK_RESERVE=2048*1024**2+768*1024**2


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*a,**kw):raise ValueError('paper public redirect forbidden')


def _public_arguments(path,params):
    expected={'category':'spot','symbol':params.get('symbol')}
    if path=='/v5/market/orderbook':expected['limit']=1
    if (path not in ('/v5/market/orderbook','/v5/market/instruments-info') or params!=expected
            or params['symbol'] not in ('BTCUSDT','ETHUSDT')):
        raise ValueError('fixed reference public GET required')


def _public_once(path,params):
    _public_arguments(path,params);started=monotonic();raw=bytearray()
    try:
        with build_opener(_NoRedirect()).open(Request('https://api.bybit.com'+path+'?'+urlencode(params)),timeout=.6) as response:
            if response.status!=200:raise ValueError('public paper read failed')
            while True:
                if monotonic()-started>.8:raise TimeoutError('public paper body wall budget')
                block=response.read1(min(65536,65537-len(raw)))
                if not block:break
                raw.extend(block)
                if len(raw)>65536:raise ValueError('public paper byte budget')
        return dict(http_status=200,payload=parse(bytes(raw)))
    except Exception as exc:
        if getattr(exc,'code',None) in (403,429):return dict(http_status=exc.code,payload=None)
        raise


def _public_process(path,params):
    # One killable child bounds DNS/connect/read as a whole, including imports.
    code="import sys;sys.path.insert(0,sys.argv[1]);from cryptoforge.paired_cash_rehearsal import _public_once;from cryptoforge.local_source_provenance import parse,canonical;sys.stdout.buffer.write(canonical(_public_once(sys.argv[2],parse(sys.argv[3]))))"
    raw=bounded_process([sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]),path,canonical(params).decode()],
        '',maximum_bytes=128*1024,maximum_seconds=1)
    return parse(raw)


class BoundedPaperPublicClient:
    base_url='https://api.bybit.com'
    def __init__(self):self.paused_until=0
    def _get_json(self,path,params):
        _public_arguments(path,params)
        if monotonic()<self.paused_until:raise TimeoutError('paper public rate pause active')
        observed=_public_process(path,params);value=observed['payload']
        if observed['http_status'] in (403,429) or value and value.get('retCode') in (10006,10429):self.paused_until=monotonic()+600
        if observed['http_status']!=200:raise ValueError('public paper read paused')
        return value


def _runtime():
    value=dict(cash_runtime(),**{'replay:'+k:v for k,v in replay_runtime().items()},
        paired_cash_rehearsal=digest(Path(__file__).read_bytes()),
        paired_cash_rehearsal_cli=digest((Path(__file__).resolve().parents[2]/'scripts/rehearse_paired_cash.py').read_bytes()))
    if '_LOADED_RUNTIME' in globals() and value!=_LOADED_RUNTIME:raise ValueError('loaded paired runtime changed; new process/namespace required')
    return value


def _resources(root):
    value=measure_resources(root)
    if (type(value['available_memory_bytes']) is not int or value['available_memory_bytes']<MINIMUM_MEMORY
            or value['free_disk_bytes']<DISK_RESERVE):raise ValueError('paired rehearsal resource reserve unavailable')
    return value


def _worker_ref(worker):
    return dict(root=str(worker.root),registration_sha256=worker.registration_sha256)


class PairedCashRehearsal:
    @classmethod
    def create(cls,root,*,start,end,rules,configs,worker_policy,closeout_seconds,backend_env,clock=None,market=None):
        clock=clock or (lambda:datetime.now(UTC));now=stamp(clock());start=stamp(start);end=stamp(end)
        duration=(end-start).total_seconds()
        if (resolve_backend(backend_env).name!='local' or not now<start or not 20<=duration<=MAXIMUM_SECONDS
                or (start-now).total_seconds()>60 or set(configs)!=set(ROLES)
                or worker_policy.get('exits',{}).get('shared_exit_signal') is not False):
            raise ValueError('new short prospective local three-role rehearsal required')
        measured=_resources(root);root=_new_root(root);(root/'journal').mkdir(mode=0o700);(root/'writer.lock').touch(mode=0o600)
        market=market or (lambda pair:observe_valuation_market(BoundedPaperPublicClient(),pair))
        source=ReferenceLedger.create(root/'source',start=start,end=end,clock=clock,
            policy=ReferencePolicy(maximum_database_bytes=16*1024**2,maximum_events=200,maximum_versions=2000,maximum_forecasts=10))
        source_ref=source.receipt()['reference']
        queue=ReferenceDelivery.create(root/'delivery',source_ref,clock=clock,
            policy=DeliveryPolicy(maximum_database_bytes=16*1024**2,maximum_scratch_database_bytes=32*1024**2,
                maximum_events=200,maximum_source_events=200,maximum_batches=20,maximum_source_events_per_batch=4))
        contract_ref=freeze_cash_contract(root/'cash-contract',queue,rules=rules,closeout_seconds=closeout_seconds,clock=clock)
        contract=load_cash_contract(contract_ref);applications={};workers={};replays={};groups=math.ceil(duration/5)+2
        lifecycle=SegmentedLifecycle(poll_seconds=5,maximum_operations_per_poll=1,estimated_bytes_per_operation=8192,
            maximum_mark_gap_seconds=10,maximum_endpoint_gap_seconds=20,minimum_known_time_fraction='.9',
            closeout_seconds=closeout_seconds,finalization_grace_seconds=30,maximum_operation_wall_seconds=5,
            maximum_storage_bytes=64*1024**2,minimum_free_disk_bytes=2048*1024**2,minimum_available_memory_bytes=MINIMUM_MEMORY)
        storage=SegmentPolicy(maximum_events=8192,maximum_segments=128,maximum_segment_events=256,
            maximum_segment_bytes=2*1024**2,maximum_record_bytes=32768,maximum_total_bytes=16*1024**2)
        native=NativeArchivePolicy(shards=4,maximum_shard_bytes=2*1024**2,maximum_active_bytes=1024**2,
            maximum_active_rows=64,maximum_records=10000,maximum_row_bytes=16384,maximum_batch_bytes=65536,
            maximum_total_bytes=32*1024**2,minimum_free_disk_bytes=2048*1024**2,minimum_available_memory_bytes=MINIMUM_MEMORY)
        capture=WorkerCapturePolicyV2(maximum_predictions_per_tick=2,maximum_actions_per_tick=24,
            maximum_clock_calls_per_tick=64,maximum_market_requests_per_tick=2,maximum_exit_requests_per_tick=2)
        replay_policy=ReplayPolicyV2(maximum_scratch_bytes=16*1024**2,maximum_state_rows=10000,maximum_active_rows=128,
            maximum_active_bytes=1024**2,maximum_wall_seconds=30,minimum_available_memory_bytes=MINIMUM_MEMORY,minimum_free_disk_bytes=2048*1024**2)
        for role in ROLES:
            config=configs[role] if type(configs[role]) is PaperConfig else PaperConfig(**configs[role])
            kernel=register_kernel(root/('kernel-'+role),candidate_sha=contract['strategies'][role],study_protocol_sha256=contract_ref['contract_sha256'],
                role=role,config=config,worker_policy=worker_policy,start=start,end=end,closeout_seconds=closeout_seconds,backend_env=backend_env,clock=clock)
            worker=CapturedPaperWorkerV2.create(root/('worker-'+role),kernel_root=kernel['root'],expected_kernel_contract_sha256=kernel['contract_sha256'],
                expected_kernel_registration_sha256=kernel['registration_sha256'],lifecycle=lifecycle,storage_policy=storage,native_policy=native,
                capture_policy=capture,market=market,clock=clock)
            app=CashWorkerApplication.create(root/('application-'+role),contract_ref,queue,worker,clock=clock,
                policy=CashApplicationPolicy(maximum_groups=groups,maximum_group_bytes=2*1024**2,maximum_bytes=groups*2*1024**2))
            applications[role]=app.reference;workers[role]=_worker_ref(worker)
            replays[role]=register_worker_replay(root/('replay-'+role),capture_root=worker.root,expected_registration_sha256=worker.registration_sha256,
                policy=replay_policy,backend_env=backend_env,clock=clock)
        value=dict(schema_version='bounded-paired-cash-rehearsal-v1',root=str(root),registered_at=now.isoformat(),start=start.isoformat(),end=end.isoformat(),
            runtime=_runtime(),cash_contract_reference=contract_ref,initial_state=dict(source=source_ref,queue=queue.receipt()['reference'],applications=applications),
            workers=workers,replays=replays,registration_resources=measured,poll_seconds=5,maximum_run_seconds=MAXIMUM_RUN_SECONDS,
            scope='single_use_reference_pair_rehearsal_not_long_study_or_live_admission',**FLAGS)
        manifest_pin=_write_new(root/'manifest.json',value);at=stamp(clock())
        if not now<=at<start:raise ValueError('paired rehearsal missed prospective start')
        ready=_write_new(root/'registered.json',dict(manifest_sha256=manifest_pin,registered_at=at.isoformat()))
        if not at<=stamp(clock())<start:
            (root/'registered.json').unlink();_sync(root);raise ValueError('paired durable registration missed start')
        return cls.open(dict(root=str(root),manifest_sha256=manifest_pin,registration_sha256=ready),clock=clock)

    @classmethod
    def open(cls,reference,*,clock=None):
        if type(reference) is not dict or set(reference)!={'root','manifest_sha256','registration_sha256'}:raise ValueError('paired registration pins required')
        root=Path(reference['root']).absolute();raw=read_file(root/'manifest.json',maximum=131072);ready=read_file(root/'registered.json',maximum=4096)
        value=parse(raw);registered=parse(ready)
        if (root.resolve()!=root or root.stat().st_uid!=os.getuid() or value['root']!=str(root)
                or digest(raw)!=sha(reference['manifest_sha256']) or digest(ready)!=sha(reference['registration_sha256'])
                or value['schema_version']!='bounded-paired-cash-rehearsal-v1' or value['runtime']!=_runtime()
                or registered['manifest_sha256']!=reference['manifest_sha256']
                or not stamp(value['registered_at'])<=stamp(registered['registered_at'])<stamp(value['start'])<stamp(value['end'])
                or any(value[k] is not False for k in FLAGS)):
            raise ValueError('original bounded paired rehearsal differs')
        obj=cls();obj.root=root;obj.manifest=value;obj.reference=dict(reference);obj.clock=clock or (lambda:datetime.now(UTC))
        obj._static()
        return obj

    def _static(self):
        if (parse(read_file(self.root/'manifest.json',maximum=131072))!=self.manifest
                or digest(read_file(self.root/'manifest.json',maximum=131072))!=self.reference['manifest_sha256']
                or digest(read_file(self.root/'registered.json',maximum=4096))!=self.reference['registration_sha256']
                or self.manifest['runtime']!=_runtime() or (self.root/'journal').resolve()!=self.root/'journal'):
            raise ValueError('original paired registration/runtime/journal differs')
        names={'manifest.json','registered.json','writer.lock','journal','source','delivery','cash-contract'}
        names|={prefix+role for prefix in ('kernel-','worker-','application-','replay-') for role in ROLES}
        actual={p.name for p in self.root.iterdir()}
        if actual not in (names,names|{'terminal.json'}):raise ValueError('paired root inventory differs')

    def inspect(self):
        # Every journal operation has two immutable records. A pending record is
        # visible and never repaired or retried by this runner.
        self._static();head=self.reference['manifest_sha256'];completed=0;pending=None;state=self.manifest['initial_state']
        names=sorted((self.root/'journal').iterdir())
        if len(names)>256:raise ValueError('paired journal budget exhausted')
        for index,path in enumerate(names,1):
            if path.name!=f'{index:08d}.json':raise ValueError('paired journal sequence differs')
            row=parse(read_file(path,maximum=131072))
            if row['previous_sha256']!=head or row['sequence']!=index:raise ValueError('paired journal chain differs')
            if index%2:
                if row['phase']!='prepared':raise ValueError('paired operation preparation required')
                pending=row
            else:
                if row['phase']!='completed' or pending is None or row['operation']!=pending['operation']:raise ValueError('paired operation result differs')
                state=row['state'];completed+=1;pending=None
            head=digest(canonical(row))
        return dict(reference=self.reference,completed_operations=completed,pending_operation=pending['operation'] if pending else None,
            latest_state=state,terminal_exists=(self.root/'terminal.json').exists(),**FLAGS)

    def run(self,*,client=None,market=None,sleeper=None):
        read_file(self.root/'writer.lock',maximum=0);fd=os.open(self.root/'writer.lock',os.O_RDONLY|os.O_NOFOLLOW)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._static()
            if any((self.root/'journal').iterdir()) or (self.root/'terminal.json').exists():raise ValueError('single-use rehearsal already started; no automatic retry')
            if not stamp(self.clock())<stamp(self.manifest['start']):raise ValueError('runner must attach before original start')
            deadline=monotonic()+MAXIMUM_RUN_SECONDS;previous_clock=stamp(self.clock());sequence=0;head=self.reference['manifest_sha256']
            state=parse(canonical(self.manifest['initial_state']));sleeper=sleeper or sleep;public=BoundedPaperPublicClient()
            market=market or (lambda pair:observe_valuation_market(public,pair));client=client or PublicReferenceClient()
            workers={r:CapturedPaperWorkerV2.resume(v['root'],expected_registration_sha256=v['registration_sha256'],market=market,clock=self.clock) for r,v in self.manifest['workers'].items()}
            source=ReferenceLedger.open(state['source'],clock=self.clock);queue=ReferenceDelivery.open(state['queue'],clock=self.clock)
            apps={r:CashWorkerApplication.open(v,clock=self.clock) for r,v in state['applications'].items()}
            def check():
                nonlocal previous_clock
                now=stamp(self.clock())
                if now<previous_clock or monotonic()>deadline:raise ValueError('paired clock/wall budget changed')
                self._static()
                previous_clock=now;return now
            def operation(name,call):
                nonlocal sequence,head
                now=check();_resources(self.root)
                prepared=dict(sequence=sequence+1,previous_sha256=head,phase='prepared',operation=name,at=now.isoformat())
                head=_write_new(self.root/'journal'/f'{sequence+1:08d}.json',prepared);sequence+=1
                result=call()
                value=dict(sequence=sequence+1,previous_sha256=head,phase='completed',operation=name,at=check().isoformat(),state=state,result=result)
                head=_write_new(self.root/'journal'/f'{sequence+1:08d}.json',value);sequence+=1
                if sequence>256:raise ValueError('paired journal budget exhausted')
                return result
            while check()<stamp(self.manifest['start']):sleeper(min(1,(stamp(self.manifest['start'])-check()).total_seconds()))
            last_anchor=None;last_slot=None;ticks={r:0 for r in ROLES};missed_slots=0
            while check()<stamp(self.manifest['end']):
                now=check();anchor=int(now.timestamp()*1000)//INTERVAL_MS*INTERVAL_MS
                if anchor!=last_anchor:
                    def poll():
                        value=source.poll(client);state['source']=source.receipt()['reference'];return dict(events=value['events'],versions=value['versions'])
                    operation('source_poll',poll);last_anchor=anchor
                    def ingest():
                        value=queue.ingest(state['source']);state['queue']=value['reference'];return dict(batches=value['batches'])
                    operation('source_ingest',ingest)
                now=check();slot=int((now-stamp(self.manifest['start'])).total_seconds()//5)
                if last_slot is None or slot>last_slot:
                    missed_slots+=max(0,slot-(last_slot+1 if last_slot is not None else 0));last_slot=slot
                    for role in ROLES:
                        if check()>=stamp(self.manifest['end']):break
                        def apply(role=role):
                            value=apps[role].apply(queue,workers[role]);state['applications'][role]=value['reference'];state['queue']=value['queue_reference'];ticks[role]+=1
                            return {k:value[k] for k in ('status','opportunity_count','positive_decisions','worker_receipt_sha256')}
                        operation(role+'_tick',apply)
                remaining=(stamp(self.manifest['start'])+timedelta(seconds=5*(slot+1))-check()).total_seconds()
                if remaining>0:sleeper(min(remaining,max(0,(stamp(self.manifest['end'])-check()).total_seconds())))
            seals={};replays={}
            for role,worker in workers.items():
                def finish(role=role,worker=worker):
                    quotes={};filters={}
                    for pair in sorted({lot['pair'] for lot in worker._source.wallet.snapshot()['open_lots']}):quotes[pair],filters[pair]=market(pair)
                    worker.mark_endpoint(quotes,filters);worker.terminate('completed');seals[role]=worker.finalize()
                    return dict(seal_sha256=seals[role]['seal_sha256'])
                operation(role+'_finalize',finish)
            for role,worker in workers.items():
                def replay(role=role,worker=worker):
                    reg=self.manifest['replays'][role]
                    value=audit_worker_replay(worker.root,expected_registration_sha256=worker.registration_sha256,
                        expected_seal_sha256=seals[role]['seal_sha256'],replay_root=reg['root'],
                        expected_replay_registration_sha256=reg['replay_registration_sha256'],scratch_parent=self.root.parent,clock=self.clock)
                    replays[role]=value;return value
                operation(role+'_independent_replay',replay)
            result=dict(completed_at=check().isoformat(),final_state=state,worker_seals=seals,independent_replays=replays,
                ticks_by_role=ticks,missed_whole_runner_slots=missed_slots,source_audit=source.audit() if hasattr(source,'audit') else source.receipt(),
                queue_audit=queue.audit(),application_audits={r:a.audit() for r,a in apps.items()},journal_head_sha256=head,
                source_poll_completeness_verified=False,scope='bounded_reference_pair_prospective_rehearsal',**FLAGS)
            _write_new(self.root/'terminal.json',result)
            return result
        finally:os.close(fd)


_LOADED_RUNTIME=_runtime()
