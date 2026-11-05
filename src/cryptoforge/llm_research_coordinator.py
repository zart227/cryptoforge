"""Common admission for proposal, SDK-fixture, local semantic and offline fit.

Explicit local digest requests only; no generated code or trading activation.
Existing per-operation journals remain bound and independently enforced.
"""
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sqlite3
from types import MappingProxyType

from cryptoforge.llm_research_advisor import FreeAdvisor, DEFAULT_MODEL, PROMPT_VERSION, SYSTEM, AdvisorCancelled, AdvisorTimedOut
from cryptoforge.llm_provider_worker import run_provider_worker, MAX_WALL_SECONDS
from cryptoforge.llm_prompt_preflight import UNVERIFIED_LIMIT
from cryptoforge.llm_research_contracts import CATALOG, validate_proposal
from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.research_resource_budget import provider_tokens
from cryptoforge.research_run_budget import ResearchRunBudget, ZERO_USAGE, BudgetCancelled, BudgetTimedOut
from cryptoforge.semantic_request_journal import SemanticRequests, RequestCancelled, RequestTimedOut
from cryptoforge.training_diagnostics import canonical, digest, timestamp, validate_diagnostics
from cryptoforge.training_experiment_planner import load_development, validate_protocol, read_json, run_experiment
from cryptoforge.typesafe_sdk_bridge import prepare_request
from cryptoforge.local_semantic_contracts import prepare_request as prepare_local_request
from cryptoforge.local_semantic_requests import LocalSemanticRequests
from cryptoforge.local_semantic_worker import SemanticCancelled, SemanticTimedOut, CLEANUP_SECONDS
from cryptoforge.semantic_research_catalog import SemanticResearchCatalog
from cryptoforge import source_semantic_contracts, semantic_asset_registry, semantic_event_review, semantic_source_snapshot


SOURCE_NAMES = ('llm_research_coordinator.py', 'research_run_budget.py', 'llm_research_advisor.py',
    'llm_research_requests.py', 'llm_prompt_preflight.py', 'llm_provider_worker.py', 'research_resource_budget.py', 'llm_research_contracts.py', 'training_experiment_planner.py',
    'semantic_request_journal.py', 'typesafe_sdk_bridge.py', 'typesafe_judgment_contracts.py', 'training_diagnostics.py', 'research_semantic_budget.py',
    'local_semantic_contracts.py', 'local_semantic_requests.py', 'local_semantic_worker.py', 'semantic_research_catalog.py', 'ollama_decision_readiness.py',
    'source_semantic_contracts.py', 'semantic_event_review.py', 'semantic_asset_registry.py',
    'semantic_source_snapshot.py', 'semantic_source_collector.py', 'semantic_source_transport.py', 'announcement_sources.py',
    'research_code_budget.py', 'research_code_preview.py')


def implementation():
    return {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}


_LOADED = implementation()


def coordinated_value(receipt, kind):
    if receipt.get('schema_version') != 'coordinated-research-receipt-v1' or receipt.get('status') != 'completed':
        raise ValueError('completed coordinator receipt required')
    call = receipt['call']
    if call['kind'] != kind or digest(call['result']) != call['result_sha256']:
        raise ValueError('coordinator result identity mismatch')
    return call['result']


def validation_report(receipt):
    if receipt.get('schema_version') == 'coordinated-research-receipt-v1':
        result = coordinated_value(receipt, 'fit')
    elif receipt.get('status') == 'completed' and receipt.get('command') == 'run':
        result = receipt['result']
    else:
        raise ValueError('completed offline experiment evidence required')
    if digest(result['artifact']) != result['artifact_sha256'] or result['artifact']['production_compatible'] is not False:
        raise ValueError('offline artifact checksum mismatch')
    report = validate_diagnostics(result['reports']['validation']['diagnostics'])
    if report['partition'] != 'validation' or report['dataset_sha256'] != result['dataset_sha256']:
        raise ValueError('consistent validation evidence required')
    return report


