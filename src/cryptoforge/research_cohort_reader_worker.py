"""Native reader/loader over projected saved SQL rows; no real HTTP, DB, fit or prediction."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
import hashlib
import io
import importlib
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from urllib import parse

from cryptoforge import model_training as training, supabase_executor as executor, supabase_market as market

MODULES = ('cryptoforge', 'bybit_private', 'candle_contract', 'market_data', 'model_training',
    'night_research', 'night_research_cli', 'order_observer', 'supabase_executor', 'supabase_market', 'target_contracts')
FIELDS = ('pair', 'symbol', 'open_time', 'open', 'high', 'low', 'close', 'volume', 'ingested_at')
NUMERIC = ('open', 'high', 'low', 'close', 'volume')


def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(v): return hashlib.sha256(canonical(v).encode()).hexdigest()
def stamp(v): return datetime.fromisoformat(v.replace('Z', '+00:00')).astimezone(timezone.utc)


def wire(rows):
    if len(rows) > 500: raise ValueError('bounded_projected_reader_rows_required')
    result = []
    for row in rows:
        if set(row) != set(FIELDS): raise ValueError('fixed_projected_reader_fields_required')
        fields = []
        for field in FIELDS:
            value = row[field]
            if type(value) is not str or len(value) > 64: raise ValueError('bounded_projected_reader_lexeme_required')
            if field in NUMERIC:
                if re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?', value) is None:
                    raise ValueError('exact_database_numeric_lexeme_required')
                fields.append(json.dumps(field)+':'+value)
            else: fields.append(json.dumps(field)+':'+json.dumps(value))
        result.append('{'+','.join(fields)+'}')
    raw = ('['+','.join(result)+']').encode()
    if len(raw) > 512000: raise ValueError('bounded_projected_pair_wire_required')
    return raw


def forbidden(*a, **kw): raise ValueError('model_fit_prediction_or_publication_forbidden_in_reader_audit')


def evaluate(packet):
    pairs = packet['pairs']; rows = packet['rows']; cutoff = stamp(packet['as_of']); anchor = stamp(packet['anchor'])
    if (not 1 <= len(pairs) <= 20 or pairs != sorted(set(pairs)) or len(rows) > 10000
            or packet['wire_kind'] != 'projected_SQL_numeric_lexemes_not_original_HTTP_body'):
        raise ValueError('fixed_saved_cohort_reader_scope_required')
    grouped = {pair: [] for pair in pairs}
    for row in rows:
        if row['pair'] not in grouped or row['symbol'] != row['pair'].replace('/', ''): raise ValueError('projected_market_identity_required')
        grouped[row['pair']].append(row)
    wires = {pair: wire(sorted(grouped[pair], key=lambda r: stamp(r['open_time']), reverse=True)) for pair in pairs}
    parsed = {pair: json.loads(body, parse_float=Decimal, parse_int=int) for pair, body in wires.items()}
    trace = []; captured = {}; synthetic_key = 'offline-projected-source-not-a-credential'
    client = market.SupabaseRestClient('https://retained-cohort.invalid', synthetic_key, timeout_seconds=3)
    def query(path):
        values = parse.parse_qs(path.partition('?')[2]); pair = (values.get('pair') or [''])[0].removeprefix('eq.')
        expected = {'pair': ['eq.'+pair], 'exchange': ['eq.bybit'], 'market_type': ['eq.spot'], 'timeframe': ['eq.5m'],
            'select': [','.join(FIELDS)], 'order': ['open_time.desc'], 'limit': ['500']}
        if path.partition('?')[0] != 'market_candles' or values != expected or pair not in wires:
            raise ValueError('native_fixed500_reader_query_required')
        return pair, values
    def projected_open(req, timeout):
        url = parse.urlsplit(req.full_url)
        if (url.scheme != 'https' or url.netloc != 'retained-cohort.invalid' or url.fragment
                or not url.path.startswith('/rest/v1/') or req.get_method() != 'GET' or req.data is not None or timeout != 3
                or req.get_header('Apikey') != synthetic_key or req.get_header('Authorization') != 'Bearer '+synthetic_key):
            raise ValueError('offline_reader_transport_only_required')
        pair, values = query(url.path.removeprefix('/rest/v1/')+'?'+url.query)
        if any(item['pair'] == pair for item in trace): raise ValueError('one_projected_reader_call_per_pair_required')
        body = wires[pair]; trace.append({'pair': pair, 'query': values, 'projected_body_bytes': len(body),
            'projected_body_sha256': hashlib.sha256(body).hexdigest(), 'actual_network_request': False})
        return io.BytesIO(body)
    class CapturedReader(executor.SupabaseMarketReader):
        def read_candles(self, pair, **kwargs):
            candles = super().read_candles(pair, **kwargs); captured[pair] = candles; return candles
    class ExactReader(executor.SupabaseMarketReader):
        def _get(self, path): return parsed[query(path)[0]]
    def load(reader):
        instance = SimpleNamespace(reader=reader, lookback_candles=500, horizon_candles=3, min_label_return=.003,
            feature_lookback_candles=120, maximum_source_age=timedelta(seconds=900), minimum_source_coverage=.8)
        examples = training.ModelTrainingRunner._load_examples(instance, pairs, timeframe='5m', as_of=cutoff)
        values = [{'pair': e.pair, 'input_end_time': e.open_time.isoformat(), 'label_end_time': e.label_end_time.isoformat(),
            'feature_hex': [float(v).hex() for v in e.features], 'future_return_hex': float(e.future_return).hex(),
            'long_label': e.label, 'short_label': e.short_label} for e in examples]
        selected = []
        for pair in pairs:
            found = [row for row in values if row['pair'] == pair and stamp(row['input_end_time']) == anchor-timedelta(minutes=5)]
            if len(found) > 1: raise ValueError('unique_selected_native_loader_example_required')
            selected.append({'pair': pair, 'example': found[0] if found else None})
        return {'source_admission': instance.last_source_admission, 'examples': values, 'selected': selected}
    original_open = executor.request.urlopen
    saved = {name: getattr(training, name) for name in ('train_logistic_model', 'fit_logistic_head', 'fit_standardizer', 'predict_probability')}
    try:
        executor.request.urlopen = projected_open
        for name in saved: setattr(training, name, forbidden)
        with localcontext(Context(prec=28)):
            native = load(CapturedReader(client)); exact = load(ExactReader(client))
    finally:
        executor.request.urlopen = original_open
        for name, value in saved.items(): setattr(training, name, value)
    if len(trace) != len(pairs): raise ValueError('all_cohort_reader_calls_required')
    mismatches = []; checked = total_mismatch = 0
    for pair, candles in captured.items():
        source = {stamp(row['open_time']): row for row in grouped[pair]}
        for candle in candles:
            for field in NUMERIC:
                checked += 1; expected = Decimal(source[candle.open_time][field]); actual = getattr(candle, field)
                if expected != actual:
                    total_mismatch += 1
                    if len(mismatches) < 12: mismatches.append({'pair': pair, 'open_time': candle.open_time.isoformat(),
                        'field': field, 'source_decimal': str(expected), 'native_decimal': str(actual)})
    loaded = {}
    for name in MODULES:
        module = importlib.import_module('cryptoforge' if name == 'cryptoforge' else 'cryptoforge.'+name)
        loaded[name] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    def summary(item):
        return {'source_admission': item['source_admission'], 'all_examples': len(item['examples']),
            'all_examples_sha256': digest(item['examples']), 'selected': item['selected']}
    return {'schema_version': 'native-projected-cohort-reader-v1', 'packet_sha256': digest(packet), 'loaded_value_runtime': loaded,
        'trace': trace, 'native': summary(native), 'exact_numeric_parser': summary(exact),
        'all_native_examples_equal_exact_numeric_parser': native['examples'] == exact['examples'],
        'scalar_fields_checked': checked, 'scalar_mismatch_count': total_mismatch, 'scalar_mismatch_examples': mismatches,
        'actual_reader_and_loader_functions_invoked': True, 'actual_HTTP_or_database_requests': 0,
        'original_HTTP_wire_captured': False, 'fit_or_prediction_performed': False, 'real_credentials_loaded': False,
        'production_publication_or_source_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--input', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 8388608: raise ValueError('bounded_projected_cohort_packet_required')
    result = evaluate(json.loads(args.input.read_text())); raw = canonical(result).encode()
    if len(raw) > 524288: raise ValueError('bounded_projected_cohort_result_required')
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())


if __name__ == '__main__': main()
