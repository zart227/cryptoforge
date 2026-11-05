"""One bounded credential-free HTTPS GET in a fixed supervised worker."""
import base64
import hashlib
import http.client
import os
from pathlib import Path
import re
import resource
import signal
import ssl
import subprocess
import sys
import time
from urllib.parse import urlsplit

from cryptoforge.llm_research_contracts import strict_json
from cryptoforge.training_diagnostics import canonical


MAX_RAW_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 2_800_000


def article_url(value):
    if not isinstance(value, str) or len(value) > 2048 or not value.isascii():
        raise ValueError('explicit official article URL required')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.netloc != 'announcements.bybit.com'
            or not re.fullmatch(r'/en/article/[A-Za-z0-9_-]{1,500}/', parsed.path)
            or parsed.query or parsed.fragment):
        raise ValueError('explicit official English article URL required; no redirects')
    return value


class FetchFailure(RuntimeError):
    def __init__(self, code, *, status=None):
        super().__init__(code)
        self.code, self.http_status = code, status


def _get(url):
    parsed = urlsplit(article_url(url))
    connection = http.client.HTTPSConnection(parsed.hostname, 443, timeout=5,
                                             context=ssl.create_default_context())
    try:
        connection.request('GET', parsed.path, headers={'User-Agent':'CryptoForge development-source-capture/1',
            'Accept':'text/html', 'Accept-Encoding':'identity', 'Connection':'close'})
        response = connection.getresponse()
        if response.status != 200:
            raise FetchFailure('http_status_refused', status=response.status)
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise FetchFailure('encoded_body_refused', status=200)
        if response.getheader('Content-Type', '').split(';')[0].strip().lower() not in {
                'text/html', 'application/xhtml+xml'}:
            raise FetchFailure('html_content_type_required', status=200)
        raw = response.read(MAX_RAW_BYTES + 1)
        if not raw or len(raw) > MAX_RAW_BYTES:
            raise FetchFailure('raw_body_size_refused', status=200)
        return raw
    except (OSError, http.client.HTTPException):
        raise FetchFailure('network_unavailable') from None
    finally:
        connection.close()


def _worker():
    try:
        request = strict_json(sys.stdin.buffer.read(4097).decode(), max_bytes=4096)
        if not isinstance(request, dict) or set(request) != {'url', 'implementation_sha256'}:
            raise ValueError
        if request['implementation_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
            raise ValueError
        url = article_url(request['url'])
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_AS, (128*1024**2, 128*1024**2))
        os.nice(10)
        signal.signal(signal.SIGALRM, signal.SIG_DFL); signal.setitimer(signal.ITIMER_REAL, 15)
        raw = _get(url)
        result = {'status':'received', 'http_status':200, 'raw_base64':base64.b64encode(raw).decode('ascii')}
    except FetchFailure as exc:
        result = {'status':'failed', 'reason_code':exc.code, 'http_status':exc.http_status}
    except Exception:
        result = {'status':'failed', 'reason_code':'worker_input_or_runtime_refused', 'http_status':None}
    sys.stdout.write(canonical(result))
    return 0


def fetch(url, *, wait_seconds=15):
    article_url(url)
    if type(wait_seconds) not in (int, float) or not 0.05 <= wait_seconds <= 15:
        raise ValueError('bounded collector waiting deadline required')
    before = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    request = canonical({'url':url, 'implementation_sha256':before}).encode()
    env = {'PATH':os.defpath, 'LANG':'C.UTF-8', 'PYTHONPATH':str(Path(__file__).resolve().parents[1]),
           'PYTHONDONTWRITEBYTECODE':'1'}
    start = time.monotonic()
    process = subprocess.Popen([sys.executable, '-m', 'cryptoforge.semantic_source_transport', '_worker'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    try:
        try:
            remaining = max(0.001, wait_seconds-(time.monotonic()-start))
            stdout, _ = process.communicate(request, timeout=remaining)
        except subprocess.TimeoutExpired:
            raise FetchFailure('timed_out') from None
        except KeyboardInterrupt:
            raise FetchFailure('cancelled') from None
    finally:
        if process.poll() is None:
            process.kill()
            try: process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                raise FetchFailure('worker_cleanup_unconfirmed') from None
    if process.returncode != 0 or len(stdout) > MAX_OUTPUT_BYTES:
        raise FetchFailure('worker_failed')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != before:
        raise FetchFailure('implementation_changed')
    try:
        result = strict_json(stdout.decode(), max_bytes=MAX_OUTPUT_BYTES)
        if result.get('status') == 'failed':
            if set(result) != {'status','reason_code','http_status'}:
                raise ValueError
            if result.get('reason_code') not in {'http_status_refused','encoded_body_refused',
                'html_content_type_required','raw_body_size_refused','network_unavailable','worker_input_or_runtime_refused'}:
                raise ValueError
            status = result.get('http_status')
            if status is not None and (type(status) is not int or not 100 <= status <= 599):
                raise ValueError
            raise FetchFailure(result['reason_code'], status=status)
        if set(result) != {'status','http_status','raw_base64'} or result['status'] != 'received' or result['http_status'] != 200:
            raise ValueError
        raw = base64.b64decode(result['raw_base64'], validate=True)
        if not 1 <= len(raw) <= MAX_RAW_BYTES:
            raise ValueError
        if time.monotonic()-start > wait_seconds:
            raise FetchFailure('timed_out')
        return raw
    except (ValueError, TypeError, AttributeError, UnicodeError):
        raise FetchFailure('invalid_worker_output') from None


if __name__ == '__main__':
    if sys.argv[1:] != ['_worker']:
        raise SystemExit('internal fixed source worker only')
    raise SystemExit(_worker())
