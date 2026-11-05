"""Trusted native feature/label compatibility check; no fit, prediction or orders."""
import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

from cryptoforge import reference_source_ledger as source
from cryptoforge import model_training as training, supabase_executor as executor
from cryptoforge import candle_contract, target_contracts


VALUE_MODULES = ('cryptoforge', 'bybit_private', 'candle_contract', 'market_data', 'model_training',
    'night_research', 'night_research_cli', 'order_observer', 'supabase_executor', 'supabase_market', 'target_contracts')


def stamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class NoReader:
    def read_candles(self, *args, **kwargs):
        raise ValueError('implicit_runtime_data_fetch_forbidden')


def evaluate(packet):
    ledger = source.ReferenceLedger.open(packet['reference'])
    if ledger.manifest['artifact_sha256'] is not None:
        raise ValueError('source_only_value_audit_required')
    target = packet['target']; threshold = float(Decimal(target['min_label_return']))
    rows_checked = 0
    with ledger._lease():
        ledger._check(active=False)
        db = source._database(ledger.path, ledger.policy, readonly=True)
        try:
            if db.execute('SELECT count(*) FROM forecasts').fetchone()[0]:
                raise ValueError('forecast_history_not_a_value_audit_input')
            def candles(records, pair, cutoff):
                nonlocal rows_checked
                result = []
                for record in records:
                    if stamp(record['known_at']) > cutoff or record['symbol'] != pair.replace('/', ''):
                        raise ValueError('selected_source_availability_mismatch')
                    found = db.execute('SELECT raw,pair,open_ms FROM versions WHERE source_id=? AND version=?',
                        (record['source_id'], record['revision_sha256'])).fetchone()
                    if found is None: raise ValueError('selected_original_version_missing')
                    raw = source.parse(found[0])
                    if (source.digest(source.canonical(raw)) != record['revision_sha256'] or found[1] != pair
                            or int(raw[0]) != found[2] or stamp(record['open_time']).timestamp()*1000 != found[2]):
                        raise ValueError('selected_raw_value_identity_mismatch')
                    opened = stamp(record['open_time'])
                    if opened+timedelta(minutes=5) > cutoff: raise ValueError('forming_value_rejected')
                    numbers = [Decimal(v) for v in raw[1:6]]
                    if any(not v.is_finite() for v in numbers): raise ValueError('finite_decimal_source_values_required')
                    result.append(executor.CandleRow(pair, pair.replace('/', ''), opened, *numbers,
                        cache_observed_at=stamp(record['known_at'])))
                    rows_checked += 1
                if any(b.open_time-a.open_time != timedelta(minutes=5) for a,b in zip(result,result[1:])):
                    raise ValueError('contiguous_selected_values_required')
                return result
            output = []
            with localcontext(Context(prec=28)):
                for selected in packet['selections']:
                    pair = selected['symbol'][:-4]+'/USDT'
                    result = {'id': selected['id'], 'feature_status': 'unavailable', 'runtime_feature_hex': None,
                        'extractor_feature_hex': None, 'runtime_contract': None,
                        'training_status': 'unavailable', 'training_feature_hex': None,
                        'future_return_hex': None, 'long_label': None, 'short_label': None,
                        'reference_close': None, 'future_close': None, 'label_end_time': None,
                        'training_input_end_time': None}
                    if selected['features'] is not None:
                        inputs = candles(selected['features'], pair, stamp(selected['decision_time']))
                        if len(inputs) != 120 or inputs[-1].open_time+timedelta(minutes=5) != stamp(selected['decision_anchor']):
                            raise ValueError('exact_closed120_anchor_required')
                        direct = training.extract_features(inputs, [c.volume for c in inputs])
                        config = {'input_candle_state': 'closed_only', 'feature_lookback_candles': 120}
                        instance = SimpleNamespace(reader=NoReader(), _feature_snapshot_time=stamp(selected['decision_time']))
                        runtime, state, observed = executor.SupabaseLiveExecutor._model_input_features(instance, inputs, config)
                        if state != 'closed_only' or observed != stamp(selected['decision_time']):
                            raise ValueError('fixed_runtime_asof_input_required')
                        if any(not math.isfinite(x) for x in (*direct,*runtime)): raise ValueError('finite_native_feature_values_required')
                        result.update(feature_status='checked', runtime_feature_hex=[float(v).hex() for v in runtime],
                            extractor_feature_hex=[float(v).hex() for v in direct],
                            runtime_contract=instance._resolved_model_input_contract)
                        if selected['labels'] is not None:
                            future = candles(selected['labels'], pair, stamp(selected['information_end']))
                            if len(future) != 3 or future[0].open_time != stamp(selected['decision_anchor']):
                                raise ValueError('exact_contiguous_horizon_values_required')
                            examples = training.build_examples(pair, inputs+future, horizon_candles=3,
                                min_label_return=threshold, feature_lookback_candles=120)
                            if len(examples) != 1: raise ValueError('one_native_training_example_required')
                            example = examples[0]
                            result.update(training_status='checked', training_feature_hex=[float(v).hex() for v in example.features],
                                future_return_hex=float(example.future_return).hex(), long_label=example.label,
                                short_label=example.short_label, reference_close=format(inputs[-1].close,'f'),
                                future_close=format(future[-1].close,'f'), label_end_time=example.label_end_time.isoformat(),
                                training_input_end_time=example.open_time.isoformat())
                    output.append(result)
        finally:
            db.close()
    if source.file_sha(ledger.path,8*1024*1024) != packet['reference']['database_sha256']:
        raise ValueError('original_source_changed_during_value_audit')
    import sys
    loaded = {name: hashlib.sha256(Path(sys.modules['cryptoforge' if name=='cryptoforge' else 'cryptoforge.'+name].__file__).read_bytes()).hexdigest()
              for name in VALUE_MODULES}
    return {'schema_version': 'research-native-values-v1', 'reference': packet['reference'],
        'selections_sha256': sha(packet['selections']), 'target_sha256': sha(target),
        'loaded_value_runtime': loaded, 'loaded_source_runtime': source.runtime_hashes(),
        'feature_names': list(training.FEATURE_NAMES), 'decimal_precision': 28, 'decimal_rounding': 'ROUND_HALF_EVEN',
        'target_contract': asdict(target_contracts.CONTRACTS['fixed-future-return-v1']),
        'source_rows_read': rows_checked, 'samples': output, 'fit_performed': False,
        'model_prediction_performed': False, 'network_request_performed': False, 'source_modified': False}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args = p.parse_args(); raw = args.input.read_bytes()
    if len(raw)>2*1024*1024: raise ValueError('bounded_native_value_packet_required')
    result = evaluate(json.loads(raw))
    raw = json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(raw)>262144: raise ValueError('bounded_native_value_result_required')
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:
        f.write(raw);f.flush();os.fsync(f.fileno())


if __name__ == '__main__': main()
