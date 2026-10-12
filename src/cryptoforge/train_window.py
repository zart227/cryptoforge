"""Research-only causal training-window preparation; never selects a winner."""
from dataclasses import dataclass
from datetime import timedelta
from math import isfinite


@dataclass(frozen=True)
class TrainingWindow:
    rows: tuple
    weights: tuple
    effective_sample_size: float
    live_eligible: bool = False


def prepare_training_window(rows, *, train_end, window_days, half_life_days=None):
    """Use [start,end) entry times and labels known by the frozen train end.

    Reject unavailable inputs instead of silently treating future rows as train.
    Weights depend on entry age, never target sign or magnitude. A consumer must
    explicitly support these weights; passing just rows does not enable weighting.
    """
    if train_end.tzinfo is None or train_end.utcoffset() is None:
        raise ValueError('aware train cutoff required')
    for value in (window_days, half_life_days):
        if value is not None and (isinstance(value, bool) or not isfinite(value) or value <= 0):
            raise ValueError('positive finite window/half life required')
    if window_days is None:
        raise ValueError('explicit bounded window required')
    start = train_end - timedelta(days=window_days)
    selected = []
    seen = set()
    for row in rows:
        for timestamp in (row.open_time, row.label_end_time):
            if timestamp is None or timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError('aware entry and label availability required')
        if not row.open_time <= row.label_end_time <= train_end or row.open_time >= train_end:
            raise ValueError('future or unordered training input')
        identity = (row.pair, row.open_time)
        if identity in seen:
            raise ValueError('duplicate training identity')
        seen.add(identity)
        if row.open_time >= start:
            selected.append(row)
    selected.sort(key=lambda row: (row.open_time, row.pair))
    if len(selected) < 2:
        raise ValueError('at least two samples inside training window required')
    weights = tuple(1.0 if half_life_days is None else
                    2.0 ** (-((train_end - row.open_time).total_seconds() / 86400) / half_life_days)
                    for row in selected)
    if any(not isfinite(weight) or weight <= 0 for weight in weights):
        raise ValueError('recency weights underflow or are invalid')
    # Normalize to mean one; regularization scale is invariant to sample count.
    total = sum(weights)
    weights = tuple(weight * len(weights) / total for weight in weights)
    effective = sum(weights) ** 2 / sum(weight * weight for weight in weights)
    return TrainingWindow(tuple(selected), weights, effective)
