"""Independent exact-rational specification of bounded-window candle-v1.

No trainer/runtime imports. EMA uses its closed weighted sum, RSI uses the
gain/loss identity. Decimal28 recurrence is deliberately not reproduced here:
any binary64 disagreement is evidence, never silently covered by tolerance.
"""
from fractions import Fraction
import math
import re


FEATURES = ('return_1', 'return_3', 'range_12', 'volume_ratio', 'ema_gap', 'rsi_14', 'candle_body')
SPEC = {
    'schema_version': 'research-feature-reference-spec-v1',
    'feature_version': 'candle-v1', 'input_state': 'closed_only',
    'timeframe_seconds': 300, 'window_candles': 120,
    'arithmetic': 'exact_decimal_lexemes_as_fractions_then_binary64',
    'comparison': 'exact_finite_float_hex_without_tolerance',
    'feature_order': list(FEATURES),
    'formulae': {
        'return_1': '(C119-C118)/C118',
        'return_3': '(C119-C116)/C116',
        'range_12': '(max(H108..H119)-min(L108..L119))/C119',
        'volume_ratio': '20*V119/sum(V100..V119); zero if denominator zero',
        'ema_gap': '(E12-E36)/C119; Ep=C0*r^119+sum(2*Cj*r^(119-j)/(p+1),j=1..119); r=(p-1)/(p+1)',
        'rsi_14': 'G/(G+L); G=sum(max(Cj-Cj-1,0),j=106..119); L=sum(max(Cj-1-Cj,0),j=106..119); one if L=0',
        'candle_body': '(C119-O119)/C119',
    },
    'zero_loss_rsi': 'one_including_flat_window',
    'legacy_prefix_ema_supported': False,
    'training_admission_enabled': False,
}


def quote(text, *, zero=False):
    if type(text) is not str or len(text) > 64 or re.fullmatch(r'(?:0|[1-9][0-9]{0,35})(?:\.[0-9]{1,24})?', text) is None:
        raise ValueError('bounded_plain_decimal_lexeme_required')
    # Fraction reads the decimal string directly, without the Decimal context.
    number = Fraction(text)
    if number > 10**18 or number < (0 if zero else Fraction(1, 10**18)):
        raise ValueError('bounded_nonnegative_quote_required')
    return number


def weighted_ema(closes, period):
    if period not in (12, 36) or len(closes) != 120:
        raise ValueError('fixed_bounded_ema_contract_required')
    ratio = Fraction(period-1, period+1)
    weights = [ratio**power for power in range(120)]
    return closes[0]*weights[119] + sum(
        (Fraction(2, period+1)*closes[index]*weights[119-index] for index in range(1, 120)), Fraction())


def reference(rows):
    """Rows have exactly five canonical O/H/L/C/V decimal lexemes."""
    if type(rows) is not list or len(rows) != 120:
        raise ValueError('exactly120_original_candles_required')
    parsed = []
    for row in rows:
        if type(row) is not list or len(row) != 5:
            raise ValueError('five_decimal_ohlcv_values_required')
        values = [quote(value, zero=index == 4) for index, value in enumerate(row)]
        opened, high, low, close, _ = values
        if not low <= min(opened, close) <= max(opened, close) <= high:
            raise ValueError('valid_original_ohlcv_geometry_required')
        parsed.append(values)
    closes = [row[3] for row in parsed]
    volume_sum = sum(row[4] for row in parsed[100:])
    deltas = [closes[index]-closes[index-1] for index in range(106, 120)]
    gains = sum(max(change, 0) for change in deltas)
    losses = sum(max(-change, 0) for change in deltas)
    exact = [
        (closes[119]-closes[118])/closes[118],
        (closes[119]-closes[116])/closes[116],
        (max(row[1] for row in parsed[108:])-min(row[2] for row in parsed[108:]))/closes[119],
        20*parsed[119][4]/volume_sum if volume_sum else Fraction(),
        (weighted_ema(closes, 12)-weighted_ema(closes, 36))/closes[119],
        gains/(gains+losses) if losses else Fraction(1),
        (closes[119]-parsed[119][0])/closes[119],
    ]
    converted = [float(number) for number in exact]
    if not all(math.isfinite(number) for number in converted):
        raise ValueError('finite_reference_features_required')
    return [number.hex() for number in converted]
