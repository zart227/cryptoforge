import copy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import threading

import pytest

from cryptoforge import ollama_decision_readiness as readiness
from cryptoforge import ollama_systemone_fixture as bridge
from cryptoforge.training_diagnostics import canonical, digest


@pytest.fixture
def catalog():
    return {'schema_version': 'semantic-research-questions-v1', 'policy_version': 'local-wire-synthetic-v1',
        'questions': {
            'mechanism': {'type': 'choice', 'instructions': 'Which change is described in `experiment`?',
                'criteria': {'threshold': 'Changes a threshold.', 'unknown': 'No supported choice.'},
                'minimum_confidence': 0.8},
            'supported': {'type': 'noul', 'instructions': 'Does the supplied result support the conclusion?',
                'criteria': {'true': 'Supported by supplied evidence.', 'false': 'Unsupported by supplied evidence.'},
                'accept_below': 0.2, 'accept_above': 0.8},
            'clarity': {'type': 'score', 'instructions': 'How specific is the supplied hypothesis?',
                'criteria': ['Unclear.', 'Partly clear.', 'Clear and specific.'], 'minimum_confidence': 0.8}}}


@pytest.fixture
def prepared(catalog):
    return bridge.prepare_request({'experiment': 'Synthetic threshold change.'}, catalog,
        model='nimble:latest', digest_pin='d'*64, version='0.35.1')


@pytest.fixture
def response(catalog):
    return {'model': 'nimble:latest', 'usage': {'input_tokens': 123, 'output_tokens': 7},
        'answers': {'mechanism': {'type': 'choice', 'choice': 'threshold', 'confidence': 0.9,
                                'probabilities': {'threshold': 0.9, 'unknown': 0.1}},
                    'supported': {'type': 'noul', 'noul': 0.5},
                    'clarity': {'type': 'score', 'score': 1.8, 'confidence': 0.9,
                        'probabilities': {'0': 0.0, '1': 0.2, '2': 0.8},
                        'legend': {str(i): v for i, v in enumerate(catalog['questions']['clarity']['criteria'])}}}}


@pytest.fixture
def metadata(monkeypatch):
    values = {'/api/version': {'version': '0.35.1'},
        '/api/tags': {'models': [{'name': 'nimble:latest', 'model': 'nimble:latest', 'digest': 'd'*64}]},
        '/api/show': {'capabilities': ['decision'], 'remote_host': '', 'remote_model': ''}}
    calls = []
    def transport(endpoint, path, payload, timeout):
        calls.append((endpoint, path, copy.deepcopy(payload), timeout))
        value = values[path]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)
    monkeypatch.setattr(readiness, '_metadata_json', transport)
    return values, calls


def test_metadata_compatible_is_not_inference_permission_or_identity_proof(metadata):
    values, calls = metadata
    before = copy.deepcopy(values)
    result = readiness.inspect_readiness(model='nimble:latest', expected_digest='sha256:'+'d'*64)
    assert result['status'] == 'metadata_compatible' and result['reason_code'] is None
    assert result['observations'] == {'server_version': '0.35.1', 'model_digest': 'sha256:'+'d'*64,
        'digest_matches_expected': True, 'capabilities': ['decision']}
    assert [(path, body) for _, path, body, _ in calls] == [('/api/version', None), ('/api/tags', None),
                                                                        ('/api/show', {'model': 'nimble:latest'})]
    assert result['metadata_request_count'] == 3 and result['inference_requests'] == 0
    assert not result['live_execution_authorized'] and not result['model_load_verified']
    assert not result['live_access_verified'] and not result['atomic_model_snapshot']
    assert not result['credentials_read'] and not result['automatic_pull_or_start']
    assert result['model_identity_assurance'] == 'server_metadata_declaration_only'
    assert result['receipt_sha256'] == digest({k: v for k, v in result.items() if k != 'receipt_sha256'})
    assert before == values


@pytest.mark.parametrize('endpoint', ['https://127.0.0.1:11434', 'http://localhost:11434',
    'http://192.0.2.1:11434', 'http://127.0.0.1', 'http://u:p@127.0.0.1:11434',
    'http://127.0.0.1:11434/prefix', 'http://127.0.0.1:11434?token=x',
    'http://127.0.0.1:11434#x', 'http://127.0.0.1:0', 'http://127.0.0.1:65536',
    'http://127.0.0.1:11434\n', 'http://[::1%25eth0]:11434'])
