"""Audit exact native local REST reader and replay the same bytes with Decimal parsing."""
import argparse
import base64
from datetime import datetime,timedelta,timezone
from decimal import Context,Decimal,localcontext
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from urllib import request,parse

from cryptoforge import model_training as training,supabase_executor as executor,supabase_market as market
from cryptoforge import reference_source_ledger as source,candle_contract,target_contracts

FIELDS={'pair','symbol','open_time','open','high','low','close','volume','ingested_at'}
NUMERIC=('open','high','low','close','volume')
MODULES=('cryptoforge','bybit_private','candle_contract','market_data','model_training','night_research',
    'night_research_cli','order_observer','supabase_executor','supabase_market','target_contracts')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def stamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def exact_rows(raw,pair):
    if len(raw)>512000:raise ValueError('bounded_local_rest_body_required')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('duplicate_rest_field')
            result[k]=v
        return result
    def constant(_):raise ValueError('finite_json_numbers_required')
    rows=json.loads(raw,parse_float=Decimal,parse_int=int,parse_constant=constant,object_pairs_hook=pairs)
    if type(rows) is not list or len(rows)>144:raise ValueError('bounded_native_rowset_required')
    opened=set()
    for r in rows:
        if type(r) is not dict or set(r)!=FIELDS or r['pair']!=pair or r['symbol']!=pair.replace('/',''):
            raise ValueError('fixed_rest_row_identity_required')
        for k in ('open_time','ingested_at'):
            if type(r[k]) is not str or len(r[k])>40 or datetime.fromisoformat(r[k].replace('Z','+00:00')).tzinfo is None:raise ValueError('aware_rest_timestamps_required')
            stamp(r[k])
        instant=stamp(r['open_time'])
        if instant in opened or instant.microsecond or int(instant.timestamp())%300:raise ValueError('unique_aligned_rest_candle_times_required')
        opened.add(instant)
        for k in NUMERIC:
            if type(r[k]) not in (str,int,Decimal) or len(str(r[k]))>64:raise ValueError('bounded_exact_numeric_required')
            n=Decimal(str(r[k]))
            if not n.is_finite() or n<0 or (k!='volume' and n==0) or n.as_tuple().exponent < -12 or n.adjusted()>=(24 if k=='volume' else 16):raise ValueError('finite_positive_quote_required')
    return rows