class ResearchCoordinator:
    def __init__(self, database, *, proposal_ledger, semantic_ledger, fit_ledger, policy=None, resource_policy=None, clock=None,
                 semantic_live_ledger=None, semantic_live_policy=None, code_check_policy=None):
        self.paths = MappingProxyType({kind: Path(path).resolve() for kind, path in
            (('proposal', proposal_ledger), ('semantic_fixture', semantic_ledger), ('fit', fit_ledger))})
        self.budget = ResearchRunBudget(database, dict(self.paths), policy=policy, resource_policy=resource_policy, clock=clock,
            semantic_live_ledger=semantic_live_ledger, semantic_live_policy=semantic_live_policy, code_check_policy=code_check_policy)
        self.live_path = Path(semantic_live_ledger).resolve() if semantic_live_ledger is not None else None

    def _identity(self, values):
        if implementation() != _LOADED:
            raise ValueError('coordinator source changed since import; restart required')
        return {'implementation': _LOADED, 'inputs': values}

    def _dispatch(self, kind, inputs, operation, *, questions=0, cancel_event=None):
        def guarded():
            envelope = operation()
            if implementation() != _LOADED:
                raise ValueError('coordinator source changed during operation')
            return envelope
        return self.budget.run(kind, self._identity(inputs), guarded, questions=questions, cancel_event=cancel_event)

    def propose(self, report, *, mock=None, provider=None, model=None, ollama_url='http://127.0.0.1:11434',
                jobpilot_env=None, daily_maximum=5, cancel_event=None, require_verified_input_limit=False):
        if type(require_verified_input_limit) is not bool:
            raise ValueError('boolean input-limit requirement required')
        if cancel_event is not None and cancel_event.is_set():
            raise BudgetCancelled('proposal cancelled before admission')
        report = deepcopy(validate_diagnostics(report))
        mock = deepcopy(mock)
        if report['partition'] != 'validation' or (mock is None) == (provider is None):
            raise ValueError('validation and exactly one mock/provider mode required')
        if mock is not None:
            if len(canonical(mock).encode()) > 64000 or jobpilot_env is not None:
                raise ValueError('bounded mock without credential source required')
            inputs = {'report': digest(report), 'origin': 'mock', 'fixture': digest(mock)}
        else:
            model = model or (DEFAULT_MODEL if provider == 'openrouter' else 'nemotron-3-nano:30b')
            preflight_advisor = FreeAdvisor(provider=provider, model=model, ollama_url=ollama_url, parameters=('l2', 'threshold'))
            prepared = preflight_advisor.preflight(report)
            if provider == 'openrouter' and not model.endswith(':free'):
                raise ValueError('fixed free OpenRouter model required')
            if require_verified_input_limit and ResearchRequests(self.paths['proposal'], daily_maximum=daily_maximum).read_cached(preflight_advisor, report) is None:
                preflight_advisor.preflight(report, require_verified_input_limit=True)
            inputs = {'report': digest(report), 'provider': provider, 'model': model,
                'endpoint_sha256': digest(ollama_url) if provider == 'ollama' else None,
                'prompt_version': PROMPT_VERSION, 'system_sha256': digest(SYSTEM),
                'catalog': {name: CATALOG[name] for name in ('l2', 'threshold')}, 'daily_maximum': daily_maximum}
        def execute():
            observed = dict(ZERO_USAGE)
            if mock is not None:
                proposal = validate_proposal(mock, report)
                if proposal['parameter'] not in ('l2', 'threshold'):
                    raise ValueError('coordinated fit supports l2/threshold only')
                advice = {'provider': 'mock', 'proposal': proposal, 'report_sha256': digest(report)}
            else:
                advisor = FreeAdvisor(provider=provider, model=model, ollama_url=ollama_url, parameters=('l2', 'threshold'))
                wall_seconds = min(MAX_WALL_SECONDS, self.budget.resource_policy['wall_ms_by_kind']['proposal']/1000)
                try:
                    advice = ResearchRequests(self.paths['proposal'], daily_maximum=daily_maximum).propose(advisor, report,
                        admit=lambda: advisor.preflight(report, require_verified_input_limit=require_verified_input_limit),
                        execute=lambda: run_provider_worker(advisor, report, wall_seconds=wall_seconds,
                            api_key=os.environ.get('CRYPTOFORGE_OPENROUTER_API_KEY'),
                            jobpilot_env=jobpilot_env, cancel_event=cancel_event))
                except AdvisorCancelled:
                    raise BudgetCancelled('local provider attempt cancelled') from None
                except AdvisorTimedOut:
                    raise BudgetTimedOut('local provider deadline exceeded') from None
                if not advice['api_cached']:
                    observed['remote_completions' if provider == 'openrouter' else 'local_llm_completions'] = 1
            envelope = {'result': {'diagnostics': report, 'advice': advice}, 'observed': observed}
            if observed['remote_completions'] or observed['local_llm_completions']:
                envelope['tokens'] = provider_tokens(advice.get('usage'))
            return envelope
        call = self._dispatch('proposal', inputs, execute, cancel_event=cancel_event)
        return {**call, 'input_admission': {'require_verified_input_limit': require_verified_input_limit,
            'current_preflight': prepared['audit'] if provider is not None else None,
            'scope': 'this_invocation_not_a_rewrite_of_historical_advice'}}

    def fit(self, dataset, protocol, *, proposal=None, report=None):
        protocol, proposal, report = deepcopy(protocol), deepcopy(proposal), deepcopy(report)
        data, splits = load_development(dataset)
        validate_protocol(protocol, data, splits)
        config = dict(protocol['baseline'])
        if proposal is not None:
            validate_proposal(proposal, report)
            if (proposal['parameter'] not in config or report['partition'] != 'validation'
                    or report['dataset_sha256'] != protocol['dataset_sha256']
                    or report['source_sha256'] != digest(protocol['implementation_hashes'])
                    or timestamp(report['development_end']) != timestamp(protocol['development_end'])):
                raise ValueError('supported proposal and matching development evidence required')
            ledger = self.paths['fit']
            if not ledger.is_file():
                raise ValueError('registered validation evidence required')
            with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
                rows = db.execute("SELECT a.payload FROM attempts a JOIN studies s ON s.id=a.study "
                    "WHERE s.protocol=? AND a.status='completed' LIMIT 51", (digest(protocol),)).fetchall()
            from cryptoforge.llm_research_contracts import strict_json
            if len(rows) > 50 or not any(digest(strict_json(row[0], max_bytes=2_000_000)['reports']['validation']['diagnostics']) == digest(report) for row in rows):
                raise ValueError('report is not registered evidence for this protocol')
            config[proposal['parameter']] = float(proposal['value'])
        # One numerical configuration stays one action, regardless of hypothesis wording.
        identity = {'dataset_sha256': digest(data), 'protocol_sha256': digest(protocol), 'config': config}
        def execute():
            result = run_experiment(dataset, protocol, self.paths['fit'], proposal=proposal, report=report)
            return {'result': result, 'observed': {**ZERO_USAGE, 'numeric_fits': int(result['training_executed'])}}
        return self._dispatch('fit', identity, execute)

    def semantic_fixture(self, request, fixture, *, semantic_policy=None, cancel_event=None):
        request, fixture = deepcopy(request), deepcopy(fixture)
        rebuilt = prepare_request(request['state'], request['catalog'], model=request['requested_model'])
        if canonical(rebuilt) != canonical(request) or len(canonical(fixture).encode()) > 64000:
            raise ValueError('unchanged SDK request and bounded fixture required')
        identity = {'request': request['request_sha256'], 'fixture': digest(fixture), 'semantic_policy': semantic_policy}
        def execute():
            try:
                result = SemanticRequests(self.paths['semantic_fixture'], policy=semantic_policy).evaluate(request, fixture, cancel_event=cancel_event)
            except RequestCancelled:
                raise BudgetCancelled('semantic fixture cancelled') from None
            except RequestTimedOut:
                raise BudgetTimedOut('semantic fixture timed out') from None
            return {'result': result, 'observed': {**ZERO_USAGE, 'fixture_workers': int(not result['semantic_cached'])}}
        return self._dispatch('semantic_fixture', identity, execute, questions=len(request['catalog']['questions']), cancel_event=cancel_event)

    def semantic_live(self, database, experiment_id, catalog, *, digest_pin,
                      endpoint='http://127.0.0.1:11434', request_policy=None, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise BudgetCancelled('local semantic cancelled before admission')
        if self.live_path is None or self.budget.semantic_configuration is None:
            raise ValueError('explicit migrated v2 semantic budget required')
        records = SemanticResearchCatalog(database).read_records()
        selected = [r for r in records if r['experiment_id'] == experiment_id]
        if len(selected) != 1:
            raise ValueError('one registered validation experiment required')
        request = prepare_local_request(selected[0], catalog, endpoint=endpoint, digest_pin=digest_pin)
        return self._semantic_request(request, {'catalog_path_sha256': digest(str(Path(database).resolve()))},
                                      request_policy=request_policy, cancel_event=cancel_event)

    def semantic_source(self, snapshot, bundle, packet, *, digest_pin,
                        endpoint='http://127.0.0.1:11434', request_policy=None, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise BudgetCancelled('source semantic cancelled before admission')
        if self.live_path is None or self.budget.semantic_configuration is None:
            raise ValueError('explicit migrated v2 semantic budget required')
        request = source_semantic_contracts.prepare_request(snapshot, bundle, packet,
            endpoint=endpoint, digest_pin=digest_pin)
        if timestamp(packet['parameters']['decision_time']) > self.budget._now():
            raise ValueError('source decision cannot follow current local admission time')
        return self._semantic_request(request, {'source_action_schema': 'source-event-semantic-v1'},
            request_policy=request_policy, cancel_event=cancel_event, source=True)

    def _semantic_request(self, request, inputs, *, request_policy, cancel_event, source=False):
        journal = LocalSemanticRequests(self.live_path, {
            'common_path_sha256': digest(str(self.budget.path)),
            'semantic_configuration_sha256': digest(self.budget.semantic_configuration)},
            policy=request_policy, clock=self.budget.clock)
        wall = min(journal.policy['wall_seconds'], self.budget.semantic_policy['wall_ms']/1000-CLEANUP_SECONDS)
        if wall < 0.001:
            raise ValueError('semantic wall allocation must include client and cleanup budget')
        identity = {**inputs, 'request_sha256': request['request_sha256'],
            'inner_manifest_sha256': digest(journal.manifest)}
        def execute():
            try:
                result = journal.evaluate(request, wall_seconds=wall, cancel_event=cancel_event)
            except SemanticCancelled:
                raise BudgetCancelled('local semantic cancelled') from None
            except SemanticTimedOut:
                raise BudgetTimedOut('local semantic timed out') from None
            if source:
                result = {**result, 'source_event_review': source_semantic_contracts.compose_review(request, result)}
            usage = result['provider_reported_usage']
            fresh = not result['semantic_cached']
            tokens = {'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
                      'total_tokens': usage['input_tokens']+usage['output_tokens']} if fresh else {
                          'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}
            return {'result': result, 'observed': {**ZERO_USAGE, 'local_llm_completions': int(fresh)}, 'tokens': tokens}
        return self._dispatch('semantic_live', identity, execute, questions=len(request['catalog']['questions']), cancel_event=cancel_event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('.local/coordinated-research.sqlite'))
    parser.add_argument('--proposal-ledger', type=Path, required=True, help='retain the established API journal')
    parser.add_argument('--semantic-ledger', type=Path, required=True)
    parser.add_argument('--fit-ledger', type=Path, required=True, help='retain the approved study attempt history')
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--resource-policy', type=Path, help='immutable token/time allocation policy')
    parser.add_argument('--semantic-live-ledger', type=Path, help='separate future live-semantic journal binding')
    parser.add_argument('--semantic-live-policy', type=Path, help='explicit immutable v2 extension; never auto-migrated')
    parser.add_argument('--code-check-policy', type=Path, help='explicit policy for an already migrated v3 shared journal')
    parser.add_argument('--output', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('migrate-semantic-budget', help='extend an existing inactive journal without executing an action')
    proposal = sub.add_parser('proposal')
    proposal.add_argument('--experiment-receipt', type=Path, required=True)
    mode = proposal.add_mutually_exclusive_group(required=True)
    mode.add_argument('--mock-response', type=Path)
    mode.add_argument('--provider', choices=('openrouter', 'ollama'))
    proposal.add_argument('--model')
    proposal.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    proposal.add_argument('--jobpilot-env', type=Path)
    proposal.add_argument('--daily-maximum', type=int, default=5)
    proposal.add_argument('--require-verified-input-limit', action='store_true', help='cached advice only until native input bounds are verified')
    fit = sub.add_parser('fit')
    fit.add_argument('--dataset', type=Path, required=True)
    fit.add_argument('--protocol', type=Path, required=True)
    fit.add_argument('--advice-receipt', type=Path)
    semantic = sub.add_parser('semantic-fixture')
    semantic.add_argument('--request', type=Path, required=True)
    semantic.add_argument('--response', type=Path, required=True)
    semantic.add_argument('--semantic-policy', type=Path)
    live = sub.add_parser('semantic-live', help='one explicit local digest request over a registered validation record')
    live.add_argument('--catalog-database', type=Path, required=True)
    live.add_argument('--experiment-id', required=True)
    live.add_argument('--questions', type=Path, default=Path('config/semantic-research-questions-v1.json'))
    live.add_argument('--model-digest', required=True)
    live.add_argument('--endpoint', default='http://127.0.0.1:11434')
    live.add_argument('--request-policy', type=Path, help='immutable local semantic inner quotas')
    source = sub.add_parser('semantic-source', help='one explicit source-event packet through the same local budgets')
    source.add_argument('--snapshot', type=Path, required=True)
    source.add_argument('--registry', type=Path, required=True)
    source.add_argument('--packet', type=Path, required=True)
    source.add_argument('--model-digest', required=True)
    source.add_argument('--endpoint', default='http://127.0.0.1:11434')
    source.add_argument('--request-policy', type=Path)
    args = parser.parse_args(argv)
    if (args.semantic_live_ledger is None) != (args.semantic_live_policy is None):
        parser.error('semantic-live policy and ledger must be specified together')
    if args.command in ('migrate-semantic-budget', 'semantic-live', 'semantic-source') and args.semantic_live_policy is None:
        parser.error('explicit semantic-live policy and ledger required for migration')
    journals = [args.database, args.proposal_ledger, args.semantic_ledger, args.fit_ledger]
    if args.semantic_live_ledger is not None:
        journals.append(args.semantic_live_ledger)
    if args.output.resolve() in {p.resolve() for p in journals}:
        parser.error('output must be separate from every journal')
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        receipt = {'schema_version': 'coordinated-research-receipt-v1', 'status': 'started'}
        stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            coordinator = ResearchCoordinator(args.database, proposal_ledger=args.proposal_ledger,
                semantic_ledger=args.semantic_ledger, fit_ledger=args.fit_ledger,
                policy=read_json(args.policy) if args.policy else None,
                resource_policy=read_json(args.resource_policy) if args.resource_policy else None,
                semantic_live_ledger=args.semantic_live_ledger,
                semantic_live_policy=read_json(args.semantic_live_policy) if args.semantic_live_policy else None,
                code_check_policy=read_json(args.code_check_policy) if args.code_check_policy else None)
            call = None
            if args.command == 'migrate-semantic-budget':
                receipt['migration'] = coordinator.budget.migrate_semantic_budget()
            elif args.command == 'fit':
                protocol = read_json(args.protocol)
                if protocol.get('status') == 'completed' and protocol.get('command') == 'freeze': protocol = protocol['result']
                advice = coordinated_value(read_json(args.advice_receipt), 'proposal') if args.advice_receipt else None
                call = coordinator.fit(args.dataset, protocol, proposal=advice['advice']['proposal'] if advice else None,
                                       report=advice['diagnostics'] if advice else None)
            elif args.command == 'proposal':
                call = coordinator.propose(validation_report(read_json(args.experiment_receipt)),
                    mock=read_json(args.mock_response, 64000) if args.mock_response else None,
                    provider=args.provider, model=args.model, ollama_url=args.ollama_url,
                    jobpilot_env=args.jobpilot_env, daily_maximum=args.daily_maximum,
                    require_verified_input_limit=args.require_verified_input_limit)
            elif args.command == 'semantic-fixture':
                call = coordinator.semantic_fixture(read_json(args.request), read_json(args.response, 64000),
                    semantic_policy=read_json(args.semantic_policy) if args.semantic_policy else None)
            elif args.command == 'semantic-live':
                call = coordinator.semantic_live(args.catalog_database, args.experiment_id, read_json(args.questions, 64000),
                    digest_pin=args.model_digest, endpoint=args.endpoint,
                    request_policy=read_json(args.request_policy) if args.request_policy else None)
            elif args.command == 'semantic-source':
                call = coordinator.semantic_source(
                    semantic_source_snapshot._read(args.snapshot, semantic_source_snapshot.MAX_SNAPSHOT_BYTES),
                    semantic_asset_registry.read_registry(args.registry),
                    semantic_source_snapshot._read(args.packet, semantic_event_review.MAX_PACKET_BYTES),
                    digest_pin=args.model_digest, endpoint=args.endpoint,
                    request_policy=read_json(args.request_policy) if args.request_policy else None)
            receipt.update(status='completed', call=call, budget=coordinator.budget.snapshot()); code = 0
        except (BudgetCancelled, KeyboardInterrupt):
            receipt.update(status='cancelled', error='coordinated action cancelled'); code = 130
        except BudgetTimedOut:
            receipt.update(status='timed_out', error='coordinated action timed out'); code = 1
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, sqlite3.Error) as error:
            receipt.update(status='failed', error='coordinated inputs, action or budget rejected'); code = 1
            if str(error) == UNVERIFIED_LIMIT:
                receipt['error_code'] = UNVERIFIED_LIMIT
        stream.seek(0); stream.truncate(); stream.write(canonical(receipt)+'\n'); stream.flush(); os.fsync(stream.fileno())
    print('Coordinated research receipt saved; no production model activated')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
