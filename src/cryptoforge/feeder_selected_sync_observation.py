"""Bounded local REST observation for an incomplete selected-sync stage.

Current timestamps and rows are not historical execution or attribution proof.
No write, retry, stage invocation, external network or secret appears in report.
"""
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import re
from time import monotonic
from urllib import parse, request

from cryptoforge.feeder_incomplete_inspection import inspect_incomplete_feeder
from cryptoforge.local_source_provenance import digest, parse as parse_json, read_file, stamp


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def local_getter(url,key,*,timeout=3,maximum_response_bytes=65536):
    """Construct a GET-only client bound to one HTTP loopback origin."""
    parsed=parse.urlsplit(url)
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','::1') or
            parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/') or not key):
        raise ValueError('local loopback REST origin required')
    origin=url.rstrip('/');opener=request.build_opener(request.ProxyHandler({}),_NoRedirect())
    def get(table,query):
        if table not in ('market_tickers','market_candles','bot_health'):raise ValueError('read-only table allowlist')
        endpoint=origin+'/rest/v1/'+table+'?'+parse.urlencode(query)
        req=request.Request(endpoint,headers={'apikey':key,'Authorization':'Bearer '+key},method='GET')
        with opener.open(req,timeout=timeout) as response:
            if response.status!=200:raise ValueError('local REST read failed')
            raw=response.read(maximum_response_bytes+1)
        if len(raw)>maximum_response_bytes:raise ValueError('REST response byte limit')
        value=parse_json(raw)
        if not isinstance(value,list) or len(value)>1:raise ValueError('bounded REST row response required')
        return value,hashlib.sha256(raw).hexdigest()
    return get


def observe_selected_sync(reference,cycle,*,get,clock=None,maximum_seconds=60):
    if type(maximum_seconds) is not int or not 1<=maximum_seconds<=120:raise ValueError('bounded observation time required')
    clock=clock or (lambda:datetime.now(UTC));started=stamp(clock());deadline=monotonic()+maximum_seconds
    original=inspect_incomplete_feeder(reference,cycle,clock=clock)
    if original['first_missing_stage']!='selected_sync' or original['effect']!='unknown_stage_effect':
        raise ValueError('incomplete selected-sync stage required')
    folder=Path(reference['root'])/'cycles'/cycle
    raw=read_file(folder/'run/selected-universe.json',maximum=65536)
    if digest(raw)!=original['retained_files']['run/selected-universe.json']['sha256']:
        raise ValueError('original selected universe changed')
    selected=parse_json(raw);pairs=selected['pairs']
    if (set(selected)!={'pairs'} or not isinstance(pairs,list) or not 1<=len(pairs)<=20 or
            len(set(pairs))!=len(pairs) or any(not isinstance(x,str) or not re.fullmatch('[A-Z0-9]{1,24}/USDT',x) for x in pairs)):
        raise ValueError('original bounded pair selection required')
    results=[]
    def fetch(table,query):
        if monotonic()>deadline:raise TimeoutError('selected-sync observation deadline')
        rows,sha=get(table,query)
        if not isinstance(rows,list) or len(rows)>1 or not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):
            raise ValueError('bounded local observation required')
        return {'rows':rows,'response_sha256':sha}
    for pair in pairs:
        symbol=pair.replace('/','')
        ticker=fetch('market_tickers',{'symbol':'eq.'+symbol,'exchange':'eq.bybit','market_type':'eq.spot',
                     'select':'pair,symbol,observed_at,updated_at','limit':'1'})
        candle=fetch('market_candles',{'symbol':'eq.'+symbol,'exchange':'eq.bybit','market_type':'eq.spot',
                     'timeframe':'eq.5m','close_time':'lte.'+started.isoformat(),'select':'pair,symbol,timeframe,open_time,close_time,ingested_at,updated_at',
                     'order':'open_time.desc','limit':'1'})
        for row in ticker['rows']+candle['rows']:
            if not isinstance(row,dict) or row.get('pair')!=pair or row.get('symbol')!=symbol:
                raise ValueError('REST row identity differs')
        if ticker['rows']:
            row=ticker['rows'][0]
            if set(row)!={'pair','symbol','observed_at','updated_at'}:raise ValueError('unexpected ticker fields')
            stamp(row['observed_at']);stamp(row['updated_at'])
        if candle['rows']:
            row=candle['rows'][0]
            if set(row)!={'pair','symbol','timeframe','open_time','close_time','ingested_at','updated_at'}:
                raise ValueError('unexpected candle fields')
            if (row.get('timeframe')!='5m' or stamp(row['close_time'])>started or
                    stamp(row['close_time'])-stamp(row['open_time'])!=timedelta(minutes=5)):
                raise ValueError('REST candle not closed at observation')
            stamp(row['ingested_at']);stamp(row['updated_at'])
        results.append({'pair':pair,'ticker':ticker,'latest_closed_candle':candle})
    health=fetch('bot_health',{'component':'eq.supabase_market_sync','select':'component,status,observed_at','limit':'1'})
    if health['rows']:
        row=health['rows'][0]
        if not isinstance(row,dict) or set(row)!={'component','status','observed_at'} or row['component']!='supabase_market_sync':
            raise ValueError('health identity differs')
        stamp(row['observed_at'])
    final=inspect_incomplete_feeder(reference,cycle,clock=clock)
    if (original['retained_files']!=final['retained_files'] or final['first_missing_stage']!='selected_sync' or
            final['effect']!='unknown_stage_effect'):raise ValueError('incomplete cycle changed during observation')
    if monotonic()>deadline:raise TimeoutError('selected-sync observation deadline')
    completed=stamp(clock())
    if completed<started:raise ValueError('observation clock moved backwards')
    return {'schema_version':'feeder-selected-sync-current-observation-v1','started_at':started.isoformat(),
            'completed_at':completed.isoformat(),'cycle':cycle,'selected_pairs_sha256':digest(raw),
            'observations':results,'bot_health':health,'local_rest_requests':len(pairs)*2+1,
            'database_instance_binding_proved':False,'historical_stage_execution_proved':False,
            'historical_effect':'unknown','competing_writers_excluded':False,'retry_authorized':False,
            'database_modified':False,'scope':'current bounded local REST observations only; not historical stage attribution'}
