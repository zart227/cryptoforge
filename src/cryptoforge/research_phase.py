"""Explicit v5 continuation in the same journal; v3/v4 history stays immutable."""
import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sqlite3

from cryptoforge import research_numeric_controls as numeric, research_run_budget as common
from cryptoforge import research_code_budget as code, research_code_preview as preview
from cryptoforge import research_code_static as static, research_feature_windows as windows
from cryptoforge import research_numeric_worker as worker, llm_research_coordinator as coordinator
from cryptoforge import research_resource_budget as resources
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, timestamp


POLICY = {'schema_version':'coordinated-research-phase-v5',
    'resumed_kinds':['proposal','fit','semantic_fixture','semantic_live','code_check'],
    'numeric_control_mode':'completed_cache_only','preserve_prior_effect_keys':True,
    'new_limits_or_refunds':False,'generic_python_execution_enabled':False}
EXTENSION='coordinated_phase_extension'
ACTIONS='coordinated_phase_actions'
RESOURCES='coordinated_phase_resources'
TABLES=numeric.TABLES|{EXTENSION,ACTIONS,RESOURCES}


def implementation():
    return {'phase':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'numeric':numeric.implementation(),'coordinator':coordinator.implementation()}


_LOADED=implementation()
_POLICY_SHA=digest(POLICY)


def _guard():
    numeric._guard()
    if digest(POLICY)!=_POLICY_SHA or implementation()!=_LOADED:raise ValueError('phase source or fixed policy changed; restart required')


def _history(db):
    values=numeric._history(db)
    for table,ordering in ((numeric.EXTENSION,'id'),(numeric.ACTIONS,'key')):
        values[table]=digest([list(row) for row in db.execute('SELECT * FROM '+table+' ORDER BY '+ordering)])
    return values


def _sha(value):
    return type(value) is str and len(value)==64 and all(char in '0123456789abcdef' for char in value)


def _envelope(raw,sha,kind,observed,observed_sha):
    value=strict_json(raw,max_bytes=2_000_000)
    exact_fields(value,{'result','observed','tokens'} if isinstance(value,dict) and 'tokens' in value else {'result','observed'})
    common.validate_usage(value['observed'],kind)
    if digest(value)!=sha or canonical(value['observed'])!=observed or digest(value['observed'])!=observed_sha:
        raise ValueError('phase result checksum mismatch')
    return value


