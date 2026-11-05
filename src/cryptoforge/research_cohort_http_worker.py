"""Fixed native 20-pair REST capture/replay. Never trains, predicts or publishes."""
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import stat
from types import SimpleNamespace
from urllib import parse, request

from cryptoforge import model_training as training, supabase_executor as executor, supabase_market as market

PAIRS = [s+'/USDT' for s in ('AERO', 'BABY1', 'BMT', 'BR', 'CAP', 'DATA', 'ENA', 'ERA', 'GRASS', 'INJ',
    'LIT', 'MEGA', 'MON', 'NEAR', 'ONDO', 'PEPE', 'SUI', 'VVV', 'WLD', 'ZRO')]
FIELDS = ('pair', 'symbol', 'open_time', 'open', 'high', 'low', 'close', 'volume', 'ingested_at')
NUMERIC = ('open', 'high', 'low', 'close', 'volume')
MODULES = ('cryptoforge', 'bybit_private', 'candle_contract', 'market_data', 'model_training',
    'night_research', 'night_research_cli', 'order_observer', 'supabase_executor', 'supabase_market', 'target_contracts')
ORIGIN = 'http://127.0.0.1:54321'


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()


def stamp(value):
    if type(value) is not str or len(value) > 40: raise ValueError('bounded_aware_timestamp_required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or not 2020 <= parsed.year <= 2100: raise ValueError('bounded_aware_timestamp_required')
    return parsed.astimezone(timezone.utc)


def write(directory, name, raw):
    with os.fdopen(os.open(directory/name, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    fd = os.open(directory, os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def read(directory, name, cap):
    path = directory/name; info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > cap:
        raise ValueError('private_bounded_regular_file_required')
    with os.fdopen(os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK), 'rb') as stream: raw = stream.read(cap+1)
    if len(raw) > cap: raise ValueError('file_byte_cap_exceeded')
    return raw


def exact_rows(raw, pair):
    if type(raw) is not bytes or len(raw) > 512000: raise ValueError('bounded_HTTP_body_required')
    def fields(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate_HTTP_field')
            result[key] = value
        return result
    def constant(value): raise ValueError('finite_HTTP_numbers_required')
    try: rows = json.loads(raw, parse_float=Decimal, parse_int=int, parse_constant=constant, object_pairs_hook=fields)
    except (ValueError, TypeError, OverflowError): raise ValueError('strict_HTTP_JSON_required') from None
    if type(rows) is not list or len(rows) > 500: raise ValueError('bounded_HTTP_rows_required')
    previous = None
    for row in rows:
        if type(row) is not dict or set(row) != set(FIELDS) or row['pair'] != pair or row['symbol'] != pair.replace('/', ''):
            raise ValueError('fixed_HTTP_row_identity_required')
        opened = stamp(row['open_time']); stamp(row['ingested_at'])
        if opened.microsecond or int(opened.timestamp()) % 300 or previous is not None and opened >= previous:
            raise ValueError('unique_descending_aligned_HTTP_candles_required')
        previous = opened
        for field in NUMERIC:
            value = row[field]
            if type(value) not in (str, int, Decimal) or len(str(value)) > 64 or re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', str(value)) is None:
                raise ValueError('bounded_HTTP_numeric_lexeme_required')
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or field != 'volume' and number == 0 or number.as_tuple().exponent < -12 or number.adjusted() >= (24 if field == 'volume' else 16):
                raise ValueError('database_numeric_domain_required')
        if not Decimal(str(row['low'])) <= min(Decimal(str(row['open'])), Decimal(str(row['close']))) <= max(Decimal(str(row['open'])), Decimal(str(row['close']))) <= Decimal(str(row['high'])):
            raise ValueError('valid_HTTP_OHLC_required')
    return rows


def query(url):
    parts = parse.urlsplit(url); values = parse.parse_qs(parts.query, keep_blank_values=True)
    pair = (values.get('pair') or [''])[0].removeprefix('eq.')
    expected = {'pair': ['eq.'+pair], 'exchange': ['eq.bybit'], 'market_type': ['eq.spot'], 'timeframe': ['eq.5m'],
        'select': [','.join(FIELDS)], 'order': ['open_time.desc'], 'limit': ['500']}
    if parts.scheme != 'http' or parts.netloc != '127.0.0.1:54321' or parts.path != '/rest/v1/market_candles' or parts.fragment or values != expected or pair not in PAIRS:
        raise ValueError('closed_local_native_500bar_query_required')
    return pair, values


def forbidden(*args, **kwargs): raise ValueError('model_fit_prediction_publication_forbidden')


def evaluate(directory, mode):
    directory = Path(directory); manifest = {}; bodies = {}; parsed = {}; trace = []; captured = {}
    key = 'offline-retained-HTTP-not-a-credential'; live = mode == 'capture'
    if mode not in ('capture', 'replay'): raise ValueError('fixed_HTTP_audit_mode_required')
    if live:
        key = read(Path('.local/database'), 'api-key', 8192).decode().strip()
        if not key: raise ValueError('existing_private_local_key_required')
        started = datetime.now(timezone.utc).isoformat()
    else:
        saved = json.loads(read(directory, 'capture.json', 65536)); manifest = saved['responses']; started = saved['started_at']
        if set(manifest) != set(PAIRS): raise ValueError('complete_fixed_cohort_capture_required')
        stamp(started); stamp(saved['completed_at'])
    class NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs): return None
    opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
    phase = 'capture' if live else 'replay'
    def transport(req, timeout):
        pair, values = query(req.full_url)
        if req.get_method() != 'GET' or req.data is not None or timeout != 3 or req.get_header('Apikey') != key or req.get_header('Authorization') != 'Bearer '+key:
            raise ValueError('fixed_local_readonly_transport_required')
        index = PAIRS.index(pair); name = f'body-{index:02d}.json'
        if phase == 'capture':
            if pair in bodies: raise ValueError('HTTP_retry_forbidden')
            attempt = {'pair': pair, 'attempt': 1, 'method': 'GET', 'query': values,
                'started_at': datetime.now(timezone.utc).isoformat(), 'auth_values_recorded': False}
            write(directory, f'attempt-{index:02d}.json', canonical(attempt).encode())
            try:
                with opener.open(req, timeout=3) as response:
                    status = response.status
                    if type(status) is not int or status not in (200, 206): raise ValueError('HTTP_status_refused')
                    raw = response.read(512001)
            except Exception:
                write(directory, f'failure-{index:02d}.json', canonical({'pair': pair, 'status': 'request_failed_no_retry', 'exception_details_recorded': False}).encode())
                raise ValueError('local_HTTP_capture_failed_no_retry') from None
            if key.encode() in raw: raise ValueError('credential_echo_HTTP_body_refused')
            exact_rows(raw, pair)
            write(directory, name, raw)
            manifest[pair] = {'file': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'status': status, 'observed_at': datetime.now(timezone.utc).isoformat()}
            write(directory, f'receipt-{index:02d}.json', canonical(manifest[pair]).encode())
            bodies[pair] = raw
        else:
            if pair not in bodies:
                item = manifest[pair]
                if set(item) != {'file', 'bytes', 'sha256', 'status', 'observed_at'} or item['file'] != name or type(item['bytes']) is not int or type(item['status']) is not int or item['status'] not in (200, 206):
                    raise ValueError('fixed_HTTP_receipt_required')
                raw = read(directory, name, 512000)
                if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256'] or not stamp(started) <= stamp(item['observed_at']) <= stamp(saved['completed_at']):
                    raise ValueError('original_HTTP_body_or_clock_changed')
                bodies[pair] = raw
            raw = bodies[pair]
        parsed[pair] = exact_rows(raw, pair)
        if phase == 'replay':
            trace.append({'pair': pair, 'query': values, 'response_bytes': len(raw), 'response_sha256': hashlib.sha256(raw).hexdigest()})
        return io.BytesIO(raw)
    client = market.SupabaseRestClient(ORIGIN, key, timeout_seconds=3)
    class CapturedReader(executor.SupabaseMarketReader):
        def read_candles(self, pair, **kwargs):
            rows = super().read_candles(pair, **kwargs); captured[pair] = rows; return rows
    class ExactReader(executor.SupabaseMarketReader):
        def _get(self, path): return parsed[query(ORIGIN+'/rest/v1/'+path)[0]]
    def load(reader, cutoff):
        instance = SimpleNamespace(reader=reader, lookback_candles=500, horizon_candles=3, min_label_return=.003,
            feature_lookback_candles=120, maximum_source_age=timedelta(seconds=900), minimum_source_coverage=.8)
        examples = training.ModelTrainingRunner._load_examples(instance, PAIRS, timeframe='5m', as_of=stamp(cutoff))
        rows = [{'pair': e.pair, 'input_end_time': e.open_time.isoformat(), 'label_end_time': e.label_end_time.isoformat(),
            'feature_hex': [float(v).hex() for v in e.features], 'future_return_hex': float(e.future_return).hex(),
            'long_label': e.label, 'short_label': e.short_label} for e in examples]
        selected = []
        for pair in PAIRS:
            values = [r for r in rows if r['pair'] == pair]
            selected.append({'pair': pair, 'example': max(values, key=lambda r: stamp(r['input_end_time'])) if values else None})
        return {'source_admission': instance.last_source_admission, 'examples': rows, 'selected': selected}
    original_open = executor.request.urlopen
    guarded = {name: getattr(training, name) for name in ('train_logistic_model', 'fit_logistic_head', 'fit_standardizer', 'predict_probability')}
    try:
        executor.request.urlopen = transport
        for name in guarded: setattr(training, name, forbidden)
        with localcontext(Context(prec=28)):
            if live:
                native_reader = executor.SupabaseMarketReader(client)
                for pair in PAIRS: native_reader.read_candles(pair, timeframe='5m', limit=500)
                saved = {'schema_version': 'native-cohort-HTTP-capture-v1', 'evidence_kind': 'actual_local_HTTP_capture', 'started_at': started,
                    'completed_at': datetime.now(timezone.utc).isoformat(), 'responses': manifest,
                    'requests': 20, 'retries': 0, 'HTTP_snapshot_is_single_database_transaction': False}
                write(directory, 'capture.json', canonical(saved).encode()); phase = 'replay'
            native = load(CapturedReader(client), saved['completed_at']); exact = load(ExactReader(client), saved['completed_at'])
    finally:
        executor.request.urlopen = original_open
        for name, value in guarded.items(): setattr(training, name, value)
    if len(trace) != 20 or [item['pair'] for item in trace] != PAIRS: raise ValueError('all_20_native_queries_required')
    checked = mismatch = 0; errors = []
    for pair, candles in captured.items():
        by_time = {stamp(row['open_time']): row for row in parsed[pair]}
        for candle in candles:
            for field in NUMERIC:
                expected = Decimal(str(by_time[candle.open_time][field])); actual = getattr(candle, field); checked += 1
                if expected != actual:
                    mismatch += 1
                    if len(errors) < 12: errors.append({'pair': pair, 'open_time': candle.open_time.isoformat(), 'field': field,
                        'wire_decimal': str(expected), 'native_decimal': str(actual)})
    def summary(value):
        return {'source_admission': value['source_admission'], 'all_examples': len(value['examples']),
            'all_examples_sha256': digest(value['examples']), 'selected': value['selected']}
    loaded = {name: hashlib.sha256(Path(importlib.import_module('cryptoforge' if name == 'cryptoforge' else 'cryptoforge.'+name).__file__).read_bytes()).hexdigest() for name in MODULES}
    return {'schema_version': 'native-cohort-HTTP-worker-v1', 'capture_sha256': digest(saved), 'as_of': saved['completed_at'],
        'trace': trace, 'loaded_value_runtime': loaded, 'native': summary(native), 'exact_parser': summary(exact),
        'scalar_fields_checked': checked, 'scalar_mismatch_count': mismatch, 'scalar_mismatch_examples': errors,
        'all_native_examples_equal_exact_parser': native['examples'] == exact['examples'],
        'model_fit_prediction_publication_performed': False, 'historical_availability_verified': False,
        'single_database_transaction_verified': False, 'actual_HTTP_requests_this_execution': 20 if live else 0,
        'credentials_loaded_this_execution': live}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--mode', choices=('capture', 'replay'), required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = evaluate(args.directory, args.mode); raw = canonical(result).encode()
    if len(raw) > 524288: raise ValueError('bounded_cohort_HTTP_result_required')
    write(args.output.parent, args.output.name, raw)


if __name__ == '__main__': main()
