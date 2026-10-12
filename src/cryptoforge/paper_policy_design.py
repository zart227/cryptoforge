"""Validate execution design before its irreversible observed registration."""
from decimal import Decimal
from cryptoforge.paper_wallet import PaperConfig


def validate_execution_design(policy):
    config=PaperConfig(**policy['wallet'])
    stop=Decimal(str(policy['exits']['stop_fraction']))
    if not stop.is_finite() or stop!=config.entry_stop_reserve_fraction:
        raise ValueError('stop and entry liquidation reserve must match')
    values=[policy['exits']['maximum_hold_seconds'],policy['runtime']['poll_seconds'],
        policy['runtime']['maximum_new_signals_per_tick'],policy['runtime']['wall_budget_seconds']]
    if any(type(value) is not int or value<1 for value in values):
        raise ValueError('paper timing and resource counts must be positive integers')
    if not policy['runtime']['poll_seconds']<config.signal_expiry_seconds:
        raise ValueError('paper polling must precede signal expiry')
    if type(policy['exits'].get('shared_exit_signal')) is not bool:
        raise ValueError('explicit shared exit flag required')
    if policy.get('live_promotion_allowed') is not False or policy.get('source_scope')!='approved_baseline_buy_opportunity_stream_only':
        raise ValueError('isolated baseline paper source scope required')
    return config
