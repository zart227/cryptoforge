"""Trusted native _load_examples audit over original source versions; never fits."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from cryptoforge import reference_source_ledger as source
from cryptoforge import model_training as training, supabase_executor as executor
from cryptoforge import candle_contract, target_contracts

MODULES = ('cryptoforge','bybit_private','candle_contract','market_data','model_training',
    'night_research','night_research_cli','order_observer','supabase_executor','supabase_market','target_contracts')


def stamp(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def evaluate(packet):
    ledger=source.ReferenceLedger.open(packet['reference'])
    if ledger.manifest['artifact_sha256'] is not None:raise ValueError('source_only_loader_audit_required')
    sessions=packet['sessions']
    if not 1<=len(sessions)<=2:raise ValueError('bounded_development_loader_sessions_required')
    output=[];rows_read=0
    with ledger._lease():
        ledger._check(active=False)
        db=source._database(ledger.path,ledger.policy,readonly=True)
        try:
            if db.execute('select count(*) from forecasts').fetchone()[0]:raise ValueError('forecasts_forbidden')
            with localcontext(Context(prec=28)):
                for session in sessions:
                    cutoff=stamp(session['as_of']);read_trace=[]
                    class Reader:
                        def read_candles(self,pair,*,timeframe,limit):
                            nonlocal rows_read
                            if timeframe!='5m' or type(limit) is not int or limit!=512 or pair not in session['pairs']:
                                raise ValueError('fixed_audit_reader_contract_required')
                            if any(r['pair']==pair for r in read_trace):raise ValueError('one_reader_call_per_pair_required')
                            records=session['rows'][pair]
                            if len(records)>512:raise ValueError('bounded_reader_snapshot_required')
                            candles=[]
                            for r in records:
                                opened=stamp(r['open_time']);known=stamp(r['known_at'])
                                if known>cutoff or opened+timedelta(minutes=5)>cutoff or r['symbol']!=pair.replace('/',''):
                                    raise ValueError('causal_original_loader_rows_required')
                                found=db.execute('select raw,pair,open_ms from versions where source_id=? and version=?',
                                    (r['source_id'],r['revision_sha256'])).fetchone()
                                if found is None:raise ValueError('original_loader_version_missing')
                                raw=source.parse(found[0])
                                if (source.digest(source.canonical(raw))!=r['revision_sha256'] or found[1]!=pair
                                        or int(raw[0])!=found[2] or int(opened.timestamp()*1000)!=found[2]):
                                    raise ValueError('original_loader_value_identity_mismatch')
                                numbers=[Decimal(v) for v in raw[1:6]]
                                if any(not v.is_finite() for v in numbers):raise ValueError('finite_loader_values_required')
                                candles.append(executor.CandleRow(pair,pair.replace('/',''),opened,*numbers,cache_observed_at=known))
                            if any(b.open_time<=a.open_time for a,b in zip(candles,candles[1:])):
                                raise ValueError('ordered_unique_loader_rows_required')
                            rows_read+=len(candles)
                            read_trace.append({'pair':pair,'timeframe':timeframe,'limit':limit,'returned':len(candles),
                                'selected_rows_sha256':digest(records)})
                            return candles
                    instance=SimpleNamespace(reader=Reader(),lookback_candles=512,horizon_candles=3,
                        min_label_return=float(Decimal(packet['target']['min_label_return'])),feature_lookback_candles=120,
                        maximum_source_age=timedelta(minutes=10),minimum_source_coverage=1.0)
                    examples=training.ModelTrainingRunner._load_examples(instance,session['pairs'],timeframe='5m',as_of=cutoff)
                    selected=[]
                    for sample in session['samples']:
                        expected_input=stamp(sample['decision_anchor'])-timedelta(minutes=5)
                        matches=[e for e in examples if e.pair==sample['pair'] and e.open_time==expected_input]
                        if len(matches)>1:raise ValueError('unique_native_loader_example_required')
                        example=matches[0] if matches else None
                        result=None
                        if example is not None:
                            if any(not math.isfinite(v) for v in (*example.features,example.future_return)):
                                raise ValueError('finite_native_loader_example_required')
                            result={'feature_hex':[float(v).hex() for v in example.features],
                                'future_return_hex':float(example.future_return).hex(),'long_label':example.label,
                                'short_label':example.short_label,'input_end_time':example.open_time.isoformat(),
                                'label_end_time':example.label_end_time.isoformat()}
                        selected.append({'id':sample['id'],'example':result})
                    output.append({'partition':session['partition'],'as_of':session['as_of'],'reader_trace':read_trace,
                        'source_admission':instance.last_source_admission,'all_native_examples':len(examples),'samples':selected})
        finally:db.close()
    if source.file_sha(ledger.path,8*1024*1024)!=packet['reference']['database_sha256']:
        raise ValueError('original_loader_source_changed')
    loaded={n:hashlib.sha256(Path(sys.modules['cryptoforge' if n=='cryptoforge' else 'cryptoforge.'+n].__file__).read_bytes()).hexdigest() for n in MODULES}
    return {'schema_version':'research-native-loader-v1','packet_sha256':digest(packet),'loaded_value_runtime':loaded,
        'loaded_source_runtime':source.runtime_hashes(),'decimal_precision':28,'source_rows_read':rows_read,
        'sessions':output,'actual_native_loader_invoked':True,'operational_postgresql_reader_checked':False,
        'fit_performed':False,'model_prediction_performed':False,'network_request_performed':False,'source_modified':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raw=args.input.read_bytes()
    if len(raw)>2097152:raise ValueError('bounded_loader_packet_required')
    result=evaluate(json.loads(raw));raw=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(raw)>262144:raise ValueError('bounded_loader_result_required')
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())


if __name__=='__main__':main()
