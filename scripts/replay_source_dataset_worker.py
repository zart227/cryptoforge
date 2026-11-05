"""Trusted, offline feature/label replay using the pinned main trainer source."""
from datetime import datetime, timedelta, timezone
from decimal import Context, localcontext
import hashlib
import importlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import sys
from types import SimpleNamespace
from urllib import parse

for kind, maximum in ((resource.RLIMIT_CPU, 20), (resource.RLIMIT_AS, 536870912),
                      (resource.RLIMIT_FSIZE, 8000000), (resource.RLIMIT_CORE, 0)):
    resource.setrlimit(kind, (maximum, maximum))
os.nice(10); signal.signal(signal.SIGALRM, signal.SIG_DFL); signal.alarm(60)

def forbidden(*args, **kwargs): raise ValueError('network_fit_prediction_publication_forbidden')
class NoNetworkSocket(socket.socket):
    connect = forbidden
    connect_ex = forbidden
    bind = forbidden
socket.socket = NoNetworkSocket; socket.create_connection = forbidden

from cryptoforge import model_training as training, supabase_executor as executor


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()


def evaluate(packet):
    required = {'schema_version', 'worker_sha256', 'module_hashes', 'pairs', 'as_of', 'rows'}
    if type(packet) is not dict or set(packet) != required or packet['schema_version'] != 'source-dataset-replay-request-v1':
        raise ValueError('fixed_replay_request_required')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != packet['worker_sha256']:
        raise ValueError('replay_worker_source_changed')
    if type(packet['pairs']) is not list or len(packet['pairs']) != 20 or len(set(packet['pairs'])) != 20:
        raise ValueError('fixed_twenty_pairs_required')
    if type(packet['rows']) is not dict or set(packet['rows']) != set(packet['pairs']):
        raise ValueError('all_original_pairs_required')
    for name, expected in packet['module_hashes'].items():
        module = importlib.import_module('cryptoforge' if name == 'cryptoforge' else 'cryptoforge.'+name)
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != expected:
            raise ValueError('original_native_runtime_changed')
    for name in ('train_logistic_model', 'fit_logistic_head', 'fit_standardizer', 'predict_probability'):
        setattr(training, name, forbidden)
    seen = []
    class Reader(executor.SupabaseMarketReader):
        def _get(self, path):
            parsed = parse.urlsplit(path); query = parse.parse_qs(parsed.query)
            pairs = query.get('pair', [])
            if parsed.path != 'market_candles' or len(pairs) != 1 or not pairs[0].startswith('eq.'):
                raise ValueError('fixed_retained_source_query_required')
            pair = pairs[0][3:]
            expected = {'pair':['eq.'+pair], 'exchange':['eq.bybit'], 'market_type':['eq.spot'], 'timeframe':['eq.5m'],
                'select':['pair,symbol,open_time,open,high,low,close,volume,ingested_at'],
                'order':['open_time.desc'], 'limit':['500']}
            if pair not in packet['rows'] or query != expected or pair in seen:
                raise ValueError('one_original_query_per_pair_required')
            seen.append(pair); return packet['rows'][pair]
    cutoff = datetime.fromisoformat(packet['as_of'].replace('Z', '+00:00')).astimezone(timezone.utc)
    runner = SimpleNamespace(reader=Reader(None), lookback_candles=500, horizon_candles=3,
        min_label_return=.003, feature_lookback_candles=120, maximum_source_age=timedelta(seconds=900),
        minimum_source_coverage=.8)
    with localcontext(Context(prec=28)):
        examples = training.ModelTrainingRunner._load_examples(runner, packet['pairs'], timeframe='5m', as_of=cutoff)
    if seen != packet['pairs']: raise ValueError('complete_original_source_query_order_required')
    rows = [{'pair':e.pair, 'input_end_time':e.open_time.isoformat(), 'label_end_time':e.label_end_time.isoformat(),
        'feature_hex':[float(v).hex() for v in e.features], 'future_return_hex':float(e.future_return).hex(),
        'long_label':e.label, 'short_label':e.short_label} for e in examples]
    return {'schema_version':'source-dataset-replay-result-v1','request_sha256':digest(packet),
        'examples':rows,'examples_sha256':digest(rows),'source_admission':runner.last_source_admission,
        'main_runtime_hashes':packet['module_hashes'],'query_pairs':seen,
        'network_fit_prediction_publication_performed':False}


if __name__ == '__main__':
    try:
        raw = sys.stdin.buffer.read(20_000_001)
        if len(raw)>20_000_000: raise ValueError('bounded_replay_input_required')
        result = canonical(evaluate(json.loads(raw))).encode()
        if len(result)>8_000_000: raise ValueError('bounded_replay_output_required')
        sys.stdout.buffer.write(result); sys.stdout.buffer.flush()
    except Exception: raise SystemExit('source dataset replay refused') from None
