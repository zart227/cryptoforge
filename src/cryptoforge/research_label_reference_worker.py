"""Independent source endpoint/label replay; stdlib and exact quote parser only."""
import argparse
from datetime import timedelta
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3

from cryptoforge.research_feature_reference import quote
from cryptoforge.research_feature_reference_worker import canonical, digest, stamp


SPEC = {'schema_version': 'research-label-reference-spec-v1',
    'target_version': 'fixed-future-return-v1', 'horizon_candles': 3,
    'timeframe_seconds': 300, 'reference': 'last_feature_candle_close',
    'future': 'third_label_candle_close', 'arithmetic': 'exact_fraction_then_binary64',
    'long_rule': 'binary64_return > binary64_threshold',
    'short_rule': 'binary64_return < -binary64_threshold',
    'fee_accounting': 'price_return_excludes_execution_fees',
    'missing_feature_or_label_selection': 'null_no_comparison',
    'training_admission_enabled': False}


def labels(reference_close, future_close, threshold):
    if (type(threshold) is not str or re.fullmatch(r'0(?:\.\d{1,12})?', threshold) is None
            or not 0 <= Fraction(threshold) <= Fraction(1, 10)):
        raise ValueError('bounded_price_label_threshold_required')
    price, future = quote(reference_close), quote(future_close)
    exact = (future-price)/price
    result, boundary = float(exact), float(Fraction(threshold))
    if not math.isfinite(result):
        raise ValueError('finite_label_reference_required')
    return {'future_return_hex': result.hex(), 'long_label': int(result > boundary),
        'short_label': int(result < -boundary),
        'exact_return_numerator': str(exact.numerator), 'exact_return_denominator': str(exact.denominator)}


def evaluate(packet):
    if set(packet) != {'reference', 'selections', 'target'}:
        raise ValueError('fixed_label_packet_required')
    target = packet['target']
    if (set(target) != {'schema_version', 'target_version', 'fee_accounting', 'min_label_return', 'round_trip_cost'}
            or target['schema_version'] != 'research-price-value-target-v1'
            or target['target_version'] != SPEC['target_version'] or target['fee_accounting'] != SPEC['fee_accounting']):
        raise ValueError('fixed_price_target_required')
    labels('1', '1', target['min_label_return'])
    if type(packet['selections']) is not list or not 1 <= len(packet['selections']) <= 16:
        raise ValueError('bounded_label_samples_required')
    source = packet['reference']; path = Path(source['root'])/'source.sqlite'
    def check():
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 8*1024*1024:
            raise ValueError('bounded_original_source_required')
        if hashlib.sha256(path.read_bytes()).hexdigest() != source['database_sha256']:
            raise ValueError('original_source_checksum_changed')
    check()
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=1)
    db.execute('PRAGMA query_only=ON')
    output = []; count = 0
    try:
        if db.execute('SELECT count(*) FROM forecasts').fetchone()[0] != 0:
            raise ValueError('source_only_label_reference_required')
        for index, sample in enumerate(packet['selections']):
            if type(sample['id']) is not int or sample['id'] != index:
                raise ValueError('fixed_label_sample_order_required')
            result = {'id': sample['id'], 'values': None, 'selected_raw_sha256': None}
            if sample['features'] is not None and sample['labels'] is not None:
                if len(sample['features']) != 120 or len(sample['labels']) != 3:
                    raise ValueError('complete_fixed_label_horizon_required')
                anchor = stamp(sample['decision_anchor']); cutoff = stamp(sample['information_end'])
                if stamp(sample['label_end_time']) != anchor+timedelta(minutes=15):
                    raise ValueError('fixed_label_end_required')
                chosen = [sample['features'][-1], *sample['labels']]
                raws = []; identities = []
                for offset, selected in enumerate(chosen):
                    expected = anchor+timedelta(minutes=5*(offset-1))
                    limit = stamp(sample['decision_time']) if offset == 0 else cutoff
                    found = db.execute('SELECT raw,pair,open_ms FROM versions WHERE source_id=? AND version=?',
                        (selected['source_id'], selected['revision_sha256'])).fetchone()
                    if found is None:
                        raise ValueError('original_label_version_missing')
                    raw = json.loads(found[0]); opened = stamp(selected['open_time'])
                    opened_ms = int(expected.timestamp())*1000
                    if (opened != expected or expected.second or expected.microsecond or expected.minute % 5
                            or stamp(selected['close_time']) != expected+timedelta(minutes=5)
                            or stamp(selected['close_time']) > stamp(selected['observed_at'])
                            or not stamp(selected['first_seen_at']) <= stamp(selected['observed_at']) <= stamp(selected['known_at']) <= limit
                            or type(raw) is not list or len(raw) != 7 or any(type(v) is not str for v in raw)
                            or digest(raw) != selected['revision_sha256'] or int(raw[0]) != opened_ms
                            or found[2] != opened_ms or found[1].replace('/', '') != sample['symbol']
                            or selected['symbol'] != sample['symbol']):
                        raise ValueError('original_label_lineage_mismatch')
                    parsed = [quote(v, zero=i == 4) for i, v in enumerate(raw[1:6])]
                    op, hi, lo, cl, _ = parsed
                    if not lo <= min(op, cl) <= max(op, cl) <= hi:
                        raise ValueError('original_label_ohlcv_invalid')
                    raws.append(raw); identities.append(digest(raw)); count += 1
                values = labels(raws[0][4], raws[-1][4], target['min_label_return'])
                values.update(reference_close=raws[0][4], future_close=raws[-1][4],
                    training_input_end_time=chosen[0]['open_time'], label_end_time=chosen[-1]['close_time'])
                result.update(values=values, selected_raw_sha256=digest(identities))
            output.append(result)
    finally:
        db.close()
    check()
    return {'schema_version': 'research-label-reference-values-v1', 'reference_sha256': digest(source),
        'selection_sha256': digest(packet['selections']), 'target_sha256': digest(target),
        'specification_sha256': digest(SPEC), 'samples': output, 'source_rows_read': count,
        'trainer_or_runtime_imported': False, 'network_request_performed': False,
        'fit_performed': False, 'model_prediction_performed': False, 'source_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input.stat().st_size > 2097152:
        raise ValueError('bounded_label_packet_required')
    result = evaluate(json.loads(args.input.read_text()))
    import sys
    if any(n in sys.modules for n in ('cryptoforge.model_training', 'cryptoforge.supabase_executor')):
        raise ValueError('independent_label_runtime_required')
    raw = canonical(result).encode()
    if len(raw) > 262144:
        raise ValueError('bounded_label_result_required')
    with os.fdopen(os.open(args.output, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


if __name__ == '__main__':
    main()