def evaluate(packet):
    if set(packet)!={'mode','as_of','wires'} or packet['mode'] not in ('local_api','retained_wire_replay'):
        raise ValueError('fixed_native_rest_action_required')
    cutoff=stamp(packet['as_of']);wires={};trace=[];parsed={};captured={};key='synthetic-retained-wire-replay'
    if packet['mode']=='local_api':
        if packet['wires'] is not None:raise ValueError('fresh_local_api_has_no_fixture_input')
        p=Path('.local/database/api-key');s=p.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o600 or not 1<=s.st_size<=8192:
            raise ValueError('private_existing_local_api_key_required')
        with os.fdopen(os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'r') as stream:key=stream.read(8193).strip()
        if not key or len(key)>8192:raise ValueError('bounded_existing_key_required')
    elif type(packet['wires']) is not dict or set(packet['wires'])!={'BTC/USDT','ETH/USDT'}:raise ValueError('two_retained_wire_responses_required')
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k):return None
    opener=request.build_opener(request.ProxyHandler({}),NoRedirect())
    original=executor.request.urlopen
    def bounded_open(req,timeout):
        url=parse.urlsplit(req.full_url);query=parse.parse_qs(url.query,keep_blank_values=True)
        pair=(query.get('pair') or [''])[0].removeprefix('eq.')
        expected={'pair':['eq.'+pair],'exchange':['eq.bybit'],'market_type':['eq.spot'],'timeframe':['eq.5m'],
            'select':['pair,symbol,open_time,open,high,low,close,volume,ingested_at'],'order':['open_time.desc'],'limit':['144']}
        if (url.scheme!='http' or url.netloc!='127.0.0.1:54321' or url.path!='/rest/v1/market_candles' or url.fragment
                or req.get_method()!='GET' or req.data is not None or query!=expected or pair not in ('BTC/USDT','ETH/USDT')
                or pair in wires or timeout!=3 or req.get_header('Apikey')!=key or req.get_header('Authorization')!='Bearer '+key):
            raise ValueError('closed_local_reader_get_required')
        if packet['mode']=='local_api':
            try:
                with opener.open(req,timeout=3) as response:
                    if response.status not in (200,206):raise ValueError('local_reader_http_status')
                    raw=response.read(512001)
            except Exception:raise ValueError('local_reader_request_rejected') from None
            retained={'body_base64':base64.b64encode(raw).decode(),'retrieved_at':datetime.now(timezone.utc).isoformat()}
        else:
            retained=packet['wires'][pair]
            if set(retained)!={'body_base64','retrieved_at'}:raise ValueError('retained_wire_fields_required')
            raw=base64.b64decode(retained['body_base64'],validate=True);stamp(retained['retrieved_at'])
        if key.encode() in raw:raise ValueError('key_echo_body_refused')
        rows=exact_rows(raw,pair);parsed[pair]=rows;wires[pair]=retained
        trace.append({'pair':pair,'method':'GET','path':url.path,'query':query,'response_bytes':len(raw),
            'response_sha256':hashlib.sha256(raw).hexdigest(),'auth_values_copied':False})
        return io.BytesIO(raw)
    class CapturedReader(executor.SupabaseMarketReader):
        def read_candles(self,pair,**kwargs):
            rows=super().read_candles(pair,**kwargs);captured[pair]=rows;return rows
    def load(reader):
        instance=SimpleNamespace(reader=reader,lookback_candles=144,horizon_candles=3,min_label_return=.003,
            feature_lookback_candles=120,maximum_source_age=timedelta(minutes=10),minimum_source_coverage=1.0)
        examples=training.ModelTrainingRunner._load_examples(instance,['BTC/USDT','ETH/USDT'],timeframe='5m',as_of=cutoff)
        values=[{'pair':e.pair,'input_end_time':e.open_time.isoformat(),'label_end_time':e.label_end_time.isoformat(),
            'feature_hex':[float(v).hex() for v in e.features],'return_hex':float(e.future_return).hex(),'long_label':e.label,'short_label':e.short_label} for e in examples]
        if any(not math.isfinite(float.fromhex(v)) for e in values for v in [*e['feature_hex'],e['return_hex']]):raise ValueError('finite_example_values_required')
        return {'source_admission':instance.last_source_admission,'examples':values}
    client=market.SupabaseRestClient('http://127.0.0.1:54321',key,timeout_seconds=3)
    try:
        executor.request.urlopen=bounded_open
        with localcontext(Context(prec=28)):native=load(CapturedReader(client))
    finally:executor.request.urlopen=original
    if set(wires)!={'BTC/USDT','ETH/USDT'} or len(trace)!=2:raise ValueError('exactly_two_native_reader_calls_required')
    class ExactReader(executor.SupabaseMarketReader):
        def _get(self,path):
            q=parse.parse_qs(path.partition('?')[2]);return parsed[q['pair'][0].removeprefix('eq.')]
    with localcontext(Context(prec=28)):exact=load(ExactReader(client))
    mismatches=[];scalars=0
    for pair,rows in captured.items():
        by_open={stamp(r['open_time']):r for r in parsed[pair]}
        for row in rows:
            for field in NUMERIC:
                scalars+=1;expected=Decimal(str(by_open[row.open_time][field]));actual=getattr(row,field)
                if expected!=actual:mismatches.append({'pair':pair,'open_time':row.open_time.isoformat(),'field':field,'wire_decimal':str(expected),'native_decimal':str(actual)})
    loaded={n:hashlib.sha256(Path(sys.modules['cryptoforge' if n=='cryptoforge' else 'cryptoforge.'+n].__file__).read_bytes()).hexdigest() for n in MODULES}
    math_result={'native':native,'exact_same_wire':exact,'scalar_fields_checked':scalars,'scalar_mismatch_count':len(mismatches),
        'scalar_mismatch_examples':mismatches[:12],'all_native_examples_equal_exact_parser':native['examples']==exact['examples'],
        'reader_query_contains_asof_filter':False,'historical_first_seen_or_revisions_verified':False}
    return {'schema_version':'native-local-rest-worker-v1','mode':packet['mode'],'as_of':packet['as_of'],'wires':wires,'trace':trace,
        'loaded_value_runtime':loaded,'loaded_source_runtime':source.runtime_hashes(),'comparison':math_result,
        'local_api_requests':2 if packet['mode']=='local_api' else 0,'fit_performed':False,'model_prediction_performed':False,'database_writes':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    raw=args.input.read_bytes()
    if len(raw)>2097152:raise ValueError('bounded_native_reader_packet_required')
    result=evaluate(json.loads(raw));raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(raw)>2097152:raise ValueError('bounded_native_reader_result_required')
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


if __name__=='__main__':main()
