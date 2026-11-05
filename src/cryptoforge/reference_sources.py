"""Credential-free, bounded Bybit Spot reference observations, independent of ranking."""
from datetime import UTC, datetime
from decimal import Decimal
import base64
import math
import re
from time import monotonic
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from cryptoforge.local_source_provenance import canonical, digest, parse, stamp

ORIGIN = 'https://api.bybit.com'
MANDATORY = ('BTC/USDT', 'ETH/USDT')
INTERVAL_MS = 300000
MAX_RESPONSE_BYTES = 65536
TIMEOUT_SECONDS = 3
NUMERIC = re.compile(r'(0|[1-9][0-9]{0,19})(\.[0-9]{1,24})?')


def source_pairs(pairs):
    if type(pairs) not in (list, tuple) or len(pairs) > 18:
        raise ValueError('bounded fixed source pair list required')
    for pair in pairs:
        if type(pair) is not str or not re.fullmatch('[A-Z0-9]{1,24}/USDT', pair):
            raise ValueError('explicit Spot USDT source pair required')
    return sorted(set(MANDATORY) | set(pairs))


def request_url(pair, anchor_ms):
    source_pairs([pair])
    if type(anchor_ms) is not int or anchor_ms <= INTERVAL_MS or anchor_ms % INTERVAL_MS:
        raise ValueError('closed UTC source anchor required')
    return ORIGIN + '/v5/market/kline?' + urlencode(dict(category='spot', symbol=pair.replace('/', ''),
        interval='5', limit='120', end=str(anchor_ms-INTERVAL_MS)))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, 'reference redirects prohibited', headers, fp)


def _fetch_once(pair, anchor_ms):
    url=request_url(pair,anchor_ms)
    prepared=datetime.now(UTC);started=monotonic();status=None;error=None;body=b''
    try:
        request=Request(url,headers={'User-Agent':'CryptoForge-reference-source/1','Accept':'application/json'})
        with build_opener(_NoRedirect()).open(request,timeout=TIMEOUT_SECONDS) as response:
            status=response.status
            body=response.read(MAX_RESPONSE_BYTES+1)
            if len(body)>MAX_RESPONSE_BYTES:
                body=body[:MAX_RESPONSE_BYTES];error='response_byte_budget'
    except HTTPError as exc:
        status=exc.code
        try:
            try:body=exc.read(MAX_RESPONSE_BYTES)
            except Exception:body=b''
        finally:exc.close()
        error='http_error'
    except Exception as exc:
        # Exception text can contain proxy/OS details. Retain a bounded type.
        error=type(exc).__name__
    completed=datetime.now(UTC);elapsed=monotonic()-started
    if completed<prepared or elapsed>TIMEOUT_SECONDS+2:error='request_clock_or_wall_budget'
    return dict(pair=pair,anchor_ms=anchor_ms,url=url,prepared_at=prepared.isoformat(),
                completed_at=completed.isoformat(),elapsed_seconds=elapsed,
                http_status=status,error_type=error,raw_body_base64=base64.b64encode(body).decode(),raw_body_sha256=digest(body))


class PublicReferenceClient:
    """One GET in a killable child: no credentials, redirects or blind retries."""
    def fetch(self,pair,anchor_ms):
        from cryptoforge.local_source_observer import bounded_process
        url=request_url(pair,anchor_ms);prepared=datetime.now(UTC);started=monotonic()
        code="import json,sys;sys.path.insert(0,sys.argv[1]);from cryptoforge.reference_sources import _fetch_once;print(json.dumps(_fetch_once(sys.argv[2],int(sys.argv[3]))))"
        command=[sys.executable,'-c',code,str(Path(__file__).resolve().parents[1]),pair,str(anchor_ms)]
        try:
            raw=bounded_process(command,'',maximum_bytes=128*1024,maximum_seconds=5)
            return parse(raw)
        except Exception:
            return dict(pair=pair,anchor_ms=anchor_ms,url=url,prepared_at=prepared.isoformat(),
                completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=monotonic()-started,
                http_status=None,error_type='bounded_transport_failed',raw_body_base64='',raw_body_sha256=digest(b''))


