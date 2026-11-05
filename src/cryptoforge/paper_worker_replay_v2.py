"""Independent bounded controller and wallet replay of delivered worker batches.

New contracts bind the explicitly selected LOCAL backend. Sealed verification
uses immutable sources only; production PostgreSQL is neither read nor written.
Delivered-batch correctness is not polling completeness or economic admission.
"""
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from cryptoforge.paper_replay_math_v2 import arithmetic,total,floor_quantity
import json
from pathlib import Path
import tempfile
from time import monotonic_ns
from types import FunctionType
from urllib.parse import urlsplit

from cryptoforge.backend import resolve_backend
from cryptoforge.evidence_segments import canonical, digest, _sync_directory
from cryptoforge.paper_worker_events_v2 import SegmentedWorkerEventLogV2 as SegmentedEventLog
from cryptoforge.native_paper_archive_v2 import NativePaperArchiveV2 as NativePaperArchive
from cryptoforge.paper_capture_v3 import _lease, _metadata, _write_new, stamp
from cryptoforge.paper_capture_state_v2 import GROUPS, _inventory
from cryptoforge.paper_wallet_replay_v2 import ReplayPolicyV2, _Replay, _Scratch, _json, _resources, _separate
from cryptoforge.paper_worker_capture_v2 import _load, audit_worker_capture, runtime_hashes as capture_runtime

SCHEMA = 'independent-local-worker-replay-v2'


def _bounded_source_audit(root, *, expected_registration_sha256, expected_seal_sha256, clock, budget):
    """Keep frozen source checks, adding private per-frame/row budget bindings."""
    class SourceLog(SegmentedEventLog):
        def iter_events(self, **kwargs):
            for record in super().iter_events(**kwargs):
                budget();yield record

    class SourceArchive(NativePaperArchive):
        def iter_rows(self, source):
            for row in super().iter_rows(source):
                budget();yield row

        def _check_seal(self):
            budget();result=super()._check_seal();budget();return result

        def _check_native(self):
            budget();result=super()._check_native();budget();return result

    original=audit_worker_capture
    private=FunctionType(original.__code__, {**original.__globals__,
        'SegmentedEventLog':SourceLog,'NativePaperArchive':SourceArchive},original.__name__,original.__defaults__)
    private.__kwdefaults__=original.__kwdefaults__
    return private(root,expected_registration_sha256=expected_registration_sha256,
        expected_seal_sha256=expected_seal_sha256,clock=clock)


def runtime_hashes():
    base = Path(__file__).parent
    runner = base.parents[1]/'scripts/audit_paper_worker_replay_v2.py'
    dependencies = ['paper_worker_replay_v2.py','paper_wallet_replay_v2.py','paper_replay_math_v2.py','backend.py','live_learning_protocol.py']
    return {**capture_runtime(), **{name:digest((base/name).read_bytes()) for name in dependencies},
            'worker_replay_runner':digest(runner.read_bytes())}


def _local_identity(identity):
    if type(identity) is not dict or set(identity) != {'name','api_origin'} or identity['name'] != 'local':
        raise ValueError('explicit local backend identity required; no cloud fallback')
    parsed = urlsplit(identity['api_origin'])
    if (parsed.scheme != 'http' or parsed.hostname not in {'localhost','127.0.0.1','::1'} or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path):
        raise ValueError('credential-free original loopback backend identity required')
    return identity