def test_nonlocal_or_ambiguous_endpoints_refused_before_transport(endpoint, metadata):
    with pytest.raises(ValueError, match='loopback'):
        readiness.inspect_readiness(endpoint=endpoint, model='nimble:latest')
    assert metadata[1] == []


@pytest.mark.parametrize('endpoint', ['http://127.0.0.1:11434', 'http://127.0.0.2:1234/', 'http://[::1]:11434'])
def test_loopback_ip_literals_are_explicit(endpoint):
    assert readiness.local_endpoint(endpoint) == endpoint.rstrip('/')


@pytest.mark.parametrize('model', ['nimble', 'clef:cloud', 'local-cloud:latest', 'x:cloud-large',
    'registry.example/nimble:latest', 'nimble:latest\n', 'Nimble:latest'])
def test_cloud_and_ambiguous_model_names_refused(model, metadata):
    with pytest.raises(ValueError, match='local model'):
        readiness.inspect_readiness(model=model)
    assert metadata[1] == []


@pytest.mark.parametrize('change,reason,count', [
    ('old_version', 'unsupported_server_version', 1), ('prerelease', 'unsupported_server_version', 1),
    ('missing_version', 'unsupported_server_version', 1), ('missing_model', 'model_not_installed', 2),
    ('duplicate_model', 'ambiguous_model_metadata', 2), ('bad_digest', 'invalid_metadata', 2),
    ('digest_mismatch', 'model_digest_mismatch', 2), ('bad_tags', 'invalid_metadata', 2),
    ('remote_host', 'remote_model_metadata_refused', 3), ('remote_model', 'remote_model_metadata_refused', 3),
    ('remote_null', 'remote_model_metadata_refused', 3), ('chat_only', 'decision_capability_missing', 3),
    ('missing_caps', 'invalid_metadata', 3), ('bad_caps', 'invalid_metadata', 3)])
def test_metadata_failures_stop_without_inference_or_pull(metadata, change, reason, count):
    values, calls = metadata
    if change == 'old_version': values['/api/version']['version'] = '0.34.9'
    elif change == 'prerelease': values['/api/version']['version'] = '0.35.1-rc1'
    elif change == 'missing_version': values['/api/version'] = {}
    elif change == 'missing_model': values['/api/tags']['models'] = []
    elif change == 'duplicate_model': values['/api/tags']['models'] *= 2
    elif change == 'bad_digest': values['/api/tags']['models'][0]['digest'] = 'short'
    elif change == 'digest_mismatch': values['/api/tags']['models'][0]['digest'] = 'a'*64
    elif change == 'bad_tags': values['/api/tags']['models'] = [None]
    elif change in ('remote_host', 'remote_model'): values['/api/show'][change] = 'paid remote'
    elif change == 'remote_null': values['/api/show']['remote_host'] = None
    elif change == 'chat_only': values['/api/show']['capabilities'] = ['completion']
    elif change == 'missing_caps': values['/api/show'] = {}
    else: values['/api/show']['capabilities'] = ['decision', 'decision']
    result = readiness.inspect_readiness(model='nimble:latest', expected_digest='d'*64)
    assert result['status'] == 'incompatible' and result['reason_code'] == reason
    assert len(calls) == count and result['inference_requests'] == 0


def test_unavailable_metadata_stays_unknown_and_does_not_retry(metadata):
    values, calls = metadata
    values['/api/version'] = readiness.MetadataUnavailable('backend_unavailable')
    result = readiness.inspect_readiness(model='nimble:latest')
    assert result['status'] == 'unavailable' and result['observations'] == {}
    assert len(calls) == 1 and result['metadata_requests'][0]['status'] == 'failed'


def test_discovery_without_digest_pin_is_explicitly_unpinned(metadata):
    result = readiness.inspect_readiness(model='nimble:latest')
    assert result['expected_digest'] is None and result['observations']['digest_matches_expected'] is None


class FakeConnection:
    status = 200
    raw = b'{"version":"0.35.1"}'
    encoding = 'identity'
    instances = []

    def __init__(self, host, port, timeout):
        self.arguments, self.requests, self.closed = (host, port, timeout), [], False
        self.instances.append(self)

    def request(self, *args): self.requests.append(args)
    def getresponse(self): return self
    def getheader(self, name, default=None): return self.encoding if name == 'Content-Encoding' else default
    def read(self, size): self.read_limit = size; return self.raw[:size]
    def close(self): self.closed = True


@pytest.fixture
def connection(monkeypatch):
    class Connection(FakeConnection):
        instances = []
    monkeypatch.setattr(readiness.http.client, 'HTTPConnection', Connection)
    return Connection


