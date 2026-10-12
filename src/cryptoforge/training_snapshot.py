"""Private, content-addressed inputs for primary-model audit and reproduction."""
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import inspect,platform,sys

SCHEMA_VERSION='primary-training-input-snapshot-v1'
MAX_UNCOMPRESSED_BYTES=128*1024*1024


def _save_raw(directory,raw):
    if len(raw)>MAX_UNCOMPRESSED_BYTES:raise ValueError('primary training snapshot size limit exceeded')
    digest=hashlib.sha256(raw).hexdigest();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/(digest+'.json.gz')
    if path.exists():
        with gzip.open(path,'rb') as stream:existing=stream.read(len(raw)+1)
        if existing!=raw:raise ValueError('existing training snapshot differs from content address')
        path.chmod(0o600)
    else:
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=directory,delete=False) as stream:
                temporary=Path(stream.name);stream.write(gzip.compress(raw,mtime=0))
                stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
    return {'path':str(path.resolve()),'sha256':digest,'compression':'gzip','uncompressed_bytes':len(raw)}


def save_runtime_sources(directory,functions,expected_hashes):
    sources={}
    for name,function in functions.items():
        path=function if isinstance(function,Path) else Path(inspect.getfile(function));raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if sha!=expected_hashes.get(name):raise ValueError('primary source changed before runtime capture')
        sources[name]={'module_filename':path.name,'sha256':sha,'source_utf8':raw.decode('utf-8')}
    payload={'schema_version':'primary-runtime-sources-v1','sources':sources,
        'python_version':list(sys.version_info[:3]),'python_implementation':platform.python_implementation(),
        'machine':platform.machine(),'automatically_execute_archived_code':False}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    return {'schema_version':payload['schema_version'],**_save_raw(directory,raw)}


def load_runtime_sources(reference,expected_hashes):
    if reference.get('schema_version')!='primary-runtime-sources-v1' or reference.get('compression')!='gzip':raise ValueError('supported primary source bundle required')
    size=reference.get('uncompressed_bytes')
    if type(size) is not int or not 0<size<=MAX_UNCOMPRESSED_BYTES:raise ValueError('bounded primary runtime size required')
    with gzip.open(reference['path'],'rb') as stream:raw=stream.read(size+1)
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('primary source bundle checksum mismatch')
    payload=json.loads(raw)
    actual={name:hashlib.sha256(record['source_utf8'].encode()).hexdigest() for name,record in payload['sources'].items()}
    if payload.get('schema_version')!=reference['schema_version'] or payload.get('automatically_execute_archived_code') is not False or actual!=expected_hashes or any(
        actual[name]!=record['sha256'] for name,record in payload['sources'].items()):
        raise ValueError('primary source bundle differs from fitted implementation')
    return payload


def save_training_snapshot(directory,*,splits,metadata):
    if set(splits)!={'train','validation','test'} or any(not rows for rows in splits.values()):
        raise ValueError('three nonempty primary input splits required')
    rows={split:[{**asdict(row),'open_time':row.open_time.isoformat(),
        'label_end_time':row.label_end_time.isoformat() if row.label_end_time is not None else None}
        for row in values] for split,values in splits.items()}
    payload={'schema_version':SCHEMA_VERSION,'metadata':metadata,'splits':rows,
        'target_version':'fixed-future-return-v1','source_kind':'historical_candle_primary_examples',
        'counts_as_real_executed_buys':False}
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    return {'schema_version':SCHEMA_VERSION,**_save_raw(directory,raw),
            'split_counts':{split:len(values) for split,values in splits.items()}}


def load_training_snapshot(reference):
    if reference.get('schema_version')!=SCHEMA_VERSION or reference.get('compression')!='gzip':
        raise ValueError('supported training snapshot reference required')
    size=reference.get('uncompressed_bytes')
    if type(size) is not int or not 0<size<=MAX_UNCOMPRESSED_BYTES:
        raise ValueError('bounded training snapshot size required')
    with gzip.open(reference['path'],'rb') as stream:raw=stream.read(size+1)
    if len(raw)!=reference['uncompressed_bytes'] or hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('training snapshot checksum mismatch')
    payload=json.loads(raw)
    if payload.get('schema_version')!=SCHEMA_VERSION or set(payload.get('splits',{}))!={'train','validation','test'}:
        raise ValueError('training snapshot schema mismatch')
    if {key:len(rows) for key,rows in payload['splits'].items()}!=reference['split_counts']:
        raise ValueError('training snapshot split counts differ')
    return payload