def register_worker_replay(root, *, capture_root, expected_registration_sha256, policy, backend_env, clock=None):
    capture_root, registration, protocol, lifecycle, _ = _load(capture_root, expected_registration_sha256)
    if type(policy) is not ReplayPolicyV2:raise ValueError('typed bounded worker replay policy required')
    root = Path(root).absolute();_separate(root,capture_root);_separate(root,Path(protocol['kernel_root']))
    now = stamp((clock or (lambda:datetime.now(UTC)))())
    if not stamp(registration['registered_at']) <= now < stamp(protocol['start']):
        raise ValueError('independent worker replay contract must precede original start')
    minimum = 8*(protocol['storage_policy']['maximum_record_bytes']+protocol['native_policy']['maximum_batch_bytes'])
    if policy.maximum_active_bytes < minimum:
        raise ValueError('worker replay active budget must cover bounded frames/projections')
    backend = resolve_backend(backend_env)
    identity = _local_identity(dict(name=backend.name,api_origin=backend.url))
    if identity != protocol['kernel_contract']['source_backend']:
        raise ValueError('independent replay backend must equal the original kernel local backend')
    measured = _resources(policy,root)
    if (measured['free_disk_bytes'] < lifecycle.minimum_free_disk_bytes+policy.maximum_scratch_bytes
            or measured['available_memory_bytes'] < lifecycle.minimum_available_memory_bytes):
        raise ValueError('combined original capture/replay resource reservation insufficient')
    root.mkdir(mode=0o700,parents=True,exist_ok=False)
    value = dict(schema_version=SCHEMA,root=str(root),capture_root=str(capture_root),
        capture_registration_sha256=expected_registration_sha256,capture_protocol_sha256=registration['protocol_sha256'],
        candidate_sha256=protocol['candidate_sha256'],role=protocol['role'],start=protocol['start'],end=protocol['end'],
        registered_at=now.isoformat(),policy=asdict(policy),source_backend=identity,
        registration_resources=measured,runtime=runtime_hashes(),arithmetic_contract=dict(precision=2048,allocation_places=512,integer_ratio_sizing=True),
        kernel_contract_sha256=protocol['kernel_contract_sha256'],kernel_registration_sha256=protocol['kernel_registration_sha256'],
        native_manifest_sha256=registration['native_manifest_sha256'],native_ready_sha256=registration['native_ready_sha256'],
        research_only=True,live_eligible=False)
    if not now <= stamp((clock or (lambda:datetime.now(UTC)))()) < stamp(protocol['start']):
        raise ValueError('independent replay setup missed original start; no adoption')
    pin = _write_new(root/'registration.json',value)
    if not now <= stamp((clock or (lambda:datetime.now(UTC)))()) < stamp(protocol['start']):
        (root/'registration.json').unlink();_sync_directory(root)
        raise ValueError('independent replay durable registration missed original start; no adoption')
    return dict(root=str(root),replay_registration_sha256=pin,source_backend=identity,live_admission_granted=False)


def _registration(root, pin, capture_root, registration, protocol):
    if root is None:raise ValueError('original prospective independent worker replay contract required')
    root = Path(root).absolute();_separate(root,capture_root);_separate(root,Path(protocol['kernel_root']))
    value = _metadata(root/'registration.json',pin)
    if (set(p.name for p in root.iterdir()) != {'registration.json'} or value.get('schema_version') != SCHEMA
            or value.get('root') != str(root) or value.get('capture_root') != str(capture_root)
            or value.get('capture_registration_sha256') != digest(canonical(registration))
            or value.get('capture_protocol_sha256') != registration['protocol_sha256']
            or any(value.get(k) != protocol[k] for k in ('candidate_sha256','role','start','end'))
            or not stamp(registration['registered_at']) <= stamp(value['registered_at']) < stamp(protocol['start'])
            or value.get('runtime') != runtime_hashes() or value.get('research_only') is not True or value.get('live_eligible') is not False):
        raise ValueError('original independent worker replay identity/runtime required')
    _local_identity(value['source_backend'])
    if (value['source_backend'] != protocol['kernel_contract']['source_backend']
            or value.get('arithmetic_contract') != dict(precision=2048,allocation_places=512,integer_ratio_sizing=True)
            or any(value.get(k)!=protocol[k] for k in ('kernel_contract_sha256','kernel_registration_sha256'))
            or any(value.get(k)!=registration[k] for k in ('native_manifest_sha256','native_ready_sha256'))):
        raise ValueError('original replay kernel/archive/arithmetic binding differs')
    policy = ReplayPolicyV2(**value['policy'])
    if policy.maximum_active_bytes < 8*(protocol['storage_policy']['maximum_record_bytes']+protocol['native_policy']['maximum_batch_bytes']):
        raise ValueError('original independent worker replay active capacity insufficient')
    measured = value['registration_resources']
    for key,floor in [('available_memory_bytes',max(policy.minimum_available_memory_bytes,protocol['lifecycle']['minimum_available_memory_bytes'])),
                      ('free_disk_bytes',max(policy.minimum_free_disk_bytes,protocol['lifecycle']['minimum_free_disk_bytes']+policy.maximum_scratch_bytes))]:
        if type(measured.get(key)) is not int or measured[key] < floor:raise ValueError('original replay resource registration differs')
    return root,value,policy