class ResearchPhaseBudget:
    def __init__(self,previous,policy):
        _guard()
        if type(previous) is not numeric.NumericControlBudget or canonical(policy)!=canonical(POLICY):
            raise ValueError('explicit existing numeric budget and fixed phase policy required')
        self.previous=previous;self.legacy=previous.legacy
        for name in ('path','policy','resource_policy','semantic_policy','semantic_configuration',
                     'code_policy','code_configuration','manifest','clock','timer'):
            setattr(self,name,getattr(self.legacy,name))
        self.configuration={'schema_version':'coordinated-phase-configuration-v5','policy':deepcopy(POLICY),
            'previous_configuration_sha256':digest(previous.configuration),'manifest_sha256':digest(self.manifest),
            'resource_policy_sha256':digest(self.resource_policy),'common_journal_path_sha256':digest(str(self.path)),
            'inherited_limits':{name:deepcopy(getattr(self,name)) for name in ('policy','resource_policy','semantic_policy','code_policy')},
            'implementation':deepcopy(_LOADED)}

    def _now(self):return self.legacy._now()

    @contextmanager
    def _connection(self,write=False):
        _guard()
        if not self.path.is_file():raise ValueError('existing common journal required; no automatic migration')
        db=sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5)
        try:
            if not write:db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            _guard()
            if write:db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()

    def migrate(self):
        with self._connection(True) as db:
            objects=numeric._objects(db)
            if objects=={('table',name) for name in TABLES}:
                self._check(db);payload=self._extension(db);already=True
            else:
                if objects!={('table',name) for name in numeric.TABLES}:raise ValueError('complete v4 journal required')
                self.previous._check(db)
                if db.execute("SELECT count(*) FROM coordinated_numeric_actions WHERE status='reserved'").fetchone()[0]:
                    raise ValueError('unfinished numeric reservations; inactive resolved journal required')
                checksums=_history(db)
                before=self.previous._snapshot(db,self.previous._legacy_check(db))
                payload={'schema_version':'coordinated-phase-extension-v5','configuration':deepcopy(self.configuration),
                    'migration':{'migrated_at':self._now().isoformat(),'frozen_tables_sha256':checksums,
                        'prior_total_actions':before['total_reserved'],'prior_numeric_actions':before['numeric_control_reserved'],
                        'prior_reserved_allocations':before['reserved_allocations']}}
                db.execute('CREATE TABLE coordinated_phase_extension (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,sha TEXT NOT NULL)')
                db.execute('''CREATE TABLE coordinated_phase_actions (key TEXT PRIMARY KEY,kind TEXT NOT NULL,input_sha TEXT NOT NULL,
                    utc_day TEXT NOT NULL,questions INTEGER NOT NULL,status TEXT NOT NULL,reserved_at TEXT NOT NULL,finished_at TEXT,
                    payload TEXT,payload_sha TEXT,observed TEXT,observed_sha TEXT,safe_error TEXT) WITHOUT ROWID''')
                db.execute('''CREATE TABLE coordinated_phase_resources (key TEXT PRIMARY KEY,allocation TEXT NOT NULL,
                    allocation_sha TEXT NOT NULL,measurement TEXT,measurement_sha TEXT) WITHOUT ROWID''')
                db.execute('INSERT INTO coordinated_phase_extension VALUES (1,?,?)',(canonical(payload),digest(payload)))
                self._check(db);already=False
        return {'schema_version':'coordinated-phase-migration-v5','already_migrated':already,'extension':payload,
            'extension_sha256':digest(payload),'new_actions':0,'old_writers_fail_closed':True,
            'journal_relocated_or_reset':False,'numeric_control_cache_only':True}

    def _extension(self,db):
        rows=db.execute('SELECT id,payload,sha FROM coordinated_phase_extension').fetchall()
        if len(rows)!=1 or rows[0][0]!=1:raise ValueError('single phase extension required')
        payload=strict_json(rows[0][1],max_bytes=128000)
        exact_fields(payload,{'schema_version','configuration','migration'})
        if digest(payload)!=rows[0][2] or payload['schema_version']!='coordinated-phase-extension-v5' or canonical(payload['configuration'])!=canonical(self.configuration):
            raise ValueError('phase configuration or checksum changed')
        audit=payload['migration']
        exact_fields(audit,{'migrated_at','frozen_tables_sha256','prior_total_actions','prior_numeric_actions','prior_reserved_allocations'})
        timestamp(audit['migrated_at']);exact_fields(audit['frozen_tables_sha256'],numeric.TABLES)
        if any(not _sha(value) for value in audit['frozen_tables_sha256'].values()):raise ValueError('frozen table digest required')
        return payload

    def _kinds(self):
        return {**self.policy['maximum_by_kind'],'semantic_live':self.semantic_policy['maximum_actions'],
            'code_check':self.code_policy['maximum_actions']}

    def _rows(self,db):
        rows=db.execute('''SELECT a.*,r.key,r.allocation,r.allocation_sha,r.measurement,r.measurement_sha
            FROM coordinated_phase_actions a LEFT JOIN coordinated_phase_resources r ON a.key=r.key''').fetchall()
        if len(rows)!=db.execute('SELECT count(*) FROM coordinated_phase_resources').fetchone()[0]:raise ValueError('phase resource coverage mismatch')
        result=[]
        for row in rows:
            key,kind,input_sha,day,questions,status,reserved,finished,raw,sha,observed,observed_sha,error,rkey,alloc,alloc_sha,measured,measured_sha=row
            if (not _sha(key) or not _sha(input_sha) or kind not in self._kinds() or type(questions) is not int
                    or (not 1<=questions<=16 if kind in ('semantic_fixture','semantic_live') else questions!=0)):
                raise ValueError('bounded phase action required')
            if day!=timestamp(reserved).date().isoformat() or rkey!=key:raise ValueError('phase day or resources mismatch')
            if db.execute('SELECT 1 FROM coordinated_actions WHERE key=? UNION ALL SELECT 1 FROM coordinated_numeric_actions WHERE key=?',(key,key)).fetchone():
                raise ValueError('duplicate historical operation key')
            value=None
            if status=='reserved':
                if any(item is not None for item in (finished,raw,sha,observed,observed_sha,error,measured,measured_sha)):raise ValueError('invalid reserved phase action')
            elif status in ('completed','failed','cancelled','timed_out'):
                timestamp(finished)
                if status=='completed':
                    value=_envelope(raw,sha,kind,observed,observed_sha)
                    if error is not None:raise ValueError('unexpected completed error')
                elif any(item is not None for item in (raw,sha,observed,observed_sha)) or error!='phase_'+status:
                    raise ValueError('unexpected failed phase result')
                if measured is None or measured_sha is None:raise ValueError('finished phase resource observation required')
            else:raise ValueError('unknown phase status')
            allocation=resources._checked(alloc,alloc_sha)
            if allocation!=resources.allocation(self.resource_policy,kind,self.semantic_policy,self.code_policy):raise ValueError('phase allocation differs from original policy')
            measurement=resources._checked(measured,measured_sha) if measured is not None else None
            if measurement is not None:
                exact_fields(measurement,{'origin','handler_wall_ms','tokens','token_origin'})
                expected=resources.measurement(kind,measurement['handler_wall_ms'],value)
                if canonical(measurement)!=canonical(expected):raise ValueError('phase measurement differs from observed operation')
            result.append({'key':key,'kind':kind,'input_sha':input_sha,'day':day,'questions':questions,'status':status,
                'envelope':value,'allocation':allocation,'measurement':measurement})
        return result

    def _check(self,db):
        if (self.path!=self.legacy.path or self.configuration['common_journal_path_sha256']!=digest(str(self.path))
                or self.configuration['previous_configuration_sha256']!=digest(self.previous.configuration)
                or self.configuration['inherited_limits']!={name:getattr(self,name) for name in ('policy','resource_policy','semantic_policy','code_policy')}):
            raise ValueError('inherited phase limits or common journal path changed')
        if any(canonical(getattr(self,name))!=canonical(getattr(self.legacy,name)) for name in
                ('manifest','semantic_configuration','code_configuration')):
            raise ValueError('inherited phase identity configuration changed')
        if numeric._objects(db)!={('table',name) for name in TABLES}:raise ValueError('explicit phase migration required')
        payload=self._extension(db);audit=payload['migration']
        if audit['frozen_tables_sha256']!=_history(db):raise ValueError('prior v3/v4 history changed')
        base=self.previous._snapshot(db,self.previous._legacy_check(db))
        if (type(audit['prior_total_actions']) is not int or type(audit['prior_numeric_actions']) is not int
                or audit['prior_total_actions']!=base['total_reserved'] or audit['prior_numeric_actions']!=base['numeric_control_reserved']
                or audit['prior_reserved_allocations']!=base['reserved_allocations']):raise ValueError('migration changed prior counters or resources')
        self._rows(db)
        return base

    def _snapshot(self,db,base):
        rows=self._rows(db);counts=Counter(base['reserved_by_kind']);statuses=Counter()
        for table in ('coordinated_actions','coordinated_numeric_actions'):
            statuses.update(dict(db.execute('SELECT status,count(*) FROM '+table+' GROUP BY status')))
        allocations=dict(base['reserved_allocations']);legacy_resources=base['legacy_resources']
        known=dict(legacy_resources['provider_tokens_known_subtotal']);unknown=dict(legacy_resources['unknown_token_actions_by_field'])
        wall=legacy_resources['measured_handler_wall_ms_subtotal']+base['numeric_measured_wall_ms'];overruns=base['overrun_actions']
        observed=dict(common.ZERO_USAGE)
        for kind,raw,sha in db.execute("SELECT kind,observed,observed_sha FROM coordinated_actions WHERE status='completed'"):
            value=resources._checked(raw,sha);common.validate_usage(value,kind)
            for name,count in value.items():observed[name]+=count
        day=self._now().date().isoformat();today=base['today_reserved'];questions=base['semantic_questions_reserved']
        for row in rows:
            counts[row['kind']]+=1;statuses[row['status']]+=1;today+=row['day']==day;questions+=row['questions']
            for name,value in row['allocation'].items():allocations[name]+=value
            value=row['measurement'];tokens=value['tokens'] if value else (resources.UNKNOWN_TOKENS if row['kind'] in ('proposal','semantic_live') else resources.ZERO_TOKENS)
            for name,count in tokens.items():
                if count is None:unknown[name]+=1
                else:known[name]+=count
            if value is not None:
                elapsed=value['handler_wall_ms'];wall+=elapsed
                overruns+=int(any(count is not None and count>row['allocation'][name] for name,count in
                    (('input_tokens',tokens['input_tokens']),('output_tokens',tokens['output_tokens']),('wall_ms',elapsed)))
                    or tokens['total_tokens'] is not None and tokens['total_tokens']>sum(row['allocation'][name] for name in ('input_tokens','output_tokens')))
            if row['envelope']:
                for name,count in row['envelope']['observed'].items():observed[name]+=count
        total=base['total_reserved']+len(rows)
        return {'schema_version':'coordinated-research-budget-snapshot-v5','utc_day':day,'manifest':deepcopy(self.manifest),
            'total_reserved_actions':total,'daily_reserved_actions':today,'reserved_by_kind':dict(counts),
            'reserved_semantic_questions':questions,'statuses':dict(statuses),'unknown_work_attempts':total-statuses['completed'],
            'observed_completed_work':observed,'phase_actions':len(rows),'numeric_control_cache_only':True,
            'numeric_control_lifetime_used':base['numeric_control_reserved'],'numeric_control_lifetime_limit':numeric.POLICY['maximum_actions'],
            'resources':{'reserved_allocations':allocations,'provider_tokens_known_subtotal':known,'unknown_token_actions_by_field':unknown,
                'measured_handler_wall_ms_subtotal':wall,'overrun_actions':overruns,'hard_consumption_cap':False,'billing_audited':False},
            'phase_configuration_sha256':digest(self.configuration),'prior_v4_configuration_sha256':digest(self.previous.configuration),
            'candidate_execution_enabled':False,'can_authorize_trades':False}

    def snapshot(self):
        with self._connection() as db:return self._snapshot(db,self._check(db))

    def _key(self,kind,identity,questions):
        fields={'kind':kind,'identity':identity,'questions':questions,'executor':common._LOADED_SHA}
        if kind=='semantic_live':fields['semantic_configuration_sha256']=digest(self.semantic_configuration)
        if kind=='code_check':fields['code_configuration_sha256']=digest(self.code_configuration)
        return digest(fields)

    def _cached(self,db,key,identity,kind):
        old=db.execute('SELECT status,payload,payload_sha,input_sha,observed,observed_sha FROM coordinated_actions WHERE key=?',(key,)).fetchone()
        new=db.execute('SELECT status,payload,payload_sha,input_sha,observed,observed_sha FROM coordinated_phase_actions WHERE key=?',(key,)).fetchone()
        if old and new:raise ValueError('duplicate old/new effect key')
        row=old or new
        if row is None:return None
        if row[0]!='completed':raise ValueError('prior failed or interrupted action; no automatic retry')
        if row[3]!=digest(identity):raise ValueError('cached effective identity mismatch')
        envelope=_envelope(row[1],row[2],kind,row[4],row[5])
        if old:measured=resources.read_measurement(db,key)
        else:
            raw,sha=db.execute('SELECT measurement,measurement_sha FROM coordinated_phase_resources WHERE key=?',(key,)).fetchone()
            measured=resources._checked(raw,sha)
        return envelope,measured,'v3' if old else 'v5'

    def _finish(self,key,status,measured,envelope=None):
        with self._connection(True) as db:
            self._check(db)
            if db.execute('''UPDATE coordinated_phase_actions SET status=?,finished_at=?,payload=?,payload_sha=?,observed=?,observed_sha=?,safe_error=?
                WHERE key=? AND status='reserved' ''',(status,self._now().isoformat(),canonical(envelope) if envelope else None,
                digest(envelope) if envelope else None,canonical(envelope['observed']) if envelope else None,
                digest(envelope['observed']) if envelope else None,None if envelope else 'phase_'+status,key)).rowcount!=1:raise ValueError('phase result immutable')
            if db.execute('UPDATE coordinated_phase_resources SET measurement=?,measurement_sha=? WHERE key=? AND measurement IS NULL',
                (canonical(measured),digest(measured),key)).rowcount!=1:raise ValueError('phase measurement immutable')

    def run(self,kind,identity,operation,*,questions=0,cancel_event=None):
        _guard()
        if kind not in self._kinds():raise ValueError('unsupported phase kind; numeric_control is cache-only')
        if type(questions) is not int or (not 1<=questions<=16 if kind in ('semantic_fixture','semantic_live') else questions!=0):raise ValueError('question count differs from kind')
        if cancel_event is not None and cancel_event.is_set():raise common.BudgetCancelled('cancelled before phase reservation')
        identity=strict_json(canonical(identity),max_bytes=16000);key=self._key(kind,identity,questions)
        allocation=resources.allocation(self.resource_policy,kind,self.semantic_policy,self.code_policy)
        with self._connection(True) as db:
            base=self._check(db);cached=self._cached(db,key,identity,kind)
            if cached is None:
                snapshot=self._snapshot(db,base)
                if snapshot['total_reserved_actions']>=self.policy['total_actions'] or snapshot['daily_reserved_actions']>=self.policy['daily_actions']:
                    raise ValueError('common research action budget exhausted')
                if snapshot['reserved_by_kind'].get(kind,0)>=self._kinds()[kind] or snapshot['reserved_semantic_questions']+questions>self.policy['semantic_questions']:
                    raise ValueError('coordinated kind or question budget exhausted')
                if snapshot['resources']['overrun_actions']:raise ValueError('prior resource overrun; fresh work blocked')
                if any(snapshot['resources']['reserved_allocations'][name]+value>self.resource_policy['total_'+name] for name,value in allocation.items()):
                    raise ValueError('common resource allocation budget exhausted')
                if cancel_event is not None and cancel_event.is_set():raise common.BudgetCancelled('cancelled before phase reservation')
                now=self._now()
                db.execute('INSERT INTO coordinated_phase_actions VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,NULL)',
                    (key,kind,digest(identity),now.date().isoformat(),questions,'reserved',now.isoformat()))
                db.execute('INSERT INTO coordinated_phase_resources VALUES (?,?,?,NULL,NULL)',(key,canonical(allocation),digest(allocation)))
        if cached is None:
            started=self.timer()
            def measure(value=None):return resources.measurement(kind,max(0,(self.timer()-started+999999)//1000000),value)
            try:
                if cancel_event is not None and cancel_event.is_set():raise common.BudgetCancelled('cancelled after phase reservation')
                supplied=operation();raw=canonical(supplied)
                if len(raw.encode())>2_000_000:raise ValueError('bounded phase result required')
                envelope=_envelope(raw,digest(supplied),kind,canonical(supplied['observed']),digest(supplied['observed']))
                measured=measure(envelope);_guard()
            except (common.BudgetCancelled,KeyboardInterrupt):
                self._finish(key,'cancelled',measure());raise common.BudgetCancelled('phase action cancelled') from None
            except common.BudgetTimedOut:self._finish(key,'timed_out',measure());raise
            except Exception:
                self._finish(key,'failed',measure());raise RuntimeError('phase action failed; details not logged') from None
            self._finish(key,'completed',measured,envelope);origin='v5'
        else:envelope,measured,origin=cached
        return {'schema_version':'coordinated-research-result-v5','kind':kind,'operation_key':key,
            'budget_manifest_sha256':digest(self.manifest),'coordinator_cached':cached is not None,'cache_origin':origin,
            'result':envelope['result'],'result_sha256':digest(envelope['result']),'resource_policy_sha256':digest(self.resource_policy),
            'resource_allocation':allocation,'semantic_configuration_sha256':digest(self.semantic_configuration),
            'code_configuration_sha256':digest(self.code_configuration),'phase_configuration_sha256':digest(self.configuration),
            'original_resources':measured,'invocation_resources':{'origin':'coordinator_cache','handler_wall_ms':0,
                'tokens':dict(resources.ZERO_TOKENS),'token_origin':'no_new_completion'} if cached is not None else measured,
            'original_observed':envelope['observed'],'invocation_observed':dict(common.ZERO_USAGE) if cached is not None else envelope['observed']}

    def numeric_cache(self,directory,window_directory,capture):
        _guard();checked=preview.read_preview(directory)
        registration=static._registered_preview(numeric._ReadAdapter(self),checked)
        selected=windows.read_window(window_directory,capture)
        if selected['status']!='prepared':raise ValueError('prepared numerical input required')
        packet,analysis,controls_sha=worker.packet(checked['candidate_text'],selected['payload']['window'])
        identity={'candidate_identity_sha256':checked['candidate_identity_sha256'],'window_identity_sha256':selected['window_identity_sha256'],
            'controls_sha256':controls_sha,'worker_policy_sha256':digest(worker.POLICY)}
        key=digest({'kind':'numeric_control','identity':identity,'configuration_sha256':digest(self.previous.configuration)})
        with self._connection() as db:
            self._check(db)
            row=db.execute('SELECT input_sha,status,payload,payload_sha FROM coordinated_numeric_actions WHERE key=?',(key,)).fetchone()
            if row is None or row[:2]!=(digest(identity),'completed'):raise ValueError('numeric controls are completed-cache only; no fresh attempt')
            result=strict_json(row[2],max_bytes=64000)
            if (digest(result)!=row[3] or result['identity']!=identity or result['packet_sha256']!=digest(packet)
                    or result['registration']!=registration
                    or result['summary']!=worker.validate_result(result['observation'],packet,analysis['required_window_size'])):raise ValueError('historical numeric evidence changed')
        if preview.read_preview(directory)!=checked or windows.read_window(window_directory,capture)!=selected:raise ValueError('numeric cache input changed')
        return {'schema_version':'historical-numeric-cache-v5','operation_key':key,'result':result,'result_sha256':digest(result),
            'original_configuration_sha256':digest(self.previous.configuration),'database_read_only':True,
            'new_actions':0,'new_worker_launches':0,'numeric_control_cache_only':True}


    def static_review(self,directory,policy):
        _guard();static._guard()
        if canonical(policy)!=canonical(static.POLICY):raise ValueError('fixed static policy required')
        checked=preview.read_preview(directory);identity={'candidate_identity_sha256':checked['candidate_identity_sha256']}
        key=self._key('code_check',identity,0)
        with self._connection() as db:
            self._check(db);cached=self._cached(db,key,identity,'code_check')
            if cached is None:raise ValueError('completed code-check registration required')
            envelope,measured,origin=cached;result=envelope['result']
            expected={'schema_version':'budgeted-code-preview-check-v3','candidate_identity_sha256':checked['candidate_identity_sha256'],
                'preview_sha256':result.get('preview_sha256'),'exact_preview_verified':True,'attempt_budget_reserved':True,
                'reservation_scope':'shared_preview_check_only','candidate_execution_budget_reserved':False,
                'candidate_execution_enabled':False,'candidate_executed':False,'syntax_checked':False,'training_executed':False,
                'evidence_ids_verified':False,'model_provenance_verified':False,'can_authorize_trades':False}
            if canonical(result)!=canonical(expected) or not _sha(result['preview_sha256']) or envelope['observed']!=common.ZERO_USAGE:
                raise ValueError('completed exact-preview-only registration required')
        analysis=static._analyze(checked['candidate_text'])
        if preview.read_preview(directory)!=checked:raise ValueError('preview changed during static check')
        _guard();static._guard()
        core={'schema_version':'phase-static-review-v5','candidate_identity_sha256':checked['candidate_identity_sha256'],
            'current_preview_sha256':checked['preview_sha256'],'original_preview_sha256':result['preview_sha256'],
            'registration_operation_key':key,'registration_result_sha256':digest(result),'cache_origin':origin,
            'analysis':analysis,'policy_sha256':digest(policy),'phase_configuration_sha256':digest(self.configuration),
            'new_actions':0,'database_read_only':True,'candidate_execution_enabled':False,'training_executed':False,
            'static_cost_in_common_handler_measurement':False,'model_provenance_verified':False,'can_authorize_trades':False}
        return {**core,'review_sha256':digest(core)}


class PhaseResearchCoordinator(coordinator.ResearchCoordinator):
    """Reuse the existing fixed handlers/identities and their bound inner journals."""
    def __init__(self,*args,phase_policy,**kwargs):
        super().__init__(*args,**kwargs)
        self.budget=ResearchPhaseBudget(numeric.NumericControlBudget(self.budget,numeric.POLICY),phase_policy)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('database','proposal-ledger','semantic-ledger','fit-ledger','semantic-live-ledger','semantic-live-policy',
                 'code-policy','numeric-policy','phase-policy','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--policy',type=Path);parser.add_argument('--resource-policy',type=Path)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('migrate');commands.add_parser('status')
    check=commands.add_parser('code-check');check.add_argument('--preview',type=Path,required=True)
    review=commands.add_parser('static-check');review.add_argument('--preview',type=Path,required=True);review.add_argument('--static-policy',type=Path,required=True)
    cached=commands.add_parser('numeric-cache')
    for name in ('preview','window','capture'):cached.add_argument('--'+name,type=Path,required=True)
    proposal=commands.add_parser('proposal');proposal.add_argument('--experiment-receipt',type=Path,required=True)
    modes=proposal.add_mutually_exclusive_group(required=True);modes.add_argument('--mock-response',type=Path);modes.add_argument('--provider',choices=('openrouter','ollama'))
    proposal.add_argument('--model');proposal.add_argument('--jobpilot-env',type=Path);proposal.add_argument('--ollama-url',default='http://127.0.0.1:11434')
    proposal.add_argument('--require-verified-input-limit',action='store_true')
    fit=commands.add_parser('fit');fit.add_argument('--dataset',type=Path,required=True);fit.add_argument('--protocol',type=Path,required=True);fit.add_argument('--advice-receipt',type=Path)
    fixture=commands.add_parser('semantic-fixture')
    for name in ('request','response'):fixture.add_argument('--'+name,type=Path,required=True)
    fixture.add_argument('--semantic-policy',type=Path)
    args=parser.parse_args(argv)
    protected=[value.resolve() for name,value in vars(args).items() if isinstance(value,Path) and name!='output']
    if any(args.output.resolve()==value or args.output.resolve().is_relative_to(value) for value in protected):parser.error('output must be separate from journals and source bundles')
    def read(path):return coordinator.read_json(path) if path is not None else None
    receipt={'schema_version':'coordinated-research-receipt-v1','phase_schema_version':'research-phase-cli-v5','command':args.command,'status':'started'}
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        stream.write(canonical(receipt)+'\n');stream.flush();os.fsync(stream.fileno())
        try:
            if canonical(read(args.numeric_policy))!=canonical(numeric.POLICY):raise ValueError('fixed previous numeric policy required')
            research=PhaseResearchCoordinator(args.database,proposal_ledger=args.proposal_ledger,semantic_ledger=args.semantic_ledger,
                fit_ledger=args.fit_ledger,semantic_live_ledger=args.semantic_live_ledger,semantic_live_policy=read(args.semantic_live_policy),
                code_check_policy=read(args.code_policy),phase_policy=read(args.phase_policy),policy=read(args.policy),resource_policy=read(args.resource_policy))
            budget=research.budget
            if args.command=='migrate':call=budget.migrate()
            elif args.command=='status':call=None
            elif args.command=='code-check':call=code.check_preview(budget,args.preview)
            elif args.command=='static-check':call=budget.static_review(args.preview,read(args.static_policy))
            elif args.command=='numeric-cache':call=budget.numeric_cache(args.preview,args.window,read(args.capture))
            elif args.command=='proposal':call=research.propose(coordinator.validation_report(read(args.experiment_receipt)),
                mock=read(args.mock_response),provider=args.provider,model=args.model,jobpilot_env=args.jobpilot_env,
                ollama_url=args.ollama_url,require_verified_input_limit=args.require_verified_input_limit)
            elif args.command=='fit':
                advice=coordinator.coordinated_value(read(args.advice_receipt),'proposal') if args.advice_receipt else None
                call=research.fit(args.dataset,read(args.protocol),proposal=advice['advice']['proposal'] if advice else None,report=advice['diagnostics'] if advice else None)
            else:call=research.semantic_fixture(read(args.request),read(args.response),semantic_policy=read(args.semantic_policy))
            receipt.update(status='completed',call=call,budget=budget.snapshot());code_result=0
        except (common.BudgetCancelled,KeyboardInterrupt):receipt.update(status='cancelled',safe_error='phase_cancelled');code_result=130
        except common.BudgetTimedOut:receipt.update(status='timed_out',safe_error='phase_timed_out');code_result=1
        except (ValueError,RuntimeError,OSError,KeyError,TypeError,sqlite3.Error):receipt.update(status='failed',safe_error='phase_inputs_action_or_budget_rejected');code_result=1
        stream.seek(0);stream.truncate();stream.write(canonical(receipt)+'\n');stream.flush();os.fsync(stream.fileno())
    print('Research phase receipt saved; prior limits retained and fresh numeric execution disabled')
    return code_result


if __name__=='__main__':raise SystemExit(main())
