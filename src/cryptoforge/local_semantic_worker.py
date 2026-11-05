"""Fixed local System One client supervised by one parent waiting deadline.

The Ollama server's compute and cancellation are not controlled by killing this
client. No credentials, discovery, model pull, arbitrary transport or code tools.
"""
from datetime import datetime, timezone
import hashlib
import http.client
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

from cryptoforge.local_semantic_contracts import validate_request, normalize_transport, check_show_metadata, inference_identity
from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, number


MAX_WALL_SECONDS = 30.0
CLEANUP_SECONDS = 2.0
LEGACY_SOURCE_NAMES = ('local_semantic_worker.py', 'local_semantic_contracts.py', 'ollama_decision_readiness.py',
    'typesafe_judgment_contracts.py', 'semantic_research_catalog.py', 'training_diagnostics.py', 'llm_research_contracts.py')
SOURCE_NAMES = LEGACY_SOURCE_NAMES + ('source_semantic_contracts.py', 'semantic_event_review.py',
    'semantic_asset_registry.py', 'semantic_source_collector.py', 'semantic_source_snapshot.py',
    'semantic_source_transport.py', 'announcement_sources.py')


def implementation():
    return {name: hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in SOURCE_NAMES}


_LOADED = implementation()


class SemanticUnavailable(RuntimeError):
    pass


class SemanticCancelled(SemanticUnavailable):
    pass


class SemanticTimedOut(SemanticUnavailable):
    pass


def _check_sources(expected):
    if expected != _LOADED or implementation() != _LOADED:
        raise ValueError('semantic worker source changed; restart required')


def _json(request, path, payload, *, timeout, limit):
    if (path, payload is None) not in {('/api/version', True), ('/api/show', False), ('/v1/systemone', False)}:
        raise ValueError('fixed semantic routes only')
    endpoint = urlsplit(request['endpoint'])
    connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=timeout)
    body = None if payload is None else canonical(payload).encode()
    headers = {'Accept': 'application/json', 'Connection': 'close'}
    if body is not None: headers['Content-Type'] = 'application/json'
    try:
        connection.request('GET' if payload is None else 'POST', path, body, headers)
        response = connection.getresponse()
        if response.status != 200 or response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise SemanticUnavailable('semantic HTTP status or encoding refused')
        raw = response.read(limit+1)
        if len(raw) > limit:
            raise SemanticUnavailable('semantic HTTP response too large')
        return strict_json(raw.decode('utf-8'), max_bytes=limit)
    except socket.timeout:
        raise SemanticTimedOut('semantic socket waiting limit exceeded') from None
    except (OSError, http.client.HTTPException, ValueError, UnicodeError):
        raise SemanticUnavailable('semantic HTTP response unavailable or invalid') from None
    finally:
        connection.close()


def evaluate(data):
    exact_fields(data, {'request', 'wall_seconds', 'implementation'})
    _check_sources(data['implementation'])
    request = validate_request(data['request'])
    wall = number(data['wall_seconds'], 0.001, MAX_WALL_SECONDS)
    signal.signal(signal.SIGALRM, signal.SIG_DFL)
    signal.setitimer(signal.ITIMER_REAL, wall)
    try:
        before = _json(request, '/api/version', None, timeout=wall, limit=4000)
        exact_fields(before, {'version'})
        if before['version'] != request['server_version']:
            raise ValueError('unchecked server profile')
        show = _json(request, '/api/show', {'model': request['model_reference']}, timeout=wall, limit=256000)
        capabilities = check_show_metadata(show, request)
        # The native local digest reference, never the mutable display tag.
        response = _json(request, '/v1/systemone', request['wire_request'], timeout=wall, limit=64000)
        received_at = datetime.now(timezone.utc).isoformat()
        after = _json(request, '/api/version', None, timeout=wall, limit=4000)
        if after != before:
            raise ValueError('server version changed during evaluation')
        result = {'request_sha256': request['request_sha256'], 'inference_identity_sha256': inference_identity(request),
            'response': response, 'metadata': {
            'server_version': before['version'], 'model_reference': request['model_reference'],
            'version_before_sha256': digest(before), 'version_after_sha256': digest(after),
            'show_sha256': digest(show), 'capabilities': capabilities,
            'checked_at': datetime.now(timezone.utc).isoformat(),
            **({'response_received_at': received_at}
               if request['schema_version'] == 'local-semantic-source-request-v2' else {})}}
        normalize_transport(request, result)
        _check_sources(data['implementation'])
        return result
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def _stop(process):
    if process.poll() is None: process.kill()
    process.communicate(timeout=CLEANUP_SECONDS)