class _WorkerReplay(_Replay):
    def __init__(self,*args):
        self.worker_events,self.latest_buys = 0,{}
        super().__init__(*args)

    def _put(self,name,row):
        super()._put(name,row)
        if name == 'worker.worker_events':
            # Reports/results are immutable and never needed as controller state.
            # Keep their exact key/hash, as with immutable wallet history.
            self.scratch.db.execute("UPDATE rows SET raw=NULL WHERE source=? AND key=?",(name,self.scratch._key(name,row[0])))
        if name == 'wallet.intents':
            if row[5] == 'pending':self.scratch.put('replay.pending',row)
            else:
                deleted = self.scratch.db.execute("DELETE FROM rows WHERE source='replay.pending' AND key=?",(row[0],)).rowcount
                self.scratch.count -= deleted

    def pending(self):
        rows = []
        for key, in self.scratch.db.execute("SELECT key FROM rows WHERE source='replay.pending' ORDER BY key"):
            if len(rows) >= self.policy.maximum_active_rows:raise ValueError('independent pending projection budget exhausted')
            rows.append(self.scratch.get('replay.pending',key))
        if len(rows) != self.pending_count:raise ValueError('independent pending index differs')
        return sorted(rows,key=lambda r:(r[3],r[0]))

    def batches(self,rows):
        selected = []
        for row in rows:
            identity = digest((row['candidate_sha256']+'|'+row['opportunity']).encode())
            key = self.scratch.get('replay.prediction',identity)
            raw = canonical(row).decode()
            if key is not None and key != [identity,raw]:raise ValueError('immutable opportunity changed between batches/restarts')
            if key is None:self.scratch.put('replay.prediction',[identity,raw])
            if self.scratch.get('worker.seen_predictions',identity) is None:selected.append(row)
        return sorted(selected,key=lambda r:(stamp(r['predicted_at']),r['opportunity']))

    def operation(self,prepared,complete):
        name,inputs = prepared['operation'],prepared['inputs']
        if not name.startswith('worker_'):
            super().operation(prepared,complete)
            if name == 'execute':
                result = complete['result']
                if result['status'] == 'filled' and not result.get('duplicate'):
                    fill = result['fill']
                    if fill['side'] == 'Buy':
                        self.latest_buys[fill['pair']] = {k:fill[k] for k in ('intent_id','filled_at','price','fill_sequence')}
                    pairs = {r[1] for r in self.lots.values()}
                    self.latest_buys = {p:v for p,v in self.latest_buys.items() if p in pairs}
            return
        self.changes = {};self._begin_clocks(complete)
        if name == 'worker_enqueue':
            now=self._clock() if self._leaf_clocks else stamp(prepared['at'])
            identity,source_key = inputs['intent_id'],inputs['source_key']
            if (inputs['side'] not in {'Buy','Sell'} or not inputs['pair'].endswith('/USDT')
                    or not 0 <= (now-stamp(inputs['created_at'])).total_seconds() <= 5):
                raise ValueError('independent worker enqueue clock/identity differs')
            exists = (self.scratch.get('worker.intent_links',identity) or self.scratch.get('wallet.intents',identity)
                or source_key and self.scratch.get('worker.seen_predictions',source_key))
            result = not bool(exists)
            if result:
                if not self._leaf_clocks:raise ValueError('independent enqueue native clock missing')
                self._put('wallet.intents',[identity,inputs['pair'],inputs['side'],inputs['created_at'],now.isoformat(),'pending',None])
                self._put('worker.intent_links',[identity,_json(inputs['payload'])])
                if source_key:self._put('worker.seen_predictions',[source_key,'queued',now.isoformat()])
        elif name == 'worker_seen':
            now=self._clock() if self._leaf_clocks else stamp(prepared['at'])
            result = None
            if self.scratch.get('worker.seen_predictions',inputs['identity']) is None:
                if not self._leaf_clocks:raise ValueError('independent seen native clock missing')
                self._put('worker.seen_predictions',[inputs['identity'],inputs['status'],now.isoformat()])
        elif name == 'worker_event':
            now=self._clock()
            result = None;self.worker_events += 1
            self._put('worker.worker_events',[self.worker_events,now.isoformat(),_json(inputs['payload'])])
        else:raise ValueError('unknown independent worker mutation')
        ordered = sorted(self.changes.values(),key=lambda c:(GROUPS.index(c['source']),c['key']))
        if result != complete['result'] or ordered != complete['changes'] or self.summary != complete['after']['sources']:
            raise ValueError('independent worker atomic state/delta/result mismatch')
        self._finish_clocks();self._guard();self.scratch.db.commit()


