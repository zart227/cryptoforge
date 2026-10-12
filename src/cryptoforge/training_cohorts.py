"""Causal support diagnostics for observed Spot-long net training examples."""
from datetime import UTC
from math import isfinite
from cryptoforge.net_regression import NET_TARGETS


def net_training_cohorts(examples, *, as_of, target_version):
    if target_version not in NET_TARGETS:
        raise ValueError('explicit net target required for cohort diagnostics')
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError('aware cohort cutoff required')
    groups = {'by_pair': {}, 'by_utc_entry_day': {}}
    available = positive = negative = zero = 0
    excluded = {'unknown_label_availability': 0, 'label_not_yet_available': 0}
    seen = set()
    for row in examples:
        if row.open_time.tzinfo is None or row.open_time.utcoffset() is None:
            raise ValueError('aware entry time required')
        key = (row.pair, row.open_time)
        if key in seen:
            raise ValueError('duplicate cohort sample identity')
        seen.add(key)
        if row.label_end_time is None:
            excluded['unknown_label_availability'] += 1
            continue
        if row.label_end_time.tzinfo is None or row.label_end_time.utcoffset() is None:
            raise ValueError('aware label availability required')
        if row.label_end_time < row.open_time:
            raise ValueError('unordered label availability')
        if row.label_end_time > as_of:
            # Never inspect unavailable target/features to produce label statistics.
            excluded['label_not_yet_available'] += 1
            continue
        if (row.short_label != 0 or len(row.features) != 7
                or not all(isfinite(value) for value in row.features)
                or not isfinite(row.future_return) or row.future_return < -1
                or row.label != int(row.future_return > 0)):
            raise ValueError('valid observed seven-feature Spot net example required')
        available += 1
        positive += int(row.future_return > 0)
        negative += int(row.future_return < 0)
        zero += int(row.future_return == 0)
        day = row.open_time.astimezone(UTC).date().isoformat()
        for axis, name in (('by_pair', row.pair), ('by_utc_entry_day', day)):
            group = groups[axis].setdefault(name, {'examples': 0, 'positive': 0,
                                                   'negative': 0, 'zero': 0})
            group['examples'] += 1
            group['positive'] += int(row.future_return > 0)
            group['negative'] += int(row.future_return < 0)
            group['zero'] += int(row.future_return == 0)
    return {**groups, 'available_examples': available, 'positive': positive,
            'negative': negative, 'zero': zero, 'excluded': excluded,
            'positive_fraction': positive / available if available else None,
            'largest_pair_fraction': max((g['examples'] for g in groups['by_pair'].values()), default=0) / available if available else None,
            'largest_day_fraction': max((g['examples'] for g in groups['by_utc_entry_day'].values()), default=0) / available if available else None,
            'as_of': as_of.isoformat(), 'target_version': target_version, 'live_promotion_allowed': False,
            'scope': 'training_example_support_not_independent_executed_portfolio_trades'}
