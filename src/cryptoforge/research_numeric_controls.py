"""Explicit sealed arithmetic-control phase in the existing common SQLite journal.

The six v3 tables remain immutable. Legacy writers refuse the two added tables;
this prototype exposes only fixed numeric controls, never an arbitrary handler.
"""
import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from cryptoforge import research_code_budget as code, research_code_preview as preview
from cryptoforge import research_code_static as static, research_feature_windows as windows
from cryptoforge import research_numeric_worker as worker, research_run_budget as common
from cryptoforge.research_resource_budget import resource_snapshot
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp


POLICY = {'schema_version':'coordinated-numeric-controls-v4','maximum_actions':3,
    'input_tokens':0,'output_tokens':0,'wall_ms':20000,'free_only':True,
    'stage':'sealed_arithmetic_controls','generic_python_execution_enabled':False}
LEGACY = {*code.HISTORY_TABLES, code.CODE_TABLE}
EXTENSION = 'coordinated_numeric_extension'
ACTIONS = 'coordinated_numeric_actions'
TABLES = LEGACY | {EXTENSION, ACTIONS}


def implementation():
    return {'numeric_controls':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'worker':worker.implementation(),'legacy':code.implementation()}


_LOADED = implementation()


def _guard():
    worker.guard()
    if implementation() != _LOADED: raise ValueError('numeric controls source changed; restart required')


def _history(db):
    result = {name:code.history_digest(db,name) for name in code.HISTORY_TABLES}
    result[code.CODE_TABLE] = digest([list(row) for row in db.execute('SELECT * FROM coordinated_code_extension ORDER BY id')])
    return result


def _objects(db):
    return set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))


class _ReadAdapter:
    """Only the exact read interface required by the existing registration verifier."""
    def __init__(self, owner):
        self.owner = owner
        for name in ('path','code_configuration','manifest','resource_policy','semantic_policy','code_policy'):
            setattr(self, name, getattr(owner.legacy, name))
    def _check_objects(self, db):
        self.owner._check(db); return set(LEGACY)
    def _check_manifest(self, db): self.owner.legacy._check_manifest(db)
    def _check_extension(self, db, tables): return self.owner.legacy._check_extension(db,tables)


