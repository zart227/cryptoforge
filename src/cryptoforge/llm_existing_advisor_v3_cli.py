"""Candidate v3 audited proposals on an established v5 phase; never create or migrate journals.

The CLI always requires native input-token proof for a new completion. Current
providers cannot supply that proof, so only established completed advice can be
delivered until the admission implementation is explicitly qualified.
"""
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sqlite3
import stat

from cryptoforge import llm_audited_provider_v3 as capture
from cryptoforge import llm_candidate_payload_v3 as payload_contract
from cryptoforge import research_phase as phase
from cryptoforge import research_phase_semantic_cli as existing
from cryptoforge.research_training_diagnostics import canonical, digest, validate_diagnostics


def implementation():
    return {'CLI': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'existing_files': hashlib.sha256(Path(existing.__file__).read_bytes()).hexdigest(),
        'capture_sha256': digest(capture.implementation()), 'phase_sha256': digest(phase.implementation())}


_LOADED = implementation()


def _guard():
    if implementation() != _LOADED: raise ValueError('existing_advisor_source_changed_restart_required')


class ExistingResearchRequests(capture.ResearchRequests):
    """Retain native request keys/quotas; open an initialized file with mode=rw."""
    def _inputs(self, adapter, report):
        if (type(adapter) is not capture.FreeAdvisor or adapter.provider != 'openrouter'
                or adapter.model != capture.CANDIDATE_MODEL
                or adapter.parameters != tuple(payload_contract.POLICY['parameters'])):
            raise ValueError('fixed_v3_candidate_required')
        return payload_contract.preview(report)['prospective_identity_inputs']

    def _db(self):
        path = existing.existing(self.path)
        before = path.stat()
        if stat.S_IMODE(before.st_mode) != 0o600 or before.st_uid != os.getuid():
            raise ValueError('owner_private_existing_API_journal_required')
        db = sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, timeout=5)
        try:
            after = path.stat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError('original_API_file_changed_during_open')
            objects = set(db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')"))
            if objects != {('table','request_policy'),('table','advisor_requests')}:
                raise ValueError('initialized_existing_API_journal_required')
            policy = db.execute('SELECT id,maximum FROM request_policy').fetchall()
            if policy != [(1,self.daily_maximum)]: raise ValueError('original_API_policy_required')
            return db
        except BaseException:
            db.close(); raise


def propose_existing(research, report, *, audit_root, provider='openrouter', model=None,
                     ollama_url='http://127.0.0.1:11434', jobpilot_env=None, daily_maximum=5,
                     cancel_event=None, require_verified_input_limit=True):
    """Existing-only candidate adapter; new completion always requires a verified input-token bound."""
    _guard()
    if type(research) is not phase.PhaseResearchCoordinator: raise ValueError('existing_v5_phase_required')
    if require_verified_input_limit is not True: raise ValueError('verified_input_limit_required')
    if cancel_event is not None and cancel_event.is_set(): raise phase.common.BudgetCancelled('cancelled before admission')
    existing.existing(research.budget.path)
    report = deepcopy(validate_diagnostics(report))
    if report['partition'] != 'validation': raise ValueError('validation_report_required')
    if provider != 'openrouter': raise ValueError('candidate_openrouter_required')
    model = model or capture.CANDIDATE_MODEL
    adapter = capture.FreeAdvisor(provider=provider, model=model, ollama_url=ollama_url, parameters=('l2','threshold'))
    if model != capture.CANDIDATE_MODEL:
        raise ValueError('fixed_free_exchange_model_required')
    prepared = adapter.preflight(report)
    journal = ExistingResearchRequests(research.paths['proposal'], daily_maximum=daily_maximum)
    # A checked read/write open performs no DDL, policy inserts or reservations.
    with journal._db() as db: pass
    db.close()
    cached = journal.read_cached(adapter, report)
    if cached is None: adapter.preflight(report, require_verified_input_limit=True)
    root = capture.private._safe_directory(audit_root, private=True)
    if cached is not None:
        reference = capture._cached_reference(cached)
        if not reference['available']:
            raise ValueError('candidate_original_v3_capture_required')
        binding = capture._journal_binding(journal, adapter, report)
        checked = capture.verify_attempt(root/binding['request_key'], expected_binding=binding)
        if (checked['capture_sha256'] != reference['capture_sha256']
                or reference.get('request_key') != binding['request_key']
                or cached.get('provider') != provider or cached.get('requested_model') != model
                or checked['validation']['proposal'] != cached['proposal']):
            raise ValueError('candidate_original_v3_capture_required')
    research.budget.snapshot()  # Original v5 history/configuration before dispatch.
    binding = capture._journal_binding(journal, adapter, report)
    inputs = {'report':digest(report),'provider':provider,'model':model,
        'endpoint_sha256':digest(ollama_url) if provider == 'ollama' else None,
        'daily_maximum':daily_maximum,'audited_worker':capture.implementation(), 'existing_only_adapter':_LOADED}
    def execute():
        observed = dict(capture.ZERO_USAGE)
        try:
            advice = journal.propose(adapter, report,
                admit=lambda:adapter.preflight(report, require_verified_input_limit=require_verified_input_limit),
                execute=lambda:capture._run_worker(adapter, report, root/binding['request_key'], binding,
                    wall_seconds=min(capture.MAX_WALL_SECONDS, research.budget.resource_policy['wall_ms_by_kind']['proposal']/1000),
                    api_key=os.environ.get('CRYPTOFORGE_OPENROUTER_API_KEY'), jobpilot_env=jobpilot_env, cancel_event=cancel_event))
        except capture.AdvisorCancelled: raise phase.common.BudgetCancelled('existing advisor cancelled') from None
        except capture.AdvisorTimedOut: raise phase.common.BudgetTimedOut('existing advisor timed out') from None
        if not advice['api_cached']: observed['remote_completions' if provider == 'openrouter' else 'local_llm_completions'] = 1
        envelope = {'result':{'diagnostics':report,'advice':advice,'exchange_capture':capture._cached_reference(advice)},'observed':observed}
        if not advice['api_cached']: envelope['tokens'] = capture.provider_tokens(advice.get('usage'))
        _guard(); return envelope
    call = research._dispatch('proposal', inputs, execute, cancel_event=cancel_event)
    verified = False; reference = call['result']['exchange_capture']
    if not reference['available']: raise ValueError('candidate_original_v3_capture_required')
    if reference['available']:
        checked = capture.verify_attempt(root/binding['request_key'], expected_binding=binding)
        advice = call['result']['advice']
        if (checked['capture_sha256'] != reference['capture_sha256']
                or reference.get('request_key') != binding['request_key']
                or advice.get('provider') != provider or advice.get('requested_model') != model
                or checked['validation']['proposal'] != advice['proposal']):
            raise ValueError('original_cached_capture_required')
        verified = True
    return {**call,'original_exchange_verified':verified,'existing_journals_only':True,
        'input_admission':{'require_verified_input_limit':require_verified_input_limit,
            'current_preflight':prepared['audit'],'scope':'current_invocation_not_historical_wire'}}


def _research(args):
    read = lambda p: phase.coordinator.read_json(existing.existing(p)) if p is not None else None
    existing.existing(args.database); existing.existing(args.proposal_ledger)
    if canonical(read(args.numeric_policy)) != canonical(phase.numeric.POLICY): raise ValueError('fixed_numeric_policy_required')
    return phase.PhaseResearchCoordinator(args.database, proposal_ledger=args.proposal_ledger,
        semantic_ledger=args.semantic_ledger, fit_ledger=args.fit_ledger, semantic_live_ledger=args.semantic_live_ledger,
        semantic_live_policy=read(args.semantic_live_policy), code_check_policy=read(args.code_policy),
        phase_policy=read(args.phase_policy), policy=read(args.policy), resource_policy=read(args.resource_policy))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    verify = commands.add_parser('verify'); verify.add_argument('--directory',type=Path,required=True)
    proposal = commands.add_parser('proposal')
    for name in ('database','proposal-ledger','semantic-ledger','fit-ledger','semantic-live-ledger',
                 'semantic-live-policy','code-policy','numeric-policy','phase-policy','experiment-receipt','audit-root'):
        proposal.add_argument('--'+name,type=Path,required=True)
    proposal.add_argument('--policy',type=Path); proposal.add_argument('--resource-policy',type=Path)
    proposal.add_argument('--provider',choices=('openrouter',),default='openrouter')
    proposal.add_argument('--model'); proposal.add_argument('--ollama-url',default='http://127.0.0.1:11434')
    proposal.add_argument('--jobpilot-env',type=Path); proposal.add_argument('--daily-maximum',type=int,default=5)
    for command in (verify,proposal): command.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv)
    output = args.output.absolute()
    if output.parent.resolve() != output.parent or output.is_symlink(): parser.error('unaliasable_output_parent_required')
    protected = [p.absolute().resolve() for n,p in vars(args).items() if isinstance(p,Path) and n != 'output']
    if any(output.resolve() == p or output.resolve().is_relative_to(p) for p in protected):
        parser.error('output_must_be_separate_from_source_journals_and_audits')
    receipt = {'schema_version':'candidate-existing-audited-advisor-receipt-v3','command':args.command,'status':'started',
        'implementation':_LOADED,'automatic_migration_or_new_journal_allowed':False,'new_limits_or_refunds':False,
        'require_verified_input_limit':True,'provider_quality_or_study_admission_attested':False}
    with os.fdopen(os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as stream:
        stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            _guard()
            if args.command == 'verify': result = capture.verify_attempt(args.directory)
            else:
                research = _research(args); before = research.budget.snapshot()
                report = phase.coordinator.validation_report(phase.coordinator.read_json(existing.existing(args.experiment_receipt)))
                result = propose_existing(research, report, audit_root=args.audit_root, provider=args.provider,model=args.model,
                    ollama_url=args.ollama_url,jobpilot_env=args.jobpilot_env,daily_maximum=args.daily_maximum,
                    require_verified_input_limit=True)
                receipt.update(budget=research.budget.snapshot(),prior_total_reserved_actions=before['total_reserved_actions'])
            receipt.update(status='completed',result=result); code = 0
        except (phase.common.BudgetCancelled,KeyboardInterrupt): receipt.update(status='cancelled',safe_error='existing_advisor_cancelled'); code = 130
        except phase.common.BudgetTimedOut: receipt.update(status='timed_out',safe_error='existing_advisor_timed_out'); code = 1
        except (ValueError,RuntimeError,OSError,KeyError,TypeError,sqlite3.Error):
            receipt.update(status='failed',safe_error='existing_advisor_inputs_journal_admission_or_capture_rejected'); code = 1
        stream.seek(0); stream.truncate(); stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
    print('Existing advisor receipt saved; no automatic journal creation, migration or limit change')
    return code


if __name__ == '__main__': raise SystemExit(main())
