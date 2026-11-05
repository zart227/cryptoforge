"""Bound the local free-advisor round trip, never execute model-supplied code.

The parent owns journals. A fixed worker reads credentials only after cache
lookup/admission, performs the existing adapter call, and returns bounded JSON.
Killing this client does not prove cancellation or zero tokens at the provider.
"""
import hashlib
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from cryptoforge.llm_research_advisor import (FreeAdvisor, http_json, jobpilot_credentials,
    AdvisorUnavailable, AdvisorCancelled, AdvisorTimedOut)
from cryptoforge.llm_research_contracts import strict_json, validate_proposal
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, number, validate_diagnostics


MAX_WALL_SECONDS = 65.0
CLEANUP_SECONDS = 2.0
SOURCE_NAMES = ('llm_provider_worker.py', 'llm_prompt_preflight.py', 'llm_research_advisor.py', 'llm_research_contracts.py', 'training_diagnostics.py')


def implementation():
    return {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}


_LOADED = implementation()


def _check_sources(expected):
    if expected != _LOADED or implementation() != _LOADED:
        raise ValueError('provider worker source changed; restart required')


def _stop(process):
    if process.poll() is None:
        process.kill()
    process.communicate(timeout=CLEANUP_SECONDS)


def run_provider_worker(advisor, report, *, wall_seconds, api_key=None, jobpilot_env=None, cancel_event=None):
    wall_seconds = number(wall_seconds, 0.001, MAX_WALL_SECONDS)
    if cancel_event is not None and cancel_event.is_set():
        raise AdvisorCancelled('provider cancelled before worker launch')
    _check_sources(_LOADED)
    if type(advisor) is not FreeAdvisor or advisor.transport is not http_json:
        raise ValueError('fixed provider adapter without custom transport required')
    validate_diagnostics(report)
    advisor.preflight(report)
    settings = {'provider': advisor.provider, 'model': advisor.model, 'ollama_url': advisor.ollama_url,
        'parameters': list(advisor.parameters), 'timeout': min(advisor.timeout, wall_seconds),
        'api_key': api_key if api_key is not None else advisor.api_key or None,
        'jobpilot_env': str(Path(jobpilot_env).resolve()) if jobpilot_env is not None else None}
    body = canonical({'report': report, 'settings': settings, 'wall_seconds': wall_seconds, 'implementation': _LOADED}).encode()
    if len(body) > 256000:
        raise ValueError('bounded provider worker input required')
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
           'PYTHONDONTWRITEBYTECODE': '1'}
    # One deadline includes process startup, credential read, catalog and completion.
    deadline = time.monotonic()+wall_seconds
    process = subprocess.Popen([sys.executable, '-m', 'cryptoforge.llm_provider_worker', '--worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
        cwd=Path(__file__).resolve().parents[2], start_new_session=True)
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise AdvisorCancelled('provider round trip cancelled')
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise AdvisorTimedOut('local provider deadline exceeded')
            try:
                stdout, _ = process.communicate(input=body, timeout=min(0.05, remaining))
                break
            except subprocess.TimeoutExpired:
                body = None
        if cancel_event is not None and cancel_event.is_set():
            raise AdvisorCancelled('provider round trip cancelled')
        if time.monotonic() >= deadline or process.returncode == -signal.SIGALRM:
            raise AdvisorTimedOut('local provider deadline exceeded')
        if process.returncode or len(stdout) > 512000:
            raise AdvisorUnavailable('provider worker failed or output exceeded limit')
        envelope = strict_json(stdout.decode(), max_bytes=512000)
        exact_fields(envelope, {'status', 'result', 'implementation'})
        _check_sources(envelope['implementation'])
        if envelope['status'] != 'completed':
            raise AdvisorUnavailable('provider worker rejected request')
        result = envelope['result']
        validate_proposal(result['proposal'], report)
        if (result['provider'] != advisor.provider or result['requested_model'] != advisor.model
                or result['report_sha256'] != digest(report)):
            raise AdvisorUnavailable('provider worker result identity mismatch')
        # Decode/validation must also finish inside the local waiting budget.
        if time.monotonic() >= deadline:
            raise AdvisorTimedOut('local provider deadline exceeded')
        return {**result, 'provider_execution': {'schema_version': 'local-provider-deadline-v1',
            'wall_seconds': wall_seconds, 'cleanup_grace_seconds': CLEANUP_SECONDS,
            'implementation': _LOADED, 'server_cancellation_verified': False}}
    except KeyboardInterrupt:
        raise AdvisorCancelled('provider round trip interrupted') from None
    except (UnicodeError, KeyError, TypeError, ValueError):
        raise AdvisorUnavailable('provider worker returned invalid data') from None
    finally:
        _stop(process)


def evaluate(data):
    exact_fields(data, {'report', 'settings', 'wall_seconds', 'implementation'})
    _check_sources(data['implementation'])
    settings = data['settings']
    exact_fields(settings, {'provider', 'model', 'ollama_url', 'parameters', 'timeout', 'api_key', 'jobpilot_env'})
    wall_seconds = number(data['wall_seconds'], 0.001, MAX_WALL_SECONDS)
    key, path = settings['api_key'], settings['jobpilot_env']
    if (key is not None and (not isinstance(key, str) or len(key) > 4096)
            or path is not None and (not isinstance(path, str) or len(path) > 4096)
            or not isinstance(settings['parameters'], list)):
        raise ValueError('bounded provider settings required')
    # Also stop if the supervisor disappears after sending the request.
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, wall_seconds)
    try:
        FreeAdvisor(provider=settings['provider'], model=settings['model'], ollama_url=settings['ollama_url'],
            parameters=tuple(settings['parameters']), timeout=settings['timeout']).preflight(data['report'])
        credentials = jobpilot_credentials(path) if path is not None else {}
        advisor = FreeAdvisor(provider=settings['provider'], model=settings['model'],
            api_key=key if key is not None else credentials.get('OPENROUTER_API_KEY', ''),
            ollama_url=settings['ollama_url'], parameters=tuple(settings['parameters']), timeout=settings['timeout'])
        if advisor.provider == 'openrouter' and not advisor.model.endswith(':free'):
            raise ValueError('fixed free model required')
        result = advisor.propose(data['report'])
        _check_sources(data['implementation'])
        return result
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def worker_main():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    os.nice(10)
    try:
        raw = sys.stdin.buffer.read(256001)
        data = strict_json(raw.decode(), max_bytes=256000)
        result = evaluate(data)
        payload = canonical({'status': 'completed', 'result': result, 'implementation': _LOADED})
        if len(payload.encode()) > 512000:
            raise ValueError('provider worker output too large')
    except Exception:
        payload = canonical({'status': 'failed', 'result': None, 'implementation': _LOADED})
    sys.stdout.write(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(worker_main() if sys.argv[1:] == ['--worker'] else 2)
