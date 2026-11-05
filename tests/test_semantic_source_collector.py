from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time

import pytest

from cryptoforge import semantic_source_collector as collector
from cryptoforge import semantic_source_transport as transport
from cryptoforge import semantic_source_snapshot as snapshots
from cryptoforge.research_training_diagnostics import canonical, digest


URL = 'https://announcements.bybit.com/en/article/synthetic-notice/'
T0,T1,T2 = ['2026-10-18T10:0'+str(i)+':00+00:00' for i in range(3)]


def html(*, date='2026-08-05', body='SYNTHETIC withdrawal notice; no trade outcome asserted.'):
    data = {'props':{'pageProps':{'articleDetail':{'title':'SYNTHETIC notice','date':date,
        'content':{'json':{'text':body}}}}}}
    return ('<html><script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script></html>').encode()


@pytest.fixture
def policy():
    return json.loads((Path(__file__).resolve().parents[1]/'config/semantic-source-policy-v1.json').read_text())


@pytest.fixture
def captured(tmp_path,monkeypatch,policy):
    raw = html(); calls = []
    def fetch(url): calls.append(url); return raw
    monkeypatch.setattr(transport,'fetch',fetch)
    times = iter([T0,T1,T2]); monkeypatch.setattr(collector,'_now',lambda:next(times))
    directory = tmp_path/'capture'
    result = collector.capture(directory,url=URL,policy=policy)
    return directory,result,raw,calls


def test_capture_durable_raw_replay_and_conservative_asof(captured):
    directory,result,raw,calls = captured
    assert result['commit']['status'] == 'completed' and calls == [URL]
    assert directory.stat().st_mode & 0o777 == 0o700
    for p in directory.iterdir(): assert p.stat().st_mode & 0o777 == 0o600
    assert (directory/'raw.html').read_bytes() == raw
    verified = collector.read_capture(directory)
    assert verified['row']['first_seen_at'] == verified['row']['received_at'] == T1
    assert verified['row']['recorded_at'] == T2 and verified['row']['published_at'] is None
    assert verified['row']['capture_sha256'] == hashlib.sha256(raw).hexdigest()
    export,audit = collector.export_captures([directory])
    assert export['origin'] == 'collector_export' and audit['raw_artifacts_verified']
    assert audit['extractor_replay_verified'] and not audit['clock_synchronization_attested']
    assert not audit['source_coverage_verified'] and not audit['upstream_development_lineage_verified']
    snap = snapshots.build_snapshot(export,verified['source_policy'])
    assert snapshots.as_of(snap,decision_time=T1,ttl_seconds=600)['model_state'] == {'texts':[]}
    assert len(snapshots.as_of(snap,decision_time=T2,ttl_seconds=600)['model_state']['texts']) == 1
    assert calls == [URL] # all verification/export/snapshot work is offline


def test_recorded_clock_sample_is_after_all_payloads_and_receipt_are_durable(tmp_path,monkeypatch,policy):
    directory = tmp_path/'capture'; times = iter([T0,T1,T2]); synced = []
    original = collector._sync
    def sync(path): synced.append(Path(path)); original(path)
    def now():
        value = next(times)
        if value == T2:
            assert all((directory/name).is_file() for name in ['raw.html','article.json','receipt.json'])
            assert synced[-1] == directory
        return value
    monkeypatch.setattr(collector,'_sync',sync); monkeypatch.setattr(collector,'_now',now)
    monkeypatch.setattr(transport,'fetch',lambda url:html())
    assert collector.capture(directory,url=URL,policy=policy)['commit']['recorded_at'] == T2


def test_existing_or_partial_capture_never_repeats_request(captured,policy,tmp_path):
    directory,_,_,calls = captured
    with pytest.raises(FileExistsError): collector.capture(directory,url=URL,policy=policy)
    partial = tmp_path/'partial'; partial.mkdir()
    with pytest.raises(FileExistsError): collector.capture(partial,url=URL,policy=policy)
    assert calls == [URL]
    with pytest.raises(FileNotFoundError): collector.read_capture(partial)


@pytest.mark.parametrize('code,status', [('network_unavailable','failed'),('http_status_refused','failed'),
                                      ('timed_out','timed_out'),('cancelled','cancelled')])
