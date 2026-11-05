"""Explicit one-article capture and verified offline development export.

Local durable bytes and extractor replay are verified. Publisher authenticity
beyond normal HTTPS, clock synchronization and feed completeness are not attested.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat

from cryptoforge import announcement_sources, llm_research_contracts, semantic_source_snapshot as snapshots
from cryptoforge import semantic_source_transport as transport, training_diagnostics
from cryptoforge.training_diagnostics import canonical, digest, exact_fields, timestamp
from cryptoforge.llm_research_contracts import strict_json


def _implementation():
    return {name: hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in {
        'collector':__file__, 'transport':transport.__file__, 'extractor':announcement_sources.__file__,
        'snapshot':snapshots.__file__, 'json':llm_research_contracts.__file__,
        'time_and_canonical':training_diagnostics.__file__}.items()}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def _write(directory, name, value):
    raw = value if isinstance(value, bytes) else (canonical(value)+'\n').encode()
    fd = os.open(directory/name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


def _read(directory, name, limit):
    fd = os.open(directory/name, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('bounded regular capture file required')
        return stream.read(limit+1)


def _json(directory, name, limit=128000):
    return strict_json(_read(directory,name,limit).decode(), max_bytes=limit)


def _seal(core, key):
    return {**core, key:digest(core)}


def _check(value, key, fields):
    exact_fields(value, fields | {key})
    if value[key] != digest({k:v for k,v in value.items() if k != key}):
        raise ValueError('capture checksum mismatch')


def _extract(raw, url):
    # The older parser is reused only after duplicate/nonfinite JSON validation.
    matches = re.findall(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', raw.decode('utf-8'), re.S)
    if len(matches) != 1:
        raise ValueError('one supported article data script required')
    strict_json(matches[0], max_bytes=transport.MAX_RAW_BYTES)
    article = announcement_sources.extract_article(raw)
    snapshots._text(article['title'],1024); snapshots._text(article['body'],32000)
    publication_raw = article['published_at']
    if not isinstance(publication_raw,str) or len(publication_raw.encode()) > 128:
        raise ValueError('bounded original publication metadata required')
    try: publication = timestamp(publication_raw).isoformat()
    except ValueError: publication = None
    return {'schema_version':'captured-source-article-v1', 'source_id':'bybit-announcements',
        'source_item_id':hashlib.sha256(url.encode()).hexdigest(), 'source_url':url,
        'title':article['title'], 'original_text':article['body'], 'published_at':publication,
        'source_publication_raw':publication_raw, 'source_revision':None, 'revised_at':None,
        'publication_time_status':'explicit_instant' if publication is not None else 'unknown_or_date_only',
        'revision_time_status':'not_extracted', 'item_identity_policy':'sha256_exact_source_url'}


REQUEST_FIELDS = {'schema_version','url','source_policy','implementation','started_at','waiting_deadline_seconds'}
RECEIPT_FIELDS = {'schema_version','request_sha256','status','reason_code','http_status',
                  'response_received_at','raw_bytes','raw_sha256','article_file_sha256','worker_launch_attempted'}
COMMIT_FIELDS = {'schema_version','receipt_sha256','status','recorded_at','clock_order_verified'}


def _finish(directory, request, receipt):
    receipt = _seal(receipt,'receipt_sha256')
    _write(directory,'receipt.json',receipt); _sync(directory)
    # This time is sampled AFTER raw/article/terminal receipt fsync+directory fsync.
    # The commit marker references those already durable bytes, not its own mtime.
    recorded = _now()
    clock_ok = timestamp(request['started_at']) <= timestamp(recorded)
    if receipt['response_received_at'] is not None:
        clock_ok &= timestamp(request['started_at']) <= timestamp(receipt['response_received_at']) <= timestamp(recorded)
    commit = _seal({'schema_version':'source-capture-commit-v1','receipt_sha256':receipt['receipt_sha256'],
        'status':receipt['status'] if clock_ok else 'failed', 'recorded_at':recorded,
        'clock_order_verified':bool(clock_ok)},'commit_sha256')
    _write(directory,'commit.json',commit); _sync(directory)
    return {'receipt':receipt,'commit':commit}


def capture(directory, *, url, policy):
    url = transport.article_url(url)
    policy = deepcopy(snapshots.validate_policy(policy))
    if 'bybit-announcements' not in policy['sources']:
        raise ValueError('registered Bybit announcement source required')
    snapshots._source_url(url,policy['sources']['bybit-announcements']['allowed_hosts'])
    before = _implementation()
    directory = Path(directory)
    directory.mkdir(mode=0o700) # Exclusive admission; existing/partial attempts never repeat GET.
    _sync(directory.parent)
    request = _seal({'schema_version':'source-capture-request-v1','url':url,'source_policy':policy,
        'implementation':before,'started_at':_now(),'waiting_deadline_seconds':15},'request_sha256')
    _write(directory,'request.json',request); _sync(directory)
    receipt = {'schema_version':'source-capture-receipt-v1','request_sha256':request['request_sha256'],
        'status':'failed','reason_code':None,'http_status':None,'response_received_at':None,
        'raw_bytes':None,'raw_sha256':None,'article_file_sha256':None,'worker_launch_attempted':True}
    try:
        raw = transport.fetch(url)
        if not isinstance(raw,bytes) or not 1 <= len(raw) <= transport.MAX_RAW_BYTES:
            raise ValueError('bounded raw article required')
        received = _now()
        receipt.update(response_received_at=received,http_status=200)
        if timestamp(received) < timestamp(request['started_at']):
            raise ValueError('clock moved backwards')
        receipt.update(raw_bytes=len(raw),raw_sha256=_write(directory,'raw.html',raw))
        article = _extract(raw,url)
        receipt['article_file_sha256'] = _write(directory,'article.json',article)
        if before != _implementation():
            raise ValueError('collector implementation changed')
        receipt['status'] = 'completed'
    except transport.FetchFailure as exc:
        receipt.update(status=exc.code if exc.code in {'timed_out','cancelled'} else 'failed',
                       reason_code=exc.code,http_status=exc.http_status)
    except KeyboardInterrupt:
        receipt.update(status='cancelled',reason_code='cancelled')
    except (ValueError,TypeError,KeyError,RecursionError,OSError):
        receipt['reason_code'] = 'capture_or_extraction_refused'
    return _finish(directory,request,receipt)


def read_capture(directory):
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('existing capture directory required')
    before = _implementation()
    request,receipt,commit = [_json(directory,name) for name in ('request.json','receipt.json','commit.json')]
    _check(request,'request_sha256',REQUEST_FIELDS); _check(receipt,'receipt_sha256',RECEIPT_FIELDS)
    _check(commit,'commit_sha256',COMMIT_FIELDS)
    if (request['schema_version'] != 'source-capture-request-v1'
            or receipt['schema_version'] != 'source-capture-receipt-v1'
            or commit['schema_version'] != 'source-capture-commit-v1'
            or request['implementation'] != before or request['waiting_deadline_seconds'] != 15
            or receipt['request_sha256'] != request['request_sha256']
            or commit['receipt_sha256'] != receipt['receipt_sha256']
            or receipt['status'] != 'completed' or receipt['reason_code'] is not None
            or receipt['http_status'] != 200 or receipt['worker_launch_attempted'] is not True
            or commit['status'] != 'completed' or commit['clock_order_verified'] is not True):
        raise ValueError('completed current-implementation capture required')
    url = transport.article_url(request['url'])
    policy = snapshots.validate_policy(request['source_policy'])
    raw = _read(directory,'raw.html',transport.MAX_RAW_BYTES)
    article_raw = _read(directory,'article.json',128000)
    if (type(receipt['raw_bytes']) is not int or receipt['raw_bytes'] != len(raw)
            or receipt['raw_sha256'] != hashlib.sha256(raw).hexdigest()
            or receipt['article_file_sha256'] != hashlib.sha256(article_raw).hexdigest()):
        raise ValueError('raw/article bytes differ from committed capture')
    article = strict_json(article_raw.decode(),max_bytes=128000)
    if article != _extract(raw,url):
        raise ValueError('article extraction replay mismatch')
    received,recorded = receipt['response_received_at'],commit['recorded_at']
    if not timestamp(request['started_at']) <= timestamp(received) <= timestamp(recorded):
        raise ValueError('capture clock order invalid')
    row = {k:article[k] for k in ('source_id','source_item_id','source_url','title','original_text',
                                   'published_at','source_revision','revised_at')}
    row.update(first_seen_at=received,received_at=received,recorded_at=recorded,capture_sha256=receipt['raw_sha256'])
    snapshots._normalize(row,policy)
    if before != _implementation():
        raise ValueError('implementation changed during capture verification')
    return {'row':row,'source_policy':policy,'raw_bytes':len(raw),'evidence':{
        'request_sha256':request['request_sha256'],'receipt_sha256':receipt['receipt_sha256'],
        'commit_sha256':commit['commit_sha256'],'raw_sha256':receipt['raw_sha256']}}


def export_captures(directories):
    if not isinstance(directories,list) or not 1 <= len(directories) <= 32:
        raise ValueError('one to 32 explicit captures required')
    verified,raw_total,policy = [],0,None
    for path in directories:
        item = read_capture(path); raw_total += item['raw_bytes']
        if raw_total > 16_000_000:
            raise ValueError('capture batch raw-byte limit exceeded')
        if policy is not None and policy != item['source_policy']:
            raise ValueError('one unchanged source policy per export required')
        policy = item['source_policy']; verified.append(item)
    export = {'schema_version':'semantic-source-export-v1','origin':'collector_export',
              'partition':'development','observations':[v['row'] for v in verified]}
    snapshots.build_snapshot(export,policy) # Validate all existing source-contract bounds before writing.
    audit = _seal({'schema_version':'verified-source-export-v1','export_sha256':digest(export),
        'source_policy_sha256':digest(policy),'captures':[v['evidence'] for v in verified],
        'raw_artifacts_verified':True,'extractor_replay_verified':True,
        'clock_synchronization_attested':False,'source_coverage_verified':False,
        'upstream_development_lineage_verified':False,'semantic_labels_created':False,
        'assurance':'local_bytes_and_extractor_replay_not_publisher_or_clock_attestation'},'verification_sha256')
    return export,audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command',required=True)
    collect = commands.add_parser('capture'); collect.add_argument('--directory',type=Path,required=True)
    collect.add_argument('--url',required=True); collect.add_argument('--policy',type=Path,required=True)
    export = commands.add_parser('export'); export.add_argument('--capture',type=Path,action='append',required=True)
    export.add_argument('--directory',type=Path,required=True)
    args = parser.parse_args(argv)
    if args.command == 'capture':
        policy = snapshots._read(args.policy,32000)
        result = capture(args.directory,url=args.url,policy=policy)
        print('Source capture: '+result['commit']['status']+'; no LLM or training')
        return 0 if result['commit']['status'] == 'completed' else 2
    data,audit = export_captures(args.capture)
    args.directory.mkdir(mode=0o700)
    _write(args.directory,'export.json',data); _write(args.directory,'verification.json',audit)
    _sync(args.directory); _sync(args.directory.parent)
    print('Verified development export saved; no network, LLM or training')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