def test_metadata_http_uses_fixed_paths_no_auth_proxy_or_redirect_handler(connection, monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://paid.invalid:9999')
    assert readiness._metadata_json('http://127.0.0.1:11434', '/api/version', None, 1) == {'version': '0.35.1'}
    conn = connection.instances[0]
    assert conn.arguments == ('127.0.0.1', 11434, 1) and conn.closed
    assert conn.requests == [('GET', '/api/version', None, {'Accept': 'application/json', 'Connection': 'close'})]
    assert conn.read_limit == readiness.MAX_METADATA_BYTES + 1
    readiness._metadata_json('http://127.0.0.1:11434', '/api/show', {'model': 'nimble:latest'}, 1)
    assert connection.instances[1].requests[0][0:3] == ('POST', '/api/show', b'{"model":"nimble:latest"}')


@pytest.mark.parametrize('path,payload', [('/v1/systemone', {'model': 'nimble:latest'}),
    ('/api/pull', {'model': 'nimble:latest'}), ('/api/generate', {'model': 'nimble:latest'}),
    ('/api/show', None), ('/api/tags', {}), ('/api/show', {'model': 'nimble:latest', 'verbose': True})])
def test_http_helper_cannot_be_used_as_inference_or_pull_transport(path, payload, connection):
    with pytest.raises(ValueError): readiness._metadata_json('http://127.0.0.1:11434', path, payload, 1)
    assert connection.instances == []


@pytest.mark.parametrize('change,reason', [('redirect', 'metadata_http_refused'),
    ('unauthorized', 'metadata_http_refused'), ('compressed', 'metadata_encoding_refused'),
    ('oversized', 'metadata_too_large'), ('duplicate', 'metadata_invalid_json'),
    ('invalid_utf8', 'metadata_invalid_json'), ('nonfinite', 'metadata_invalid_json')])
def test_http_errors_are_sanitized_and_connection_closed(change, reason, connection):
    if change == 'redirect': connection.status = 302
    elif change == 'unauthorized': connection.status = 401
    elif change == 'compressed': connection.encoding = 'gzip'
    elif change == 'oversized': connection.raw = b'x'*(readiness.MAX_METADATA_BYTES+1)
    elif change == 'duplicate': connection.raw = b'{"secret":"x","secret":"y"}'
    elif change == 'invalid_utf8': connection.raw = b'\xff'
    else: connection.raw = b'{"secret":NaN}'
    with pytest.raises(readiness.MetadataUnavailable, match='^'+reason+'$'):
        readiness._metadata_json('http://127.0.0.1:11434', '/api/version', None, 1)
    assert connection.instances[0].closed


def test_readiness_cli_reserves_private_output_before_network(metadata, tmp_path):
    path = tmp_path/'readiness.json'
    args = ['--model', 'nimble:latest', '--expected-digest', 'd'*64, '--output', str(path)]
    assert readiness.main(args) == 0 and path.stat().st_mode & 0o777 == 0o600
    before, count = path.read_bytes(), len(metadata[1])
    with pytest.raises(FileExistsError): readiness.main(args)
    assert path.read_bytes() == before and len(metadata[1]) == count


def test_readiness_cli_unavailable_exit_and_failed_receipt(metadata, tmp_path):
    metadata[0]['/api/version'] = readiness.MetadataUnavailable('backend_unavailable')
    path = tmp_path/'readiness.json'
    assert readiness.main(['--model', 'nimble:latest', '--output', str(path)]) == 2
    assert json.loads(path.read_text())['reason_code'] == 'backend_unavailable'


@contextmanager
def loopback_metadata(mode):
    calls, stop = [], threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def respond(self):
            payload = None if self.command == 'GET' else json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.command, self.path, payload, self.headers.get('Authorization')))
            if mode == 'redirect':
                self.send_response(302); self.send_header('Location', 'https://unrequested.invalid/'); self.end_headers(); return
            if mode == 'timeout': stop.wait(1)
            if self.path == '/api/version': body = {'version': '0.35.1'}
            elif self.path == '/api/tags': body = {'models': [{'name': 'nimble:latest', 'digest': 'd'*64}]}
            elif self.path == '/api/show':
                body = {'capabilities': ['decision'], 'remote_host': 'https://paid.invalid' if mode == 'remote' else ''}
            else:
                self.send_error(500); return
            raw = canonical(body).encode()
            self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass
        do_GET = respond
        do_POST = respond
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls
    finally:
        stop.set(); server.shutdown(); server.server_close(); thread.join(timeout=1)