def test_failures_preserve_terminal_receipts_but_never_export(tmp_path,monkeypatch,policy,code,status):
    def fail(url): raise transport.FetchFailure(code,status=302 if code=='http_status_refused' else None)
    monkeypatch.setattr(transport,'fetch',fail)
    result = collector.capture(tmp_path/'attempt',url=URL,policy=policy)
    assert result['commit']['status'] == status and result['receipt']['reason_code'] == code
    assert result['receipt']['raw_bytes'] is None and result['receipt']['response_received_at'] is None
    with pytest.raises(ValueError): collector.export_captures([tmp_path/'attempt'])


@pytest.mark.parametrize('raw', [b'not supported HTML',html(body=' '),b'x'*2_000_001,
    b'<script id="__NEXT_DATA__">{"props":1,"props":2}</script>'])
def test_unusable_body_not_replaced_by_empty_or_truncated_text(tmp_path,monkeypatch,policy,raw):
    monkeypatch.setattr(transport,'fetch',lambda url:raw)
    result = collector.capture(tmp_path/'attempt',url=URL,policy=policy)
    assert result['commit']['status'] == 'failed'
    with pytest.raises(ValueError): collector.read_capture(tmp_path/'attempt')


@pytest.mark.parametrize('times', [[T1,T0,T2],[T0,T2,T1]])
def test_backward_wall_clock_refuses_export(tmp_path,monkeypatch,policy,times):
    clock = iter(times); monkeypatch.setattr(collector,'_now',lambda:next(clock))
    monkeypatch.setattr(transport,'fetch',lambda url:html())
    result = collector.capture(tmp_path/'attempt',url=URL,policy=policy)
    assert result['commit']['status'] == 'failed'
    with pytest.raises(ValueError): collector.read_capture(tmp_path/'attempt')


@pytest.mark.parametrize('name', ['request.json','receipt.json','commit.json','article.json','raw.html'])
def test_tampered_file_cannot_export(captured,name):
    directory,_,_,_ = captured
    (directory/name).write_bytes((directory/name).read_bytes()+b'X')
    with pytest.raises(ValueError): collector.read_capture(directory)


def test_symlink_capture_file_is_refused(captured,tmp_path):
    directory,_,raw,_ = captured
    (directory/'raw.html').unlink(); other = tmp_path/'outside.html'; other.write_bytes(raw)
    (directory/'raw.html').symlink_to(other)
    with pytest.raises(OSError): collector.read_capture(directory)


def test_extractor_replay_catches_rehashed_text_override(captured):
    directory,_,_,_ = captured
    article = json.loads((directory/'article.json').read_text()); article['original_text'] = 'SYNTHETIC forged body'
    (directory/'article.json').write_text(canonical(article)+'\n')
    receipt = json.loads((directory/'receipt.json').read_text())
    receipt['article_file_sha256'] = hashlib.sha256((directory/'article.json').read_bytes()).hexdigest()
    receipt['receipt_sha256'] = digest({k:v for k,v in receipt.items() if k != 'receipt_sha256'})
    (directory/'receipt.json').write_text(canonical(receipt)+'\n')
    commit = json.loads((directory/'commit.json').read_text()); commit['receipt_sha256'] = receipt['receipt_sha256']
    commit['commit_sha256'] = digest({k:v for k,v in commit.items() if k != 'commit_sha256'})
    (directory/'commit.json').write_text(canonical(commit)+'\n')
    with pytest.raises(ValueError,match='replay'): collector.read_capture(directory)


def test_old_implementation_capture_is_refused_without_network(captured,monkeypatch):
    directory,_,_,calls = captured
    changed = collector._implementation(); changed['extractor'] = 'f'*64
    monkeypatch.setattr(collector,'_implementation',lambda:changed)
    with pytest.raises(ValueError): collector.read_capture(directory)
    assert calls == [URL]


@pytest.mark.parametrize('url', ['http://announcements.bybit.com/en/article/x/',
    'https://announcements.bybit.global/en/article/x/','https://announcements.bybit.com/en/',
    URL+'?token=secret', URL+'#x','https://u:p@announcements.bybit.com/en/article/x/',
    'https://announcements.bybit.com:443/en/article/x/','https://announcements.bybit.com/en/article/x/\n'])