def normalize_observation(observation):
    expected={'pair','anchor_ms','url','prepared_at','completed_at','elapsed_seconds',
              'http_status','error_type','raw_body_base64','raw_body_sha256'}
    if type(observation) is not dict or set(observation)!=expected:
        raise ValueError('original reference observation schema required')
    pair,anchor=observation['pair'],observation['anchor_ms']
    if observation['url']!=request_url(pair,anchor):raise ValueError('original public query differs')
    before,after=stamp(observation['prepared_at']),stamp(observation['completed_at'])
    elapsed=observation['elapsed_seconds'];encoded=observation['raw_body_base64']
    if type(encoded) is not str or len(encoded)>4*((MAX_RESPONSE_BYTES+2)//3):
        raise ValueError('bounded original response encoding required')
    try:body=base64.b64decode(encoded,validate=True)
    except (ValueError,TypeError):raise ValueError('original source response encoding differs') from None
    if (type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=TIMEOUT_SECONDS+3
            or not 0<=(after-before).total_seconds()<=TIMEOUT_SECONDS+4
            or len(body)>MAX_RESPONSE_BYTES or observation['raw_body_sha256']!=digest(body)
            or anchor>int(before.timestamp()*1000) or int(before.timestamp()*1000)-anchor>=INTERVAL_MS):
        raise ValueError('original bounded source bytes/clocks required')
    status=observation['http_status'];error=observation['error_type']
    if status is not None and (type(status) is not int or not 100<=status<=599):
        raise ValueError('original HTTP status required')
    if error is not None and (type(error) is not str or not re.fullmatch('[A-Za-z_][A-Za-z0-9_]{0,63}',error)):
        raise ValueError('bounded source failure classification required')
    if error or status!=200:
        return dict(pair=pair,status='unavailable',reason=error or 'http_status',rows=[],
                    known_at=after.isoformat(),rate_limited=status in (403,429))
    response=parse(body)
    if type(response) is not dict or type(response.get('retCode')) is not int:
        raise ValueError('original public response envelope required')
    if response['retCode']!=0:
        return dict(pair=pair,status='unavailable',reason='venue_error',rows=[],known_at=after.isoformat(),
                    rate_limited=response['retCode'] in (10006,10429))
    server_time=response.get('time')
    result=response.get('result')
    if (type(server_time) is not int or not int(before.timestamp()*1000)-5000<=server_time<=int(after.timestamp()*1000)+5000
            or type(result) is not dict or result.get('category')!='spot'
            or result.get('symbol')!=pair.replace('/','') or type(result.get('list')) is not list
            or len(result['list'])!=120):
        raise ValueError('complete original Spot source window required')
    records=[]
    for i,row in enumerate(result['list']):
        if (type(row) is not list or len(row)!=7 or any(type(v) is not str for v in row)
                or not re.fullmatch('[0-9]{13}',row[0])
                or int(row[0])!=anchor-INTERVAL_MS*(i+1)
                or any(not NUMERIC.fullmatch(v) for v in row[1:])):
            raise ValueError('forming/future/gapped/duplicate original source candle rejected')
        o,h,l,c,v,t=map(Decimal,row[1:])
        if not (0<l<=min(o,c)<=max(o,c)<=h and v>=0 and t>=0):
            raise ValueError('invalid reference OHLCV rejected')
        natural=dict(provider=ORIGIN,path='/v5/market/kline',category='spot',pair=pair,interval='5',open_ms=int(row[0]))
        records.append(dict(source_id=digest(canonical(natural)),version_sha256=digest(canonical(row)),
                            pair=pair,open_ms=int(row[0]),raw_row=row,known_at=after.isoformat()))
    records.reverse()
    age=(int(after.timestamp()*1000)-anchor)/1000
    return dict(pair=pair,status='ready' if 0<=age<=600 else 'stale',reason=None,rows=records,
                known_at=after.isoformat(),latest_close_ms=anchor,age_seconds=age,rate_limited=False)
