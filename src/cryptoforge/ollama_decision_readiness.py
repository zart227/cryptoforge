"""Metadata-only local decision readiness; never starts, pulls or runs a model."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.research_training_diagnostics import canonical, digest, number


MAX_METADATA_BYTES = 256_000
MIN_SERVER_VERSION = (0, 35, 1)  # Conservative common floor including Clef.


def local_endpoint(value):
    """IP literals avoid DNS and environment proxy/credential discovery."""
    if not isinstance(value, str) or not value.isascii() or any(c.isspace() for c in value):
        raise ValueError('explicit loopback HTTP endpoint required')
    try:
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        if (parsed.scheme != 'http' or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or host is None or '%' in host or port is None or not 1 <= port <= 65535):
            raise ValueError
        address = ipaddress.ip_address(host)
        if not address.is_loopback:
            raise ValueError
    except ValueError:
        raise ValueError('explicit loopback HTTP endpoint required') from None
    hostname = f'[{address.compressed}]' if address.version == 6 else address.compressed
    return f'http://{hostname}:{port}'


def local_model(value):
    # A tag is required even for latest; identity is separately pinned by digest.
    if (not isinstance(value, str)
            or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}:[a-z0-9][a-z0-9._-]{0,63}', value)
            or 'cloud' in value):
        raise ValueError('explicit local model:tag required; cloud names refused')
    return value


def model_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', value):
        raise ValueError('full SHA256 model digest required')
    return 'sha256:' + value.removeprefix('sha256:')


def server_version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}', value):
        raise ValueError('stable server version required')
    if tuple(map(int, value.split('.'))) < MIN_SERVER_VERSION:
        raise ValueError('server below conservative System One version floor')
    return value


class MetadataUnavailable(RuntimeError):
    pass


def _metadata_json(endpoint, path, payload, timeout):
    """Fixed read-only metadata routes. http.client ignores environment proxies."""
    if (path, payload is None) not in {('/api/version', True), ('/api/tags', True), ('/api/show', False)}:
        raise ValueError('metadata route refused')
    if payload is not None:
        if not isinstance(payload, dict) or set(payload) != {'model'}:
            raise ValueError('metadata payload refused')
        local_model(payload['model'])
    parsed = urlsplit(local_endpoint(endpoint))
    number(timeout, 0.05, 5)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=timeout)
    body = None if payload is None else canonical(payload).encode()
    headers = {'Accept': 'application/json', 'Connection': 'close'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        connection.request('GET' if body is None else 'POST', path, body, headers)
        response = connection.getresponse()
        if response.status != 200:  # Includes redirects: no Location is followed.
            raise MetadataUnavailable('metadata_http_refused')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise MetadataUnavailable('metadata_encoding_refused')
        raw = response.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise MetadataUnavailable('metadata_too_large')
        return strict_json(raw.decode('utf-8'), max_bytes=MAX_METADATA_BYTES)
    except MetadataUnavailable:
        raise
    except (OSError, http.client.HTTPException):
        raise MetadataUnavailable('backend_unavailable') from None
    except (ValueError, UnicodeError):
        raise MetadataUnavailable('metadata_invalid_json') from None
    finally:
        connection.close()


def inspect_readiness(*, endpoint='http://127.0.0.1:11434', model, expected_digest=None, timeout=1.0):
    endpoint, model = local_endpoint(endpoint), local_model(model)
    expected = model_digest(expected_digest) if expected_digest is not None else None
    number(timeout, 0.05, 5)
    observations, requests = {}, []

    def get(path, payload=None):
        requests.append({'method': 'GET' if payload is None else 'POST', 'path': path, 'status': 'started'})
        value = _metadata_json(endpoint, path, payload, timeout)
        requests[-1].update(status='received', response_sha256=digest(value))
        return value

    status, reason = 'incompatible', 'invalid_metadata'
    try:
        version = get('/api/version')
        if not isinstance(version, dict):
            raise ValueError
        try:
            observations['server_version'] = server_version(version.get('version'))
        except ValueError:
            reason = 'unsupported_server_version'
            raise
        tags = get('/api/tags')
        if not isinstance(tags, dict) or not isinstance(tags.get('models'), list) or len(tags['models']) > 2048:
            raise ValueError
        if any(not isinstance(row, dict) for row in tags['models']):
            raise ValueError
        candidates = [row for row in tags['models'] if row.get('name') == model]
        reason = 'model_not_installed' if not candidates else 'ambiguous_model_metadata'
        if len(candidates) != 1:
            raise ValueError
        reason = 'invalid_metadata'
        row = candidates[0]
        if row.get('model', model) != model:
            raise ValueError
        observations['model_digest'] = model_digest(row.get('digest'))
        observations['digest_matches_expected'] = None if expected is None else expected == observations['model_digest']
        if expected is not None and not observations['digest_matches_expected']:
            reason = 'model_digest_mismatch'
            raise ValueError
        show = get('/api/show', {'model': model})
        if not isinstance(show, dict):
            raise ValueError
        # Custom aliases can point at paid cloud models despite a local-looking name.
        if any(key in show and show[key] != '' for key in ('remote_host', 'remote_model')):
            reason = 'remote_model_metadata_refused'
            raise ValueError
        capabilities = show.get('capabilities')
        if (not isinstance(capabilities, list) or len(capabilities) > 16
                or any(not isinstance(c, str) or not 1 <= len(c) <= 64 for c in capabilities)
                or len(capabilities) != len(set(capabilities))):
            raise ValueError
        observations['capabilities'] = sorted(capabilities)
        if 'decision' not in capabilities:
            reason = 'decision_capability_missing'
            raise ValueError
        status, reason = 'metadata_compatible', None
    except MetadataUnavailable as exc:
        status, reason = 'unavailable', str(exc)
        requests[-1]['status'] = 'failed'
    except (ValueError, TypeError):
        pass
    core = {'schema_version': 'ollama-decision-readiness-v1', 'origin': 'ollama_metadata_probe',
        'checked_at': datetime.now(timezone.utc).isoformat(), 'endpoint': endpoint,
        'requested_model': model, 'expected_digest': expected, 'status': status, 'reason_code': reason,
        'observations': observations, 'metadata_requests': requests,
        'metadata_request_count': len(requests), 'inference_requests': 0,
        'credentials_read': False, 'automatic_pull_or_start': False,
        'model_identity_assurance': 'server_metadata_declaration_only',
        'model_load_verified': False, 'live_access_verified': False,
        'live_execution_authorized': False, 'atomic_model_snapshot': False,
        'socket_timeout_seconds': timeout, 'hard_total_deadline_verified': False,
        'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return {**core, 'receipt_sha256': digest(core)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', default='http://127.0.0.1:11434')
    parser.add_argument('--model', required=True)
    parser.add_argument('--expected-digest')
    parser.add_argument('--timeout', type=float, default=1.0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    # Validate before touching the output; reserve it before any metadata request.
    local_endpoint(args.endpoint); local_model(args.model); number(args.timeout, 0.05, 5)
    if args.expected_digest is not None:
        model_digest(args.expected_digest)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(canonical({'schema_version': 'ollama-decision-readiness-started-v1', 'status': 'started'}))
        stream.flush()
        result = inspect_readiness(endpoint=args.endpoint, model=args.model,
            expected_digest=args.expected_digest, timeout=args.timeout)
        stream.seek(0); stream.truncate(); stream.write(canonical(result) + '\n')
    print('Local metadata readiness saved; no inference or model changes')
    return 0 if result['status'] == 'metadata_compatible' else 2


if __name__ == '__main__':
    raise SystemExit(main())