class NumericControlBudget:
    def __init__(self, legacy, policy):
        if type(legacy) is not common.ResearchRunBudget or legacy.code_configuration is None:
            raise ValueError('explicit existing v3 budget required')
        if canonical(policy) != canonical(POLICY): raise ValueError('fixed numeric control policy required')
        self.legacy = legacy
        self.configuration = {'schema_version':'numeric-control-configuration-v4','policy':strict_json(canonical(POLICY)),
            'manifest_sha256':digest(legacy.manifest),'code_configuration_sha256':digest(legacy.code_configuration),
            'worker_policy_sha256':digest(worker.POLICY),'implementation':_LOADED}

    @contextmanager
    def _connection(self, write=False):
        _guard()
        if not self.legacy.path.is_file() or self.legacy.path.is_symlink(): raise ValueError('existing common journal required')
        db = sqlite3.connect(self.legacy.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=5)
        try:
            if not write: db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            _guard()
            if write: db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()

    def _legacy_check(self, db):
        self.legacy._check_manifest(db); self.legacy._check_extension(db,LEGACY)
        for kind,questions,status,raw,sha,observed,observed_sha in db.execute(
                'SELECT kind,questions,status,payload,payload_sha,observed,observed_sha FROM coordinated_actions'):
            if kind not in {*self.legacy.policy['maximum_by_kind'],'semantic_live','code_check'} or type(questions) is not int:
                raise ValueError('invalid legacy action')
            if (not 1 <= questions <= 16 if kind in ('semantic_live','semantic_fixture') else questions != 0): raise ValueError('invalid legacy questions')
            if status == 'completed':
                envelope = strict_json(raw,max_bytes=2_000_000)
                exact_fields(envelope,{'result','observed','tokens'} if 'tokens' in envelope else {'result','observed'})
                common.validate_usage(envelope['observed'],kind)
                if digest(envelope) != sha or canonical(envelope['observed']) != observed or digest(envelope['observed']) != observed_sha:
                    raise ValueError('corrupt legacy result')
            elif status in ('failed','cancelled','timed_out'):
                if any(value is not None for value in (raw,sha,observed,observed_sha)): raise ValueError('unexpected legacy result')
            else: raise ValueError('unresolved legacy reservation')
        return resource_snapshot(db,self.legacy.resource_policy,self.legacy.semantic_policy,self.legacy.code_policy)

    def migrate(self):
        """One explicit irreversible phase seal; no automatic migration or journal copy."""
        with self._connection(True) as db:
            objects = _objects(db)
            if objects == {('table',name) for name in TABLES}:
                extension, _ = self._check(db); already = True
            else:
                if objects != {('table',name) for name in LEGACY}: raise ValueError('complete inactive v3 journal required')
                self._legacy_check(db)
                extension = {'schema_version':'numeric-control-extension-v4','configuration':self.configuration,
                    'migration':{'migrated_at':self.legacy._now().isoformat(),'sealed_tables_sha256':_history(db),
                        'prior_action_count':db.execute('SELECT count(*) FROM coordinated_actions').fetchone()[0]}}
                db.execute('CREATE TABLE coordinated_numeric_extension (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, sha TEXT NOT NULL)')
                db.execute('''CREATE TABLE coordinated_numeric_actions (key TEXT PRIMARY KEY, input_sha TEXT NOT NULL,
                    utc_day TEXT NOT NULL, status TEXT NOT NULL, reserved_at TEXT NOT NULL, finished_at TEXT,
                    payload TEXT, payload_sha TEXT, measured_wall_ms INTEGER, safe_error TEXT) WITHOUT ROWID''')
                db.execute('INSERT INTO coordinated_numeric_extension VALUES (1,?,?)',(canonical(extension),digest(extension)))
                self._check(db); already = False
        return {'schema_version':'numeric-control-migration-v4','already_migrated':already,
            'extension':extension,'extension_sha256':digest(extension),'new_actions':0,
            'legacy_writers_sealed':True,'journal_relocated_or_reset':False}

    def _check(self, db):
        if _objects(db) != {('table',name) for name in TABLES}: raise ValueError('explicit numeric migration required')
        self.legacy._check_manifest(db); self.legacy._check_extension(db,LEGACY)
        rows = db.execute('SELECT payload,sha FROM coordinated_numeric_extension').fetchall()
        if len(rows) != 1: raise ValueError('numeric extension missing')
        raw,sha = rows[0]; extension = strict_json(raw,max_bytes=64000)
        exact_fields(extension,{'schema_version','configuration','migration'})
        audit = extension['migration']; exact_fields(audit,{'migrated_at','sealed_tables_sha256','prior_action_count'})
        timestamp(audit['migrated_at'])
        if (digest(extension) != sha or extension['schema_version'] != 'numeric-control-extension-v4'
                or canonical(extension['configuration']) != canonical(self.configuration)
                or audit['sealed_tables_sha256'] != _history(db)
                or type(audit['prior_action_count']) is not int
                or audit['prior_action_count'] != db.execute('SELECT count(*) FROM coordinated_actions').fetchone()[0]):
            raise ValueError('sealed research configuration or history changed')
        resources = self._legacy_check(db)
        for key,input_sha,day,status,reserved,finished,payload,checksum,elapsed,error in db.execute('SELECT * FROM coordinated_numeric_actions'):
            for value in (key,input_sha):
                if type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value): raise ValueError('invalid numeric identity')
            when = timestamp(reserved)
            if day != when.date().isoformat(): raise ValueError('numeric day mismatch')
            if status == 'reserved':
                if any(value is not None for value in (finished,payload,checksum,elapsed,error)): raise ValueError('invalid reserved numeric row')
            elif status in ('completed','failed','cancelled','timed_out'):
                timestamp(finished)
                if type(elapsed) is not int or elapsed < 0: raise ValueError('invalid numeric wall observation')
                if status == 'completed':
                    result = strict_json(payload,max_bytes=64000)
                    if digest(result) != checksum or error is not None: raise ValueError('numeric result checksum mismatch')
                    _validate_report(result)
                elif payload is not None or checksum is not None or error != 'numeric_'+status: raise ValueError('unexpected failed numeric result')
            else: raise ValueError('invalid numeric status')
        return extension,resources

    def _snapshot(self, db, resources):
        day = self.legacy._now().date().isoformat()
        count,daily,wall = db.execute('SELECT count(*),coalesce(sum(utc_day=?),0),coalesce(sum(measured_wall_ms),0) FROM coordinated_numeric_actions',(day,)).fetchone()
        old_count,questions = db.execute('SELECT count(*),coalesce(sum(questions),0) FROM coordinated_actions').fetchone()
        old_daily = db.execute('SELECT count(*) FROM coordinated_actions WHERE utc_day=?',(day,)).fetchone()[0]
        allocations = dict(resources['reserved_allocations']); allocations['wall_ms'] += count*POLICY['wall_ms']
        overrun = resources['overrun_actions'] + db.execute('SELECT count(*) FROM coordinated_numeric_actions WHERE measured_wall_ms>?',(POLICY['wall_ms'],)).fetchone()[0]
        kinds = dict(db.execute('SELECT kind,count(*) FROM coordinated_actions GROUP BY kind'))
        if count: kinds['numeric_control'] = count
        return {'schema_version':'numeric-control-budget-status-v4','total_reserved':old_count+count,
            'today_reserved':old_daily+daily,'numeric_control_reserved':count,'semantic_questions_reserved':questions,
            'reserved_by_kind':kinds,'numeric_statuses':dict(db.execute('SELECT status,count(*) FROM coordinated_numeric_actions GROUP BY status')),
            'reserved_allocations':allocations,'numeric_measured_wall_ms':wall,'overrun_actions':overrun,
            'legacy_writers_sealed':True,'legacy_resources':resources,'generic_python_execution_enabled':False,
            'configuration_sha256':digest(self.configuration)}

    def snapshot(self):
        with self._connection() as db:
            _,resources = self._check(db); return self._snapshot(db,resources)

    def _finish(self,key,status,started,result=None):
        elapsed = max(0,(time.monotonic_ns()-started+999999)//1000000)
        with self._connection(True) as db:
            self._check(db)
            if db.execute('''UPDATE coordinated_numeric_actions SET status=?,finished_at=?,payload=?,payload_sha=?,measured_wall_ms=?,safe_error=?
                    WHERE key=? AND status='reserved' ''',(status,self.legacy._now().isoformat(),
                    canonical(result) if result is not None else None,digest(result) if result is not None else None,
                    elapsed,None if result is not None else 'numeric_'+status,key)).rowcount != 1:
                raise ValueError('numeric reservation immutable')

    def check(self, preview_directory, window_directory, capture, *, cancel_event=None):
        _guard()
        if cancel_event is not None and cancel_event.is_set(): raise common.BudgetCancelled('cancelled before reservation')
        checked = preview.read_preview(preview_directory)
        registration = static._registered_preview(_ReadAdapter(self),checked)
        selected = windows.read_window(window_directory,capture)
        if selected['status'] != 'prepared': raise ValueError('prepared closed input required')
        packet,analysis,controls_sha = worker.packet(checked['candidate_text'],selected['payload']['window'])
        identity = {'candidate_identity_sha256':checked['candidate_identity_sha256'],
            'window_identity_sha256':selected['window_identity_sha256'],'controls_sha256':controls_sha,
            'worker_policy_sha256':digest(worker.POLICY)}
        key = digest({'kind':'numeric_control','identity':identity,'configuration_sha256':digest(self.configuration)})
        with self._connection(True) as db:
            _,resources = self._check(db)
            row = db.execute('SELECT status,payload,input_sha FROM coordinated_numeric_actions WHERE key=?',(key,)).fetchone()
            if row:
                if row[0] != 'completed': raise ValueError('prior unresolved or failed control; no automatic retry')
                if row[2] != digest(identity): raise ValueError('numeric cached identity mismatch')
                result = strict_json(row[1],max_bytes=64000); cached = True
                if (result['identity'] != identity or result['packet_sha256'] != digest(packet)
                        or result['registration'] != registration
                        or result['summary'] != worker.validate_result(result['observation'],packet,analysis['required_window_size'])):
                    raise ValueError('numeric cached report identity or controls mismatch')
            else:
                snapshot = self._snapshot(db,resources)
                if (snapshot['total_reserved'] >= self.legacy.policy['total_actions']
                        or snapshot['today_reserved'] >= self.legacy.policy['daily_actions']
                        or snapshot['numeric_control_reserved'] >= POLICY['maximum_actions']): raise ValueError('shared action budget exhausted')
                if snapshot['overrun_actions']: raise ValueError('prior resource overrun; fresh work blocked')
                if snapshot['reserved_allocations']['wall_ms']+POLICY['wall_ms'] > self.legacy.resource_policy['total_wall_ms']:
                    raise ValueError('shared wall budget exhausted')
                if any(snapshot['reserved_allocations'][name] > self.legacy.resource_policy['total_'+name] for name in ('input_tokens','output_tokens')):
                    raise ValueError('prior token allocation exceeds shared budget')
                if cancel_event is not None and cancel_event.is_set(): raise common.BudgetCancelled('cancelled before reservation')
                now = self.legacy._now()
                db.execute('INSERT INTO coordinated_numeric_actions VALUES (?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)',
                    (key,digest(identity),now.date().isoformat(),'reserved',now.isoformat())); cached = False
        if not cached:
            started = time.monotonic_ns()
            try:
                if cancel_event is not None and cancel_event.is_set(): raise common.BudgetCancelled('cancelled after reservation')
                observed = worker.run(packet)
                summary = worker.validate_result(observed,packet,analysis['required_window_size'])
                if preview.read_preview(preview_directory)['preview_sha256'] != checked['preview_sha256']: raise ValueError('preview changed during controls')
                if windows.read_window(window_directory,capture) != selected: raise ValueError('input changed during controls')
                _guard()
                result = {'schema_version':'budgeted-numeric-controls-v4','identity':identity,
                    'original_preview_sha256':checked['preview_sha256'],'registration':registration,
                    'summary':summary,'observation':observed,'packet_sha256':digest(packet),
                    'candidate_expression_evaluated':True,'candidate_python_executed':False,
                    'training_executed':False,'provider_requests':0,'operational_database_connections':0,
                    'feature_utility_verified':False,'causal_market_validity_proven':False,
                    'source_backend_attested':False,'model_provenance_verified':False,'can_authorize_trades':False}
                _validate_report(result)
            except (KeyboardInterrupt,common.BudgetCancelled):
                self._finish(key,'cancelled',started); raise common.BudgetCancelled('numeric controls cancelled') from None
            except subprocess.TimeoutExpired:
                self._finish(key,'timed_out',started); raise common.BudgetTimedOut('numeric controls timed out') from None
            except Exception:
                self._finish(key,'failed',started); raise RuntimeError('numeric controls failed; details not logged') from None
            self._finish(key,'completed',started,result)
        # Cache reads also revalidate mutable bundles. Original provenance is retained.
        if preview.read_preview(preview_directory)['preview_sha256'] != checked['preview_sha256'] or windows.read_window(window_directory,capture) != selected:
            raise ValueError('numeric bundles changed')
        return {'schema_version':'numeric-control-invocation-v4','operation_key':key,'cached':cached,
            'new_actions':0 if cached else 1,'invocation_arithmetic_evaluations':0 if cached else result['summary']['arithmetic_evaluations'],
            'current_preview_sha256':checked['preview_sha256'],'current_window_pack_sha256':selected['window_pack_sha256'],
            'result':result,'result_sha256':digest(result)}


def _validate_report(result):
    exact_fields(result,{'schema_version','identity','original_preview_sha256','registration','summary','observation','packet_sha256',
        'candidate_expression_evaluated','candidate_python_executed','training_executed','provider_requests','operational_database_connections',
        'feature_utility_verified','causal_market_validity_proven','source_backend_attested','model_provenance_verified','can_authorize_trades'})
    if result['schema_version'] != 'budgeted-numeric-controls-v4' or result['candidate_expression_evaluated'] is not True:
        raise ValueError('numeric report schema')
    for name in ('candidate_python_executed','training_executed','feature_utility_verified','causal_market_validity_proven',
                 'source_backend_attested','model_provenance_verified','can_authorize_trades'):
        if result[name] is not False: raise ValueError('numeric report cannot grant production rights')
    if any(type(result[name]) is not int or result[name] != 0 for name in ('provider_requests','operational_database_connections')):
        raise ValueError('offline numeric report required')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database','proposal-ledger','semantic-ledger','fit-ledger','semantic-live-ledger',
                 'semantic-live-policy','code-policy','numeric-policy','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--policy',type=Path); parser.add_argument('--resource-policy',type=Path)
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('migrate'); sub.add_parser('status')
    check = sub.add_parser('check')
    for name in ('preview','window','capture'): check.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args(argv)
    protected = [path.resolve() for name,path in vars(args).items() if isinstance(path,Path) and name != 'output']
    if any(args.output.resolve() == path or args.output.resolve().is_relative_to(path) for path in protected):
        parser.error('output must be separate from journal, policy and input bundles')
    def read(path): return preview.files._json(path.parent,path.name,512000) if path is not None else None
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        receipt = {'schema_version':'numeric-control-cli-v4','status':'started','command':args.command}
        stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            legacy = common.ResearchRunBudget(args.database,{'proposal':args.proposal_ledger,'semantic_fixture':args.semantic_ledger,'fit':args.fit_ledger},
                policy=read(args.policy),resource_policy=read(args.resource_policy),semantic_live_ledger=args.semantic_live_ledger,
                semantic_live_policy=read(args.semantic_live_policy),code_check_policy=read(args.code_policy))
            budget = NumericControlBudget(legacy,read(args.numeric_policy))
            result = budget.migrate() if args.command == 'migrate' else (budget.check(args.preview,args.window,read(args.capture)) if args.command == 'check' else None)
            receipt.update(status='completed',result=result,budget=budget.snapshot()); code_result = 0
        except (KeyboardInterrupt,common.BudgetCancelled): receipt.update(status='cancelled',safe_error='numeric_cancelled'); code_result = 130
        except common.BudgetTimedOut: receipt.update(status='timed_out',safe_error='numeric_timed_out'); code_result = 1
        except (OSError,ValueError,RuntimeError,TypeError,KeyError,sqlite3.Error): receipt.update(status='failed',safe_error='numeric_inputs_or_budget_rejected'); code_result = 1
        stream.seek(0); stream.truncate(); stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
    print('Numeric control receipt saved; generic Python execution disabled')
    return code_result


if __name__ == '__main__': raise SystemExit(main())