def test_unsupported_urls_refused_before_directory_or_worker(tmp_path,policy,monkeypatch,url):
    def forbidden(*a,**k): raise AssertionError('worker must not start')
    monkeypatch.setattr(transport,'fetch',forbidden)
    with pytest.raises(ValueError): collector.capture(tmp_path/'capture',url=url,policy=policy)
    assert not (tmp_path/'capture').exists()


def test_offline_export_cli_private_and_no_mutation(captured,tmp_path,monkeypatch):
    directory,_,_,_ = captured
    before = {p.name:p.read_bytes() for p in directory.iterdir()}
    def forbidden(*a,**k): raise AssertionError('network/process execution refused')
    monkeypatch.setattr(socket,'socket',forbidden); monkeypatch.setattr(subprocess,'Popen',forbidden)
    output = tmp_path/'export'
    assert collector.main(['export','--capture',str(directory),'--directory',str(output)]) == 0
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir())
    with pytest.raises(FileExistsError): collector.main(['export','--capture',str(directory),'--directory',str(output)])
    assert {p.name:p.read_bytes() for p in directory.iterdir()} == before


class Response:
    def __init__(self,status=200,headers=None,raw=b'SYNTHETIC html'):
        self.status,self.headers,self.raw = status,headers or {'Content-Type':'text/html; charset=utf-8'},raw
    def getheader(self,key,default=''): return self.headers.get(key,default)
    def read(self,limit): self.limit = limit; return self.raw[:limit]


@pytest.mark.parametrize('kind,code', [('redirect','http_status_refused'),('gzip','encoded_body_refused'),
    ('json','html_content_type_required'),('large','raw_body_size_refused'),('empty','raw_body_size_refused')])
def test_https_contract_rejects_redirect_encoding_type_and_size(monkeypatch,kind,code):
    response = Response(); calls = []
    if kind == 'redirect': response.status = 302
    elif kind == 'gzip': response.headers['Content-Encoding'] = 'gzip'
    elif kind == 'json': response.headers['Content-Type'] = 'application/json'
    elif kind == 'large': response.raw = b'x'*2_000_001
    else: response.raw = b''
    class Connection:
        def __init__(self,host,port,timeout,context):
            assert host == 'announcements.bybit.com' and port == 443 and timeout == 5
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        def request(self,*args,**kwargs): calls.append((args,kwargs))
        def getresponse(self): return response
        def close(self): calls.append('closed')
    monkeypatch.setattr(transport.http.client,'HTTPSConnection',Connection)
    with pytest.raises(transport.FetchFailure) as exc: transport._get(URL)
    assert exc.value.code == code and len(calls) == 2 # one GET, close; no redirect follow
    headers = calls[0][1]['headers']
    assert headers['Accept-Encoding'] == 'identity' and not any(k.lower() in {'authorization','cookie'} for k in headers)


def test_parent_timeout_kills_and_reaps_real_process_with_minimal_environment(monkeypatch):
    actual = subprocess.Popen; children = []
    def sleeping_worker(argv,**kwargs):
        assert argv[-2:] == ['cryptoforge.semantic_source_transport','_worker']
        assert set(kwargs['env']) == {'PATH','LANG','PYTHONPATH','PYTHONDONTWRITEBYTECODE'}
        p = actual([sys.executable,'-c','import time; time.sleep(10)'],**kwargs); children.append(p); return p
    monkeypatch.setattr(transport.subprocess,'Popen',sleeping_worker)
    start = time.monotonic()
    with pytest.raises(transport.FetchFailure,match='timed_out'): transport.fetch(URL,wait_seconds=0.15)
    assert time.monotonic()-start < 3 and len(children) == 1 and children[0].poll() is not None


def test_actual_fixed_worker_validates_private_input_without_network():
    env = {'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONPATH':str(Path(transport.__file__).resolve().parents[1]),
           'PYTHONDONTWRITEBYTECODE':'1'}
    request = {'url':'https://unsupported.invalid/','implementation_sha256':hashlib.sha256(Path(transport.__file__).read_bytes()).hexdigest()}
    result = subprocess.run([sys.executable,'-m','cryptoforge.semantic_source_transport','_worker'],
        input=canonical(request).encode(),capture_output=True,env=env,timeout=3)
    assert result.returncode == 0
    assert json.loads(result.stdout)['reason_code'] == 'worker_input_or_runtime_refused'
