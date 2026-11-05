"""Operator order switches, reread at submission rather than cached per cycle."""
import json


class OrderControlBlocked(RuntimeError):
    """Local guard rejected the order before any exchange submit."""


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate operator control field')
        result[key] = value
    return result


def control_blockers(path, side):
    if side not in {'Buy', 'Sell'}:
        return ('invalid order side',)
    try:
        state = json.loads(path.read_bytes(), object_pairs_hook=unique_fields)
        if (not isinstance(state, dict) or state.get('schema_version') != 'executor-controls-v1'
                or any(type(state.get(key)) is not bool for key in ('kill_switch', 'no_new_entry'))):
            raise ValueError('invalid controls')
    except (OSError, ValueError, TypeError):
        return ('operator controls unavailable or invalid; order submission paused',)
    if state['kill_switch']:
        return ('operator kill switch active; all new order submissions paused',)
    if side == 'Buy' and state['no_new_entry']:
        return ('operator no-new-entry active; buys paused',)
    return ()


class ControlledOrderClient:
    def __init__(self, client, path):
        self.client, self.path = client, path

    def __getattr__(self, name):
        return getattr(self.client, name)

    def _submit(self, method, intent):
        blockers = control_blockers(self.path, intent.get('side'))
        if blockers:
            raise OrderControlBlocked('; '.join(blockers))
        return getattr(self.client, method)(**intent)

    def create_spot_market_order(self, **intent):
        return self._submit('create_spot_market_order', intent)

    def create_spot_limit_order(self, **intent):
        return self._submit('create_spot_limit_order', intent)
