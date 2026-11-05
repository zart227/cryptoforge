"""Exact entry exposure and planned-stop budget checks; never an execution guarantee."""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json

from cryptoforge.execution_controls import unique_fields


@dataclass(frozen=True)
class FractionalRiskPolicy:
    maximum_position_fraction: Decimal
    maximum_planned_risk_fraction: Decimal
    stop_fraction: Decimal
    round_trip_cost_fraction: Decimal

    def __post_init__(self):
        values = (self.maximum_position_fraction, self.maximum_planned_risk_fraction,
            self.stop_fraction, self.round_trip_cost_fraction)
        if any(not isinstance(value, Decimal) or not value.is_finite() for value in values):
            raise ValueError('finite Decimal policy fractions required')
        if (not 0 < self.maximum_position_fraction <= Decimal('.05')
                or not 0 < self.maximum_planned_risk_fraction <= Decimal('.005')
                or not 0 < self.stop_fraction < 1 or not 0 <= self.round_trip_cost_fraction < 1):
            raise ValueError('fractional policy exceeds supported explicit bounds')


def load_fractional_policy(path, *, stop_fraction):
    raw = path.read_bytes(); source = json.loads(raw, object_pairs_hook=unique_fields)
    keys = {'schema_version','maximum_position_fraction','maximum_planned_risk_fraction','round_trip_cost_fraction'}
    if set(source) != keys or source['schema_version'] != 'fractional-entry-risk-v1':
        raise ValueError('explicit fractional-entry-risk-v1 policy required')
    if any(type(source[key]) is not str for key in keys-{'schema_version'}):
        raise ValueError('explicit decimal strings required')
    policy = FractionalRiskPolicy(stop_fraction=stop_fraction, **{
        key: Decimal(source[key]) for key in keys-{'schema_version'}})
    return policy, hashlib.sha256(raw).hexdigest()


def fractional_risk_blockers(policy, *, equity, quote_notional, existing_symbol_value):
    values = (equity, quote_notional, existing_symbol_value)
    if (any(not isinstance(value, Decimal) or not value.is_finite() or value < 0 for value in values)
            or equity == 0 or quote_notional == 0):
        return ('fractional risk inputs unavailable or invalid',)
    reasons = []
    if existing_symbol_value+quote_notional > equity*policy.maximum_position_fraction:
        reasons.append('post-buy symbol exposure exceeds explicit equity fraction')
    planned_loss = quote_notional*(policy.stop_fraction+policy.round_trip_cost_fraction)
    if planned_loss > equity*policy.maximum_planned_risk_fraction:
        reasons.append('planned stop and cost loss exceeds explicit equity risk fraction')
    return tuple(reasons)