@pytest.mark.parametrize('mode,status,count', [('ready', 'metadata_compatible', 3),
    ('remote', 'incompatible', 3), ('redirect', 'unavailable', 1), ('timeout', 'unavailable', 1)])
def test_real_loopback_metadata_never_runs_inference_or_follows_redirects(mode, status, count, monkeypatch):
    monkeypatch.setenv('HTTP_PROXY', 'http://unrequested.invalid:9999')
    monkeypatch.setenv('OLLAMA_API_KEY', 'synthetic-unused-key')
    with loopback_metadata(mode) as (endpoint, calls):
        result = readiness.inspect_readiness(endpoint=endpoint, model='nimble:latest', timeout=0.1)
    assert result['status'] == status and len(calls) == count
    assert all(path in ('/api/version', '/api/tags', '/api/show') and auth is None for _, path, _, auth in calls)
    assert result['inference_requests'] == 0


def test_wire_keeps_thresholds_in_code_and_uses_explicit_digest(prepared, catalog):
    assert prepared['declared_model_pin'] == {'model': 'nimble:latest', 'model_digest': 'sha256:'+'d'*64,
                                             'server_version': '0.35.1'}
    wire = prepared['wire_request']
    assert set(wire) == {'model', 'state', 'questions', 'keep_alive'} and wire['keep_alive'] == 0
    for name, q in wire['questions'].items():
        assert set(q) == {'type', 'instructions', 'criteria'}
        assert q['criteria'] == catalog['questions'][name]['criteria']
    assert prepared['wire_bytes'] == len(canonical(wire).encode())
    assert not prepared['hard_input_token_limit_verified'] and not prepared['byte_limit_is_token_limit']


