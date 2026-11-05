"""Fixed exchange capture through the existing common and API reservations.

This opt-in adapter does not migrate journals, grant admission or retry a failed
request. Legacy completed advice remains usable without manufacturing old wire.
The child alone handles credentials and persists cleaned complete responses.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib import error, request

from cryptoforge import llm_exchange_audit as audit
from cryptoforge import llm_research_advisor as advisor_module
from cryptoforge import llm_research_coordinator as coordinator_module
from cryptoforge import research_local_export as private
from cryptoforge import semantic_source_collector as files
from cryptoforge.llm_provider_worker import MAX_WALL_SECONDS, CLEANUP_SECONDS, _stop
from cryptoforge.llm_research_advisor import FreeAdvisor, AdvisorUnavailable, AdvisorCancelled, AdvisorTimedOut
from cryptoforge.llm_research_contracts import CATALOG, strict_json, validate_proposal
from cryptoforge.llm_research_requests import ResearchRequests
from cryptoforge.research_resource_budget import provider_tokens
from cryptoforge.research_run_budget import ZERO_USAGE, BudgetCancelled, BudgetTimedOut
from cryptoforge.research_training_diagnostics import canonical, digest, exact_fields, number, validate_diagnostics

POLICY = {'schema_version': 'audited-fixed-advisor-v1', 'maximum_worker_input_bytes': 256000,
    'maximum_worker_output_bytes': 64000, 'maximum_response_bytes': 1000000,
    'maximum_attempt_bytes': 2000000, 'retries': 0, 'legacy_completed_cache_recaptured': False,
    'new_budget_or_journal_migration': False, 'server_cancellation_verified': False,
    'native_input_token_proof_added': False, 'semantic_quality_attested': False}


def implementation():
    names = ('llm_audited_provider.py', 'llm_provider_worker.py', 'llm_research_requests.py',
        'research_local_export.py', 'semantic_source_collector.py')
    return {'sources': {n: hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in names},
        'exchange': audit.implementation(), 'coordinator': coordinator_module.implementation()}


_LOADED = implementation(); _POLICY = canonical(POLICY)


def _guard():
    if implementation() != _LOADED or canonical(POLICY) != _POLICY:
        raise ValueError('audited_provider_source_changed_restart_required')


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _read(directory, name, maximum=128000):
    return strict_json(private._private_read(directory, name, maximum).decode(), max_bytes=maximum)


def _journal_binding(journal, adapter, report):
    return {'schema_version': 'advisor-exchange-journal-binding-v1',
        'API_journal_path_sha256': digest(str(journal.path.resolve())),
        'request_key': digest(journal._inputs(adapter, report)), 'report_sha256': digest(report),
        'provider': adapter.provider, 'requested_model': adapter.model}


def _cached_reference(advice):
    # Cache hits never create a replacement exchange, read keys or issue HTTP.
    return advice.get('exchange_capture', {'schema_version': 'advisor-exchange-reference-v1',
        'available': False, 'reason': 'legacy_completed_advice_has_no_original_exchange',
        'historical_wire_reconstructed': False})


def _http(url, payload=None, headers=None, timeout=30):
    raw_request = None if payload is None else canonical(payload).encode()
    req = request.Request(url, data=raw_request, headers={'Content-Type': 'application/json', **(headers or {})})
    opener = request.build_opener(request.ProxyHandler({}), advisor_module.NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(1000001); status = response.status
    except error.HTTPError as exc:
        try: raw, status = exc.read(1000001), exc.code
        finally: exc.close()
    except (error.URLError, TimeoutError, OSError, ValueError):
        raise AdvisorUnavailable('audited provider transport failed') from None
    if len(raw) > 1000000:
        raise AdvisorUnavailable('audited provider response exceeded limit')
    return status, raw


def _evaluate(data):
    exact_fields(data, {'report', 'settings', 'wall_seconds', 'implementation', 'directory', 'binding'})
    _guard()
    if data['implementation'] != _LOADED: raise ValueError('fixed_audited_worker_required')
    settings = data['settings']
    exact_fields(settings, {'provider', 'model', 'ollama_url', 'parameters', 'timeout', 'api_key', 'jobpilot_env'})
    if (type(settings['parameters']) is not list or type(data['directory']) is not str
            or len(data['directory']) > 4096): raise ValueError('bounded_audited_worker_settings_required')
    for name in ('api_key', 'jobpilot_env'):
        if settings[name] is not None and (type(settings[name]) is not str or len(settings[name]) > 4096):
            raise ValueError('bounded_private_worker_settings_required')
    directory = private._safe_directory(data['directory'], private=True)
    attempt = _read(directory, 'attempt.json')
    if attempt['binding'] != data['binding'] or attempt['implementation'] != _LOADED:
        raise ValueError('original_attempt_binding_required')
    adapter = FreeAdvisor(provider=settings['provider'], model=settings['model'],
        ollama_url=settings['ollama_url'], parameters=tuple(settings['parameters']), timeout=settings['timeout'])
    prepared = adapter.preflight(data['report'])
    if adapter.provider == 'openrouter' and adapter.model != advisor_module.DEFAULT_MODEL:
        raise ValueError('fixed_free_exchange_model_required')
    if data['binding']['report_sha256'] != digest(data['report']): raise ValueError('report_binding_changed')
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, number(data['wall_seconds'], .001, MAX_WALL_SECONDS))
    try:
        key = settings['api_key'] or ''
        if adapter.provider == 'openrouter' and settings['api_key'] is None and settings['jobpilot_env'] is not None:
            key = advisor_module.jobpilot_credentials(settings['jobpilot_env']).get('OPENROUTER_API_KEY', '')
        secrets = (key,) if key else ()
        clean_request, redactions = audit.scrub(prepared['payload'], secrets)
        if clean_request != prepared['payload'] or any(redactions.values()):
            raise AdvisorUnavailable('outbound request privacy refused')
        price = None
        if adapter.provider == 'openrouter':
            if not key: raise AdvisorUnavailable('OpenRouter key required')
            status, raw = _http('https://openrouter.ai/api/v1/models', timeout=adapter.timeout)
            if status != 200: raise AdvisorUnavailable('free catalog request refused')
            price = advisor_module.free_model_receipt(audit._parse(raw), adapter.model)
            url = 'https://openrouter.ai/api/v1/chat/completions'
            headers = {'Authorization': 'Bearer '+key}
        else:
            url = adapter.ollama_url.rstrip('/')+'/api/chat'; headers = None
        # Save dispatch intent first. SIGALRM/process death afterwards is unknown
        # completion, never a refundable or automatically repeatable request.
        dispatch = {'schema_version': 'advisor-dispatch-intent-v1', 'started_at': _stamp(),
            'request_payload_sha256': digest(prepared['payload']), 'endpoint_sha256': digest(url),
            'headers_or_credentials_saved': False, 'price_receipt': price}
        files._write(directory, 'dispatch.json', dispatch)
        status, raw = _http(url, prepared['payload'], headers, adapter.timeout)
        received = _stamp()
        record = audit.build(data['report'], raw, provider=adapter.provider, model=adapter.model,
            parameters=adapter.parameters, observed_at=received, known_secrets=secrets)
        if record['provenance']['original_request_factory_payload_sha256'] != dispatch['request_payload_sha256']:
            raise AdvisorUnavailable('outbound factory identity changed')
        manifest = audit.save(directory/'exchange', record, known_secrets=secrets)
        capture = {'schema_version': 'advisor-transport-capture-v1', 'binding': data['binding'],
            'observed_at': received, 'HTTP_status': status, 'request_payload_sha256': digest(prepared['payload']),
            'response_body_sha256': hashlib.sha256(raw).hexdigest(), 'exchange_manifest_sha256': digest(manifest),
            'implementation': _LOADED, 'source': 'fixed_worker_actual_transport_body',
            'server_upstream_transformations_or_execution_attested': False,
            'account_billing_attested': False, 'raw_response_or_headers_saved': False}
        files._write(directory, 'capture.json', capture)
        validation = record['validation']
        if status != 200 or validation['status'] != 'proposal_schema_valid_only':
            raise AdvisorUnavailable('audited provider response refused')
        response = audit._parse(raw)
        usage = {k: v for k, v in validation['usage'].items() if v is not None}
        return {'proposal': validation['proposal'], 'provider': adapter.provider, 'model': response['model'],
            'requested_model': adapter.model, 'prompt_version': advisor_module.PROMPT_VERSION,
            'request_sha256': digest(prepared['messages']), 'report_sha256': digest(data['report']),
            'price_receipt': price, 'usage': usage, 'input_preflight': prepared['audit'],
            'exchange_capture': {'schema_version': 'advisor-exchange-reference-v1', 'available': True,
                'request_key': data['binding']['request_key'], 'capture_sha256': digest(capture),
                'exchange_manifest_sha256': digest(manifest), 'historical_wire_reconstructed': False}}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def _run_worker(adapter, report, directory, binding, *, wall_seconds, api_key=None, jobpilot_env=None, cancel_event=None):
    _guard(); wall_seconds = number(wall_seconds, .001, MAX_WALL_SECONDS)
    if cancel_event is not None and cancel_event.is_set(): raise AdvisorCancelled('cancelled before audited worker')
    if type(adapter) is not FreeAdvisor or adapter.transport is not advisor_module.http_json:
        raise ValueError('fixed_audited_adapter_required')
    prepared = adapter.preflight(report)
    directory = Path(directory).absolute(); private._safe_directory(directory.parent, private=True)
    if directory.exists() or directory.is_symlink(): raise ValueError('new_private_attempt_directory_required')
    settings = {'provider': adapter.provider, 'model': adapter.model, 'ollama_url': adapter.ollama_url,
        'parameters': list(adapter.parameters), 'timeout': min(adapter.timeout, wall_seconds),
        'api_key': api_key if api_key is not None else adapter.api_key or None,
        'jobpilot_env': str(Path(jobpilot_env).absolute()) if jobpilot_env is not None else None}
    body = canonical({'report': report, 'settings': settings, 'wall_seconds': wall_seconds,
        'implementation': _LOADED, 'directory': str(directory), 'binding': binding}).encode()
    if len(body) > 256000: raise ValueError('bounded_audited_worker_input_required')
    directory.mkdir(mode=0o700)
    files._write(directory, 'attempt.json', {'schema_version': 'audited-advisor-attempt-v1', 'binding': binding,
        'implementation': _LOADED, 'policy': POLICY, 'started_at': _stamp(), 'wall_seconds': wall_seconds,
        'request_payload_sha256': digest(prepared['payload']), 'reservation_owner': 'existing_ResearchRequests',
        'provider_completion_status': 'unknown_until_capture'})
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
        'PYTHONDONTWRITEBYTECODE': '1'}
    deadline = time.monotonic()+wall_seconds; process = None; outcome = 'failed'
    try:
        process = subprocess.Popen([sys.executable, '-B', '-m', 'cryptoforge.llm_audited_provider', '--worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
            cwd=Path(__file__).resolve().parents[2], start_new_session=True)
        while True:
            if cancel_event is not None and cancel_event.is_set(): raise AdvisorCancelled('audited provider cancelled')
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise AdvisorTimedOut('audited provider deadline exceeded')
            try:
                stdout, _ = process.communicate(input=body, timeout=min(.05, remaining)); break
            except subprocess.TimeoutExpired: body = None
        if cancel_event is not None and cancel_event.is_set(): raise AdvisorCancelled('audited provider cancelled')
        if time.monotonic() >= deadline or process.returncode == -signal.SIGALRM:
            raise AdvisorTimedOut('audited provider deadline exceeded')
        if process.returncode or len(stdout) > 64000: raise AdvisorUnavailable('audited worker failed')
        envelope = strict_json(stdout.decode(), max_bytes=64000)
        exact_fields(envelope, {'status', 'result', 'implementation'})
        if envelope['implementation'] != _LOADED or envelope['status'] != 'completed':
            raise AdvisorUnavailable('audited worker rejected request')
        result = envelope['result']; checked = verify_attempt(directory, expected_binding=binding, finished=False)
        if (checked['validation']['status'] != 'proposal_schema_valid_only'
                or checked['validation']['proposal'] != result['proposal']
                or result['report_sha256'] != digest(report) or result['provider'] != adapter.provider
                or result['requested_model'] != adapter.model
                or result['exchange_capture']['capture_sha256'] != checked['capture_sha256']):
            raise AdvisorUnavailable('audited worker result binding changed')
        validate_proposal(result['proposal'], report); _guard()
        if time.monotonic() >= deadline: raise AdvisorTimedOut('audited provider deadline exceeded')
        outcome = 'completed'; return result
    except (AdvisorCancelled, KeyboardInterrupt):
        outcome = 'cancelled'; raise AdvisorCancelled('audited provider cancelled') from None
    except AdvisorTimedOut:
        outcome = 'timed_out'; raise
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise AdvisorUnavailable('audited worker returned invalid data') from None
    finally:
        if process is not None: _stop(process)
        files._write(directory, 'outcome.json', {'schema_version': 'audited-advisor-local-outcome-v1',
            'status': outcome, 'finished_at': _stamp(), 'child_reaped': process is None or process.poll() is not None,
            'server_cancellation_verified': False, 'missing_usage_means_zero': False,
            'failed_or_interrupted_attempt_refunded': False})


def verify_attempt(directory, *, expected_binding=None, finished=True):
    """Offline integrity checks; no credential reads, HTTP or journal mutation."""
    _guard(); directory = private._safe_directory(directory, private=True)
    attempt = _read(directory, 'attempt.json')
    if attempt['implementation'] != _LOADED or attempt['policy'] != POLICY:
        raise ValueError('original_audited_attempt_required')
    binding = attempt['binding']
    if expected_binding is not None and expected_binding != binding: raise ValueError('original_API_binding_required')
    for key in ('API_journal_path_sha256', 'request_key', 'report_sha256'):
        if not _sha(binding[key]): raise ValueError('original_API_binding_required')
    validation = capture_sha = None
    if (directory/'capture.json').exists():
        capture = _read(directory, 'capture.json'); dispatch = _read(directory, 'dispatch.json')
        manifest = _read(directory/'exchange', 'manifest.json')
        validation = audit.verify(directory/'exchange'); provenance = _read(directory/'exchange', 'provenance.json')
        if (capture['implementation'] != _LOADED or capture['binding'] != binding
                or digest(manifest) != capture['exchange_manifest_sha256']
                or capture['response_body_sha256'] != provenance['original_response_body_sha256']
                or capture['request_payload_sha256'] != provenance['original_request_factory_payload_sha256']
                or capture['request_payload_sha256'] != attempt['request_payload_sha256']
                or capture['request_payload_sha256'] != dispatch['request_payload_sha256']
                or provenance['report_sha256'] != binding['report_sha256']):
            raise ValueError('original_transport_capture_binding_required')
        capture_sha = digest(capture)
    outcome = _read(directory, 'outcome.json') if finished else None
    if finished and outcome['status'] == 'completed' and (validation is None or validation['status'] != 'proposal_schema_valid_only'):
        raise ValueError('completed_capture_required')
    if sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()) > 2000000:
        raise ValueError('bounded_attempt_disk_required')
    return {'binding': binding, 'validation': validation, 'capture_sha256': capture_sha, 'local_outcome': outcome,
        'capture_available': validation is not None, 'server_cancellation_verified': False,
        'account_billing_or_semantic_quality_attested': False}


def propose_audited(coordinator, report, *, audit_root, provider='openrouter', model=None,
                    ollama_url='http://127.0.0.1:11434', daily_maximum=5, jobpilot_env=None,
                    cancel_event=None, require_verified_input_limit=True):
    """Opt in on an existing coordinator/phase; all earlier limits stay active."""
    _guard()
    if not isinstance(coordinator, coordinator_module.ResearchCoordinator): raise ValueError('existing_coordinator_required')
    if type(require_verified_input_limit) is not bool: raise ValueError('boolean_input_limit_requirement_required')
    if cancel_event is not None and cancel_event.is_set(): raise BudgetCancelled('cancelled before admission')
    report = deepcopy(validate_diagnostics(report))
    if report['partition'] != 'validation': raise ValueError('validation_report_required')
    model = model or (advisor_module.DEFAULT_MODEL if provider == 'openrouter' else 'nemotron-3-nano:30b')
    adapter = FreeAdvisor(provider=provider, model=model, ollama_url=ollama_url, parameters=('l2', 'threshold'))
    if provider == 'openrouter' and model != advisor_module.DEFAULT_MODEL: raise ValueError('fixed_free_exchange_model_required')
    prepared = adapter.preflight(report); journal = ResearchRequests(coordinator.paths['proposal'], daily_maximum=daily_maximum)
    cached = journal.read_cached(adapter, report)
    if cached is None: adapter.preflight(report, require_verified_input_limit=require_verified_input_limit)
    root = private._safe_directory(audit_root, private=True)
    binding = _journal_binding(journal, adapter, report)
    inputs = {'report': digest(report), 'provider': provider, 'model': model,
        'endpoint_sha256': digest(ollama_url) if provider == 'ollama' else None,
        'daily_maximum': daily_maximum, 'audited_worker': _LOADED}
    def execute():
        observed = dict(ZERO_USAGE)
        try:
            advice = journal.propose(adapter, report,
                admit=lambda: adapter.preflight(report, require_verified_input_limit=require_verified_input_limit),
                execute=lambda: _run_worker(adapter, report, root/binding['request_key'], binding,
                    wall_seconds=min(MAX_WALL_SECONDS, coordinator.budget.resource_policy['wall_ms_by_kind']['proposal']/1000),
                    api_key=os.environ.get('CRYPTOFORGE_OPENROUTER_API_KEY'), jobpilot_env=jobpilot_env, cancel_event=cancel_event))
        except AdvisorCancelled: raise BudgetCancelled('audited provider cancelled') from None
        except AdvisorTimedOut: raise BudgetTimedOut('audited provider deadline exceeded') from None
        if not advice['api_cached']: observed['remote_completions' if provider == 'openrouter' else 'local_llm_completions'] = 1
        envelope = {'result': {'diagnostics': report, 'advice': advice,
            'exchange_capture': _cached_reference(advice)}, 'observed': observed}
        if observed['remote_completions'] or observed['local_llm_completions']:
            envelope['tokens'] = provider_tokens(advice.get('usage'))
        _guard(); return envelope
    call = coordinator._dispatch('proposal', inputs, execute, cancel_event=cancel_event)
    reference = call['result']['exchange_capture']
    verified = False
    if reference['available']:
        checked = verify_attempt(root/binding['request_key'], expected_binding=binding)
        if checked['capture_sha256'] != reference['capture_sha256']:
            raise ValueError('original_cached_exchange_required_no_recapture')
        verified = True
    return {**call, 'input_admission': {'require_verified_input_limit': require_verified_input_limit,
        'current_preflight': prepared['audit'], 'scope': 'current_invocation_not_historical_wire'},
        'audit_policy_sha256': digest(POLICY), 'original_exchange_verified': verified}


def worker_main():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1300000, 1300000))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); os.nice(10)
    try:
        data = strict_json(sys.stdin.buffer.read(256001).decode(), max_bytes=256000)
        result = _evaluate(data)
        payload = canonical({'status': 'completed', 'result': result, 'implementation': _LOADED})
        if len(payload.encode()) > 64000: raise ValueError('bounded_audited_worker_output_required')
    except Exception:
        payload = canonical({'status': 'failed', 'result': None, 'implementation': _LOADED})
    sys.stdout.write(payload); return 0


if __name__ == '__main__': raise SystemExit(worker_main() if sys.argv[1:] == ['--worker'] else 2)
