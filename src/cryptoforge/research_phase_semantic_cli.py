"""Explicit local semantic commands for an existing v5 journal; no migration or reset."""
import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sqlite3
import stat

from cryptoforge import research_phase as phase
from cryptoforge import semantic_source_snapshot as snapshots,semantic_asset_registry as assets,semantic_event_review as events
from cryptoforge.training_diagnostics import canonical,digest


def existing(path,maximum=16777216):
    path=Path(path).absolute()
    if path.resolve()!=path or path.is_symlink() or not path.is_file():raise ValueError('existing_original_regular_file_required')
    details=path.stat()
    if not stat.S_ISREG(details.st_mode) or not 0<details.st_size<=maximum:raise ValueError('bounded_existing_file_required')
    return path



class ExistingLocalSemanticRequests(phase.coordinator.LocalSemanticRequests):
    """Keep native policy/identity/quota logic; never initialize a journal."""
    @contextmanager
    def _transaction(self):
        existing(self.path)
        if stat.S_IMODE(self.path.stat().st_mode)!=0o600:raise ValueError('private_existing_live_journal_required')
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=5)
        try:
            db.execute('BEGIN IMMEDIATE');self._objects(db);self._check_manifest(db)
            yield db
            db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()


class ExistingPhaseSemanticCoordinator(phase.PhaseResearchCoordinator):
    # This fixed handler retains the native effect identity, resource and request contracts.
    # The only behavioral change is requiring the inner database to exist at open time.
    def _semantic_request(self,request,inputs,*,request_policy,cancel_event,source=False):
        native=phase.coordinator
        journal=ExistingLocalSemanticRequests(self.live_path,{
            'common_path_sha256':digest(str(self.budget.path)),
            'semantic_configuration_sha256':digest(self.budget.semantic_configuration)},
            policy=request_policy,clock=self.budget.clock)
        wall=min(journal.policy['wall_seconds'],self.budget.semantic_policy['wall_ms']/1000-native.CLEANUP_SECONDS)
        if wall<0.001:raise ValueError('semantic wall allocation must include client and cleanup budget')
        identity={**inputs,'request_sha256':request['request_sha256'],'inner_manifest_sha256':digest(journal.manifest)}
        def execute():
            try:result=journal.evaluate(request,wall_seconds=wall,cancel_event=cancel_event)
            except native.SemanticCancelled:raise native.BudgetCancelled('local semantic cancelled') from None
            except native.SemanticTimedOut:raise native.BudgetTimedOut('local semantic timed out') from None
            if source:result={**result,'source_event_review':native.source_semantic_contracts.compose_review(request,result)}
            usage=result['provider_reported_usage'];fresh=not result['semantic_cached']
            tokens={'input_tokens':usage['input_tokens'],'output_tokens':usage['output_tokens'],
                'total_tokens':usage['input_tokens']+usage['output_tokens']} if fresh else {'input_tokens':0,'output_tokens':0,'total_tokens':0}
            return {'result':result,'observed':{**native.ZERO_USAGE,'local_llm_completions':int(fresh)},'tokens':tokens}
        return self._dispatch('semantic_live',identity,execute,questions=len(request['catalog']['questions']),cancel_event=cancel_event)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('database','proposal-ledger','semantic-ledger','fit-ledger','semantic-live-ledger',
                 'semantic-live-policy','code-policy','numeric-policy','phase-policy','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--policy',type=Path);parser.add_argument('--resource-policy',type=Path)
    commands=parser.add_subparsers(dest='command',required=True)
    live=commands.add_parser('semantic-live')
    live.add_argument('--catalog-database',type=Path,required=True);live.add_argument('--experiment-id',required=True)
    live.add_argument('--questions',type=Path,required=True)
    source=commands.add_parser('semantic-source')
    for name in ('snapshot','registry','packet'):source.add_argument('--'+name,type=Path,required=True)
    for command in (live,source):
        command.add_argument('--model-digest',required=True);command.add_argument('--endpoint',default='http://127.0.0.1:11434')
        command.add_argument('--request-policy',type=Path)
    args=parser.parse_args(argv)
    protected=[p.resolve() for name,p in vars(args).items() if isinstance(p,Path) and name!='output']
    output=args.output.absolute()
    if output.parent.resolve()!=output.parent or output.is_symlink():parser.error('unaliasable output parent required')
    if any(output.resolve()==p or output.resolve().is_relative_to(p) for p in protected):parser.error('output must be separate from journals and source inputs')
    read=lambda p:phase.coordinator.read_json(p) if p is not None else None
    receipt={'schema_version':'coordinated-research-receipt-v1','phase_schema_version':'research-phase-semantic-cli-v5',
        'command':args.command,'status':'started','wrapper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'automatic_migration_or_new_journal_allowed':False,'new_limits_or_refunds':False}
    with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600),'w') as stream:
        stream.write(canonical(receipt)+'\n');stream.flush();os.fsync(stream.fileno())
        try:
            # Never create a common or live inner journal as a side effect of these commands.
            existing(args.database);existing(args.semantic_live_ledger)
            if canonical(read(args.numeric_policy))!=canonical(phase.numeric.POLICY):raise ValueError('fixed_numeric_policy_required')
            research=ExistingPhaseSemanticCoordinator(args.database,proposal_ledger=args.proposal_ledger,
                semantic_ledger=args.semantic_ledger,fit_ledger=args.fit_ledger,semantic_live_ledger=args.semantic_live_ledger,
                semantic_live_policy=read(args.semantic_live_policy),code_check_policy=read(args.code_policy),
                phase_policy=read(args.phase_policy),policy=read(args.policy),resource_policy=read(args.resource_policy))
            before=research.budget.snapshot()  # Checks the original persisted v5 source/configuration before dispatch.
            if args.command=='semantic-live':
                existing(args.catalog_database,8388608)
                call=research.semantic_live(args.catalog_database,args.experiment_id,read(args.questions),digest_pin=args.model_digest,
                    endpoint=args.endpoint,request_policy=read(args.request_policy))
            else:
                call=research.semantic_source(snapshots._read(args.snapshot,snapshots.MAX_SNAPSHOT_BYTES),
                    assets.read_registry(args.registry),snapshots._read(args.packet,events.MAX_PACKET_BYTES),
                    digest_pin=args.model_digest,endpoint=args.endpoint,request_policy=read(args.request_policy))
            receipt.update(status='completed',call=call,budget=research.budget.snapshot(),
                prior_total_reserved_actions=before['total_reserved_actions']);code=0
        except (phase.common.BudgetCancelled,KeyboardInterrupt):receipt.update(status='cancelled',safe_error='phase_semantic_cancelled');code=130
        except phase.common.BudgetTimedOut:receipt.update(status='timed_out',safe_error='phase_semantic_timed_out');code=1
        except (ValueError,RuntimeError,OSError,KeyError,TypeError,sqlite3.Error):
            receipt.update(status='failed',safe_error='existing_phase_semantic_inputs_action_or_budget_rejected');code=1
        stream.seek(0);stream.truncate();stream.write(canonical(receipt)+'\n');stream.flush();os.fsync(stream.fileno())
    print('Existing phase semantic receipt saved; same limits retained and no automatic journal creation/migration')
    return code


if __name__=='__main__':raise SystemExit(main())