def test_fixture_roundtrip_has_no_external_usage_or_model_provenance(prepared, response, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('offline fixture must not connect or read keys')
    monkeypatch.setattr(socket, 'socket', forbidden)
    monkeypatch.setattr(os, 'getenv', forbidden)
    result = bridge.evaluate_fixture(prepared, response)
    assert result['compatible_answer_count'] == 3 and result['mapping_errors'] == {}
    assert result['normalized_judgments']['answers']['supported']['status'] == 'abstain'
    assert result['normalized_judgments']['answers']['clarity']['value'] == 1.8
    assert result['normalized_judgments']['origin'] == 'mock'
    assert result['source_fixture_sha256'] == digest(response)
    assert result['fixture_reported_usage'] == {'input_tokens': 123, 'output_tokens': 7}
    assert result['model_identity_assurance'] == 'fixture_declaration_only'
    assert not result['usage_is_external_observation'] and not result['live_access_verified']
    assert not result['live_model_quality_evaluated'] and not result['independent_trading_evidence']
    assert result['api_calls'] == 0


@pytest.mark.parametrize('change', ['missing', 'noul_confidence', 'noul_type', 'choice_value', 'rounded_sum',
                                   'score_expectation', 'score_legend', 'missing_legend'])
def test_bad_answer_does_not_erase_valid_companions_or_get_repaired(prepared, response, change):
    affected = 'supported'
    if change == 'missing': response['answers'].pop(affected)
    elif change == 'noul_confidence': response['answers'][affected]['confidence'] = 0.99
    elif change == 'noul_type': response['answers'][affected]['type'] = 'score'
    elif change == 'choice_value':
        affected = 'mechanism'; response['answers'][affected]['choice'] = 'unknown'
    elif change == 'rounded_sum':
        affected = 'mechanism'; response['answers'][affected]['probabilities']['threshold'] = 0.8999
    elif change == 'score_expectation':
        affected = 'clarity'; response['answers'][affected]['score'] = 0.1
    elif change == 'score_legend':
        affected = 'clarity'; response['answers'][affected]['legend']['2'] = 'Changed meaning.'
    else:
        affected = 'clarity'; response['answers'][affected].pop('legend')
    result = bridge.evaluate_fixture(prepared, response)
    assert result['compatible_answer_count'] == 2
    assert result['mapping_errors'] == {affected: 'invalid_or_missing_ollama_fixture_answer'}
    assert result['normalized_judgments']['answers'][affected]['status'] == 'error'


@pytest.mark.parametrize('change', ['state', 'catalog', 'model', 'digest', 'version', 'wire', 'source', 'hash'])
def test_request_mutation_or_implementation_drift_is_rejected(prepared, response, change):
    if change == 'state': prepared['state']['experiment'] = 'Other evidence.'
    elif change == 'catalog': prepared['catalog']['questions']['supported']['accept_above'] = 0.9
    elif change == 'model': prepared['declared_model_pin']['model'] = 'tev1:latest'
    elif change == 'digest': prepared['declared_model_pin']['model_digest'] = 'sha256:'+'a'*64
    elif change == 'version': prepared['declared_model_pin']['server_version'] = '0.36.0'
    elif change == 'wire': prepared['wire_request']['keep_alive'] = -1
    elif change == 'source': prepared['implementation_sources']['normalizer'] = '0'*64
    else: prepared['request_sha256'] = '0'*64
    with pytest.raises(ValueError, match='changed'): bridge.evaluate_fixture(prepared, response)


@pytest.mark.parametrize('change', ['model', 'unknown_question', 'unknown_field', 'missing_usage'])
def test_response_envelope_must_match_request(prepared, response, change):
    if change == 'model': response['model'] = 'jev-1.13.0'
    elif change == 'unknown_question': response['answers']['other'] = {'type': 'noul', 'noul': 0.9}
    elif change == 'unknown_field': response['tool_calls'] = []
    else: response.pop('usage')
    with pytest.raises(ValueError): bridge.evaluate_fixture(prepared, response)


@pytest.mark.parametrize('value', [None, -1, True, 1.5, '10', 1_000_000_001])
def test_fixture_usage_requires_explicit_integer_fields(prepared, response, value):
    response['usage']['input_tokens'] = value
    with pytest.raises(ValueError, match='fixture token'): bridge.evaluate_fixture(prepared, response)


def test_cached_count_is_retained_without_inventing_billing_rules(prepared, response):
    response['prompt_eval_cached_count'] = 200
    result = bridge.evaluate_fixture(prepared, response)
    assert result['fixture_reported_cached_input_tokens'] == 200
    assert result['fixture_reported_usage']['input_tokens'] == 123
    assert not result['cached_usage_accounting_verified']


def test_wire_byte_boundary_uses_json_escaping_without_truncation(catalog, monkeypatch):
    state = {'experiment': '\U0001f4c8'*100}
    args = dict(model='nimble:latest', digest_pin='d'*64, version='0.35.1')
    prepared = bridge.prepare_request(state, catalog, **args)
    monkeypatch.setattr(bridge, 'MAX_WIRE_BYTES', prepared['wire_bytes'])
    assert bridge.prepare_request(state, catalog, **args)['wire_bytes'] == prepared['wire_bytes']
    monkeypatch.setattr(bridge, 'MAX_WIRE_BYTES', prepared['wire_bytes']-1)
    with pytest.raises(ValueError, match='no truncation'): bridge.prepare_request(state, catalog, **args)
    assert len(state['experiment']) == 100


@pytest.mark.parametrize('state', [{}, [], {'text': 'x'*32_000}])
def test_state_bounds_before_fixture_preparation(state, catalog):
    with pytest.raises(ValueError, match='state'):
        bridge.prepare_request(state, catalog, model='nimble:latest', digest_pin='d'*64, version='0.35.1')


@pytest.mark.parametrize('value', ['d'*12, 'sha256:'+'D'*64, 'd'*64+'\n', None])
def test_model_digest_requires_full_exact_hash(value, catalog):
    with pytest.raises(ValueError, match='digest'):
        bridge.prepare_request({'x': 'synthetic'}, catalog, model='nimble:latest', digest_pin=value, version='0.35.1')


def test_offline_cli_creates_private_new_files_only(catalog, response, tmp_path):
    state, questions, request, fixture, result = [tmp_path/name for name in
        ('state.json', 'questions.json', 'request.json', 'fixture.json', 'result.json')]
    state.write_text(canonical({'experiment': 'Synthetic threshold.'})); questions.write_text(canonical(catalog))
    fixture.write_text(canonical(response))
    args = ['prepare', '--state', str(state), '--questions', str(questions), '--model', 'nimble:latest',
        '--model-digest', 'd'*64, '--server-version', '0.35.1', '--output', str(request)]
    assert bridge.main(args) == 0
    assert bridge.main(['fixture', '--request', str(request), '--response', str(fixture), '--output', str(result)]) == 0
    assert json.loads(result.read_text())['api_calls'] == 0
    for path in (request, result): assert path.stat().st_mode & 0o777 == 0o600
    before = request.read_bytes()
    with pytest.raises(FileExistsError): bridge.main(args)
    assert request.read_bytes() == before


def test_offline_cli_has_no_live_execution_command():
    with pytest.raises(SystemExit) as exc: bridge.main(['live'])
    assert exc.value.code == 2
