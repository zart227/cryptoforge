"""Fixed native calculations over original selected local-cache rows; no reader/fit API."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
import hashlib
import importlib
import json
import os
from pathlib import Path

from cryptoforge import model_training as training, supabase_executor as executor

MODULES = ('cryptoforge', 'bybit_private', 'candle_contract', 'market_data', 'model_training',
    'night_research', 'night_research_cli', 'order_observer', 'supabase_executor', 'supabase_market', 'target_contracts')


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def stamp(value): return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


class NoReader:
    def read_candles(self, *args, **kwargs): raise ValueError('implicit_local_or_network_reader_forbidden')


def evaluate(packet):
    from types import SimpleNamespace
    if len(packet['selections']) > 20: raise ValueError('local_cohort_sample_cap')
    output = []; rows_read = 0
    with localcontext(Context(prec=28)):
        for sample in packet['selections']:
            result = {'pair': sample['pair'], 'feature_hex': None, 'runtime_feature_hex': None,
                'training_feature_hex': None, 'future_return_hex': None, 'long_label': None, 'short_label': None}
            def candles(selected, cutoff):
                nonlocal rows_read
                parsed = []
                for r in selected:
                    opened = stamp(r['open_time']); closed = stamp(r['close_time']); observed = stamp(r['ingested_at'])
                    if r['pair'] != sample['pair'] or closed != opened+timedelta(minutes=5) or not closed <= observed <= cutoff:
                        raise ValueError('original_closed_selected_local_rows_required')
                    parsed.append(executor.CandleRow(r['pair'], r['symbol'], opened,
                        *[Decimal(r[k]) for k in ('open', 'high', 'low', 'close', 'volume')], cache_observed_at=observed))
                    rows_read += 1
                if any(b.open_time-a.open_time != timedelta(minutes=5) for a, b in zip(parsed, parsed[1:])):
                    raise ValueError('contiguous_original_local_rows_required')
                return parsed
            if sample['features'] is not None:
                inputs = candles(sample['features'], stamp(packet['plan']['decision_time']))
                if len(inputs) != 120 or inputs[-1].open_time+timedelta(minutes=5) != stamp(packet['plan']['decision_anchor']):
                    raise ValueError('fixed120_local_feature_anchor_required')
                result['feature_hex'] = [float(x).hex() for x in training.extract_features(inputs, [c.volume for c in inputs])]
                instance = SimpleNamespace(reader=NoReader(), _feature_snapshot_time=stamp(packet['plan']['decision_time']))
                runtime, state, observed = executor.SupabaseLiveExecutor._model_input_features(instance, inputs,
                    {'input_candle_state': 'closed_only', 'feature_lookback_candles': 120})
                if state != 'closed_only' or observed != stamp(packet['plan']['decision_time']): raise ValueError('fixed_local_runtime_asof_required')
                result['runtime_feature_hex'] = [float(x).hex() for x in runtime]
                if sample['labels'] is not None:
                    future = candles(sample['labels'], stamp(packet['plan']['label_information_end']))
                    examples = training.build_examples(sample['pair'], inputs+future, horizon_candles=3,
                        min_label_return=float(Decimal(packet['plan']['min_label_return'])), feature_lookback_candles=120)
                    if len(examples) != 1: raise ValueError('one_fixed_local_native_example_required')
                    example = examples[0]
                    if example.label_end_time != stamp(packet['plan']['label_end_time']): raise ValueError('fixed_local_label_endpoint_required')
                    result.update(training_feature_hex=[float(x).hex() for x in example.features],
                        future_return_hex=example.future_return.hex(), long_label=example.label, short_label=example.short_label)
            output.append(result)
    loaded = {}
    for name in MODULES:
        module = importlib.import_module('cryptoforge' if name == 'cryptoforge' else 'cryptoforge.'+name)
        loaded[name] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    return {'schema_version': 'local-cohort-native-values-v1', 'packet_sha256': digest(packet),
        'loaded_value_runtime': loaded, 'samples': output, 'source_rows_read': rows_read,
        'fit_performed': False, 'model_prediction_performed': False, 'provider_or_network_or_database_accessed': False,
        'actual_production_reader_invoked': False, 'source_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--input', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 8388608: raise ValueError('bounded_local_native_packet_required')
    result = evaluate(json.loads(args.input.read_text())); raw = canonical(result).encode()
    if len(raw) > 262144: raise ValueError('bounded_local_native_output_required')
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


if __name__ == '__main__': main()