class _Controller:
    """A separate coroutine states the next exact controller I/O or mutation."""
    def __init__(self,replay,protocol,event):
        self.r,self.p,self.event = replay,protocol,event
        self.quotes,self.rules,self.errors,self.results = {},{},{},[]
        self.rows,self.pending = [],[]

    def guard(self):
        active = dict(lots=self.r.lots,filters=self.r.filters,anchors=self.r.anchors,latest=self.r.latest,
            window_latest=self.r.window_latest,lot_order=self.r.lot_order,leaf_clocks=self.r._leaf_clocks,
            latest_buys=self.r.latest_buys,quotes=self.quotes,rules=self.rules,errors=self.errors,
            results=self.results,predictions=self.rows,pending=self.pending)
        size = len(canonical(active))
        self.r.peak_active_bytes = max(self.r.peak_active_bytes,size)
        if size > self.r.policy.maximum_active_bytes:raise ValueError('independent controller active bytes exhausted')

    def enqueue(self,identity,pair,side,created,payload,source_key=None):
        return ('action','worker_enqueue',dict(intent_id=identity,pair=pair,side=side,created_at=created.isoformat(),payload=payload,source_key=source_key))

    def run(self):
        if self.event['mode'] == 'endpoint':
            return (yield ('action','mark',self.event['inputs']))
        yield ('action','compact',{})
        self.rows = self.r.batches(self.event['inputs']['predictions'])
        now = yield ('clock',)
        start_wall = yield ('monotonic',)
        start,end,cutoff = stamp(self.p['start']),stamp(self.p['end']),stamp(self.p['plan']['entry_cutoff'])
        if not start <= now < end:raise ValueError('independent worker decision outside window')
        new,requests = 0,0
        config,policy = self.r.config,self.p['worker_policy']
        for row in self.rows:
            if row['candidate_sha256'] != self.p['candidate_sha256']:continue
            identity = digest((row['candidate_sha256']+'|'+row['opportunity']).encode())
            predicted = stamp(row['predicted_at'])
            if not start <= predicted < end:continue
            status = ('outside_window_or_future' if predicted > now else
                'unverified_prediction_observation' if not row.get('observed_at') or not predicted <= stamp(row['observed_at']) <= now else
                'candidate_rejected' if not row['would_enter'] else
                'source_prediction_expired' if now >= predicted+timedelta(seconds=config.signal_expiry_seconds) else
                'paper_entry_window_finished' if now >= cutoff else None)
            if status:
                yield ('action','worker_seen',dict(identity=identity,status=status));continue
            if new >= policy['runtime']['maximum_new_signals_per_tick']:break
            deadline = predicted+timedelta(seconds=config.signal_expiry_seconds)
            queued = yield self.enqueue('paper-buy:'+identity,row['pair'],'Buy',now,
                dict(source_prediction=row,source_deadline=deadline.isoformat()),identity)
            if queued:new += 1
        self.pending = self.r.pending()
        for intent in self.pending:
            if intent[2]=='Buy' and (yield ('clock',))>=cutoff:
                yield ('action','cancel_pending',dict(intent_id=intent[0],reason='paper_entry_window_finished'))
        self.pending = self.r.pending()
        pairs = sorted({r[1] for r in self.r.lots.values()}|{r[1] for r in self.pending})
        for pair in pairs:
            wall = yield ('monotonic',)
            if wall-start_wall >= policy['runtime']['wall_budget_seconds']:
                self.errors[pair] = 'paper_tick_wall_budget_exhausted';continue
            observed = yield ('provider','market',pair)
            if observed['error'] is not None:self.errors[pair] = observed['error']
            else:
                self.quotes[pair],self.rules[pair] = observed['result']['quote'],observed['result']['filters'];requests += 1
        mark_inputs = dict(quotes=self.quotes,filters=self.rules)
        mark = yield ('action','mark',mark_inputs)
        for intent in sorted(self.pending,key=lambda r:(r[2]=='Buy',r[3],r[0])):
            if intent[2]=='Buy' and (yield ('clock',))>=cutoff:
                yield ('action','cancel_pending',dict(intent_id=intent[0],reason='paper_entry_window_finished'));continue
            link = self.r.scratch.get('worker.intent_links',intent[0])
            link = json.loads(link[1]) if link else {}
            if link.get('source_deadline'):
                observed = yield ('clock',)
                if observed >= stamp(link['source_deadline']):
                    yield ('action','cancel_pending',dict(intent_id=intent[0],reason='source_prediction_expired'));continue
            pair = intent[1]
            if pair not in self.quotes:continue
            result = yield ('action','execute',dict(intent_id=intent[0],quote=self.quotes[pair],filters=self.rules[pair],entry_cutoff=self.p['plan']['entry_cutoff']))
            self.results.append(result['status'])
            yield ('action','worker_event',dict(payload=dict(intent=intent[0],result=result)))
            mark = yield ('action','mark',mark_inputs)
        self.pending = self.r.pending()
        selling = {r[1] for r in self.pending if r[2]=='Sell'}
        by_pair = {}
        for lot in sorted(self.r.lots.values(),key=lambda r:self.r.lot_order[r[0]]):by_pair.setdefault(lot[1],[]).append(lot)
        for pair,lots in by_pair.items():
            if pair in selling or pair not in self.quotes:continue
            quote,rules = self.quotes[pair],self.rules[pair]
            observed = yield ('clock',)
            if not timedelta(0) <= observed-stamp(quote['observed_at']) <= timedelta(seconds=config.quote_max_age_seconds):
                self.errors['exit:'+pair] = 'stale_exit_quote';continue
            quantity = total(D(r[3]) for r in lots);step = D(rules['quantity_step'])
            sellable = floor_quantity(quantity,step)
            if sellable*D(quote['bid'])*(1-config.slippage) < D(rules['minimum_notional']):continue
            latest = self.r.latest_buys[pair]
            elapsed = ((yield ('clock',))-stamp(latest['filled_at'])).total_seconds()
            bid,entry,stop = D(quote['bid']),D(latest['price']),D(policy['exits']['stop_fraction'])
            hold = policy['exits']['maximum_hold_seconds']
            if not bid.is_finite() or bid <= 0 or not entry.is_finite() or entry <= 0 or not stop.is_finite() or not 0 < stop < 1 or hold <= 0 or elapsed < 0:
                raise ValueError('independent price/time exit inputs invalid')
            reason = 'paper_hard_stop' if bid <= entry*(1-stop) else 'paper_maximum_hold' if elapsed >= hold else None
            if (yield ('clock',)) >= cutoff:reason = 'paper_window_closeout'
            elif reason is None and policy['exits'].get('shared_exit_signal'):
                if (yield ('monotonic',))-start_wall >= policy['runtime']['wall_budget_seconds']:
                    self.errors['exit:'+pair] = 'paper_exit_wall_budget_exhausted';continue
                indicator = yield ('provider','exit',pair)
                if indicator['error'] is not None:self.errors['exit:'+pair] = indicator['error']
                elif indicator['result']['exits']:reason = 'shared_exit_signal'
            if reason:
                inventory = digest(json.dumps([(r[0],r[3]) for r in lots],sort_keys=True).encode())
                identity = 'paper-sell:'+inventory+':'+(yield ('clock',)).isoformat()
                created = yield ('clock',)
                yield self.enqueue(identity,pair,'Sell',created,dict(exit_reason=reason,inventory_key=inventory))
                yield ('action','worker_event',dict(payload=dict(intent=identity,exit_reason=reason)))
        report = dict(producer_version=self.p['kernel_contract']['producer_version'],status='paper_tick_complete',new_intents=new,market_observations=requests,
            fills_processed=self.results,errors=self.errors,equity_known=mark['equity'] is not None,live_promotion_allowed=False,mode='paper')
        yield ('action','worker_event',dict(payload=report))
        return report