def run_worker(request, *, wall_seconds, cancel_event=None):
    wall = number(wall_seconds, 0.001, MAX_WALL_SECONDS)
    if cancel_event is not None and cancel_event.is_set():
        raise SemanticCancelled('semantic cancelled before worker launch')
    validate_request(request); _check_sources(_LOADED)
    body = canonical({'request': request, 'wall_seconds': wall, 'implementation': _LOADED}).encode()
    if len(body) > 256000:
        raise ValueError('bounded semantic worker input required')
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
        'PYTHONDONTWRITEBYTECODE': '1'}
    deadline = time.monotonic()+wall
    process = subprocess.Popen([sys.executable, '-m', 'cryptoforge.local_semantic_worker', '--worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
        cwd=Path(__file__).resolve().parents[2], start_new_session=True)
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set(): raise SemanticCancelled('semantic cancelled')
            remaining = deadline-time.monotonic()
            if remaining <= 0: raise SemanticTimedOut('local semantic deadline exceeded')
            try:
                stdout, _ = process.communicate(input=body, timeout=min(0.05, remaining)); break
            except subprocess.TimeoutExpired:
                body = None
        if cancel_event is not None and cancel_event.is_set(): raise SemanticCancelled('semantic cancelled')
        if time.monotonic() >= deadline or process.returncode == -signal.SIGALRM:
            raise SemanticTimedOut('local semantic deadline exceeded')
        if process.returncode or len(stdout) > 256000:
            raise SemanticUnavailable('semantic worker failed or exceeded output limit')
        envelope = strict_json(stdout.decode(), max_bytes=256000)
        exact_fields(envelope, {'status', 'result', 'implementation'})
        _check_sources(envelope['implementation'])
        if envelope['status'] == 'timed_out': raise SemanticTimedOut('semantic HTTP waiting limit exceeded')
        if envelope['status'] != 'completed': raise SemanticUnavailable('semantic worker rejected request')
        if envelope['result']['request_sha256'] != request['request_sha256']:
            raise SemanticUnavailable('fresh semantic worker request mismatch')
        normalize_transport(request, envelope['result'])
        if time.monotonic() >= deadline: raise SemanticTimedOut('local semantic deadline exceeded')
        return envelope['result']
    except KeyboardInterrupt:
        raise SemanticCancelled('semantic interrupted') from None
    except (UnicodeError, KeyError, TypeError, ValueError):
        raise SemanticUnavailable('semantic worker returned invalid data') from None
    finally:
        _stop(process)


def worker_main():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256*1024*1024, 256*1024*1024))
    os.nice(10)
    result, status = None, 'failed'
    try:
        raw = sys.stdin.buffer.read(256001)
        result = evaluate(strict_json(raw.decode(), max_bytes=256000)); status = 'completed'
    except SemanticTimedOut:
        status = 'timed_out'
    except Exception:
        pass
    payload = canonical({'status': status, 'result': result, 'implementation': _LOADED})
    if len(payload.encode()) > 256000:
        payload = canonical({'status': 'failed', 'result': None, 'implementation': _LOADED})
    sys.stdout.write(payload)
    return 0


if __name__ == '__main__':
    raise SystemExit(worker_main() if sys.argv[1:] == ['--worker'] else 2)