def _audit_worker_replay(capture_root, *, expected_registration_sha256, expected_seal_sha256=None,
        replay_root=None, expected_replay_registration_sha256=None, scratch_parent=None, clock=None):
    capture_root,registration,protocol,lifecycle,_ = _load(capture_root,expected_registration_sha256)
    output = dict(schema_version=SCHEMA,capture_registration_sha256=expected_registration_sha256,
        source_poll_completeness_verified=False,full_worker_decision_replay_pass=False,full_fifo_replay_pass=False,
        coverage_evidence_pass=False,full_worker_or_host_qualified=False,paper_evidence_pass=False,
        economic_profitability_established=False,live_admission_granted=False)
    if stamp((clock or (lambda:datetime.now(UTC)))()) < stamp(protocol['end']):
        return {**output,'status':'sealed_until_capture_end','performance_hidden':True}
    replay_root,replay,policy = _registration(replay_root,expected_replay_registration_sha256,capture_root,registration,protocol)
    parent = Path(scratch_parent or tempfile.gettempdir()).absolute()
    if parent.resolve() != parent or not parent.is_dir() or any(parent == p or p in parent.parents for p in (capture_root,replay_root,Path(protocol['kernel_root']))):
        raise ValueError('private scratch parent must be outside evidence roots')
    def resources():
        measured=_resources(policy,parent)
        if (measured['available_memory_bytes']<lifecycle.minimum_available_memory_bytes
                or measured['free_disk_bytes']<lifecycle.minimum_free_disk_bytes+policy.maximum_scratch_bytes):
            raise ValueError('original combined capture/replay resource floor failed')
    resources();started = monotonic_ns();budget_checks=0
    def budget():
        nonlocal budget_checks
        if monotonic_ns()-started > policy.maximum_wall_seconds*1000000000:raise ValueError('independent worker replay wall budget exhausted')
        budget_checks+=1
        if budget_checks%128==0:resources()
    trace = _bounded_source_audit(capture_root,expected_registration_sha256=expected_registration_sha256,
        expected_seal_sha256=expected_seal_sha256,clock=clock,budget=budget)
    budget()
    with _lease(capture_root,writer=False):
        _inventory(capture_root);seal = _metadata(capture_root/'sealed.json',expected_seal_sha256)
        log = SegmentedEventLog._load(capture_root/'storage',registration['storage_manifest_sha256'])
        source = NativePaperArchive.reader(capture_root/'native',expected_manifest_sha256=registration['native_manifest_sha256'],
            expected_ready_sha256=registration['native_ready_sha256'],expected_seal_sha256=seal['native_seal_sha256'])
        with tempfile.TemporaryDirectory(prefix='cryptoforge-worker-replay-',dir=parent) as temporary:
            temporary = Path(temporary);_separate(temporary,capture_root);_separate(temporary,replay_root);_separate(temporary,Path(protocol['kernel_root']))
            scratch = _Scratch(temporary/'state.sqlite',policy)
            try:
                wallet = _WorkerReplay(protocol,registration['native_manifest_sha256'],scratch,policy,lifecycle)
                controller = generator = wanted = pending = terminal = expected_result = None
                ticks = count = 0
                native_clocks=[]
                def advance(value=None,first=False):
                    nonlocal wanted,expected_result
                    try:wanted = next(generator) if first else generator.send(value)
                    except StopIteration as done:wanted,expected_result = None,done.value
                for record in log.iter_events(expected_head_sha256=seal['head_sha256'],expected_catalog_sha256=seal['catalog_sha256']):
                    count += 1;budget();kind,event = record['kind'],record['payload'];phase = event.get('phase')
                    if count % 128 == 0:_resources(policy,temporary)
                    if kind == 'genesis':
                        if event['after']['sources'] != wallet.summary:raise ValueError('independent worker initial state differs')
                    elif kind == 'terminated':
                        if generator is not None:raise ValueError('independent controller unfinished at terminal')
                        wallet.coverage.invalidate(event['at']);terminal = event
                    elif phase == 'tick' and kind == 'prepared':
                        if generator is not None or event['before']['sources'] != wallet.summary:
                            raise ValueError('independent tick initial state differs')
                        controller = _Controller(wallet,protocol,event);generator = controller.run();expected_result = None
                        advance(first=True)
                    elif phase == 'tick' and kind == 'complete':
                        if generator is None or wanted is not None or expected_result != event['result'] or event['after']['sources'] != wallet.summary:
                            raise ValueError('independent whole worker report/decision sequence differs')
                        ticks += int(controller.event['mode']=='tick');generator = controller = None
                    elif phase in {'clock','monotonic'}:
                        if phase=='clock' and event['action_prepared_seq'] is not None:
                            if pending is None or pending['phase']!='action' or event['action_prepared_seq']!=pending['sequence']:
                                raise ValueError('independent native clock parent/order differs')
                            native_clocks.append(event['at']);continue
                        if pending is not None:raise ValueError('independent controller clock inside pending call')
                        if wanted != (phase,):raise ValueError('independent controller clock/order differs')
                        advance(stamp(event['at']) if phase=='clock' else event['value'])
                    elif kind == 'prepared':
                        actual = (('action',event['operation'],event['inputs']) if phase=='action' else ('provider',phase,event['pair']))
                        if actual != wanted or pending is not None:raise ValueError('independent controller decision/request/order differs')
                        if event.get('before',{}).get('sources',wallet.summary) != wallet.summary:
                            raise ValueError('independent native action before-state differs')
                        if phase=='action' and event['operation'] in {'mark','execute'}:wallet.coverage.invalidate(event['at'])
                        pending = dict(event,sequence=record['sequence']);native_clocks=[]
                    elif kind == 'complete':
                        if pending is None:raise ValueError('independent action/provider missing preparation')
                        if phase=='action':
                            if event['native_clocks']!=native_clocks:raise ValueError('independent original native clocks differ')
                            wallet.operation(pending,event);result = event['result']
                        else:result = dict(result=event['result'],error=event['error'])
                        pending = None;advance(result)
                    else:raise ValueError('unexpected independent controller record')
                    if controller is not None:controller.guard()
                if (generator is not None or pending is not None or terminal is None or count != seal['sequence']
                        or wallet.summary != seal['native_after']['sources']):raise ValueError('independent final worker source state differs')
                coverage = wallet.coverage.finish()
                final_known = wallet.latest is not None and wallet.latest['equity'] is not None
                window_known=wallet.window_latest is not None and wallet.window_latest['equity'] is not None
                dust = set(wallet.window_latest['nontradable_small_basis_pairs']) if window_known else set()
                material = {r[1] for r in wallet.lots.values()}-dust
                checks = dict(completed=terminal['reason']=='completed',coverage=coverage['coverage_pass'],covers_end=coverage['covers_end'],
                    final_valuation_known=final_known,final_valuation_source_verified=wallet.latest_source_qualified,
                    window_valuation_known=window_known,window_valuation_source_verified=wallet.window_source_qualified,
                    no_pending_intents=wallet.pending_count==0,closeout_no_material_inventory=not material,
                    raw_fill_sources=wallet.raw_fills==wallet.fills,whole_tick_wall_budget=trace['operation_wall_budget_pass'])
                _resources(policy,temporary);budget()
                result = {**output,'status':'independent_delivered_worker_decisions_and_wallet_replayed','performance_hidden':False,
                    'source_backend':replay['source_backend'],'replay_registration_sha256':expected_replay_registration_sha256,
                    'worker_source_trace_pass':True,'full_worker_decision_replay_pass':True,'full_fifo_replay_pass':True,
                    'coverage_evidence_pass':all(checks.values()),'lifecycle_checks':checks,'coverage':coverage,
                    'events_checked':count,'ticks_checked':ticks,'marks_checked':wallet.marks,'fills_checked':wallet.fills,
                    'segments_checked':wallet.segments,'worker_events_checked':wallet.worker_events,'final_cash':wallet.cash,
                    'final_equity':wallet.latest['equity'] if final_known else None,
                    'final_equity_observed_at':wallet.latest['observed_at'] if final_known else None,
                    'final_valuation_after_window':final_known and stamp(wallet.latest['observed_at'])>stamp(protocol['end']),
                    'endpoint_observations_backfill_window':False,'pending_intents':wallet.pending_count,
                    'last_in_window_equity':wallet.window_latest['equity'] if window_known else None,
                    'last_in_window_equity_observed_at':wallet.window_latest['observed_at'] if window_known else None,
                    'allocated_realized_pnl':str(wallet.realized),'fill_fee_quote_equivalent':str(wallet.fees),
                    'material_inventory_pairs':sorted(material),'scratch_rows':scratch.count,'scratch_bytes':scratch.path.stat().st_size,
                    'peak_active_bytes':wallet.peak_active_bytes,'scope':'delivered_batches_only_not_poll_completeness_strategy_profit_or_host_admission'}
            finally:scratch.db.close()
        source._check_seal();_load(capture_root,expected_registration_sha256)
        if _metadata(capture_root/'sealed.json',expected_seal_sha256) != seal:raise ValueError('worker source seal changed during replay')
        if _registration(replay_root,expected_replay_registration_sha256,capture_root,registration,protocol)[1] != replay:
            raise ValueError('worker replay registration changed during audit')
        budget()
    return result


def audit_worker_replay(capture_root, *, expected_registration_sha256, expected_seal_sha256=None,
        replay_root=None, expected_replay_registration_sha256=None, scratch_parent=None, clock=None):
    # Fresh private arithmetic context: caller precision/traps cannot alter proof.
    with arithmetic():
        return _audit_worker_replay(capture_root,expected_registration_sha256=expected_registration_sha256,
            expected_seal_sha256=expected_seal_sha256,replay_root=replay_root,
            expected_replay_registration_sha256=expected_replay_registration_sha256,scratch_parent=scratch_parent,clock=clock)
