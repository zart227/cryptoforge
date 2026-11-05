"""Persistent observed-equity peak; never initialize or reset on missing state."""
from datetime import UTC
from decimal import Decimal
import fcntl
import json

from cryptoforge.atomic_reports import write_json_report
from cryptoforge.execution_controls import unique_fields
from cryptoforge.live_learning_protocol import time


def drawdown_blockers(*, current_equity, maximum_drawdown, state_path, owner_id, now):
    if (now.tzinfo is None or not isinstance(current_equity, Decimal)
            or not current_equity.is_finite() or current_equity < 0
            or not isinstance(maximum_drawdown, Decimal) or not maximum_drawdown.is_finite()
            or not Decimal('0') < maximum_drawdown <= Decimal('.10')
            or not isinstance(owner_id, str) or len(owner_id) != 64
            or any(char not in '0123456789abcdef' for char in owner_id)):
        return ('portfolio drawdown inputs invalid; new entries paused',)
    try:
        # No automatic provisioning: a missing historical peak is unknown.
        if not state_path.is_file():
            raise ValueError('missing peak state')
        lock_path = state_path.with_name(state_path.name+'.lock')
        with lock_path.open('a') as lock:
            lock_path.chmod(0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = json.loads(state_path.read_bytes(), object_pairs_hook=unique_fields)
            if (state['schema_version'] != 'observed-portfolio-drawdown-v1' or state['owner_id'] != owner_id
                    or type(state['breach_latched']) is not bool
                    or any(type(state[key]) is not str for key in
                        ('maximum_drawdown','peak_equity','last_equity','observed_at'))
                    or Decimal(state['maximum_drawdown']) != maximum_drawdown):
                raise ValueError('incompatible peak state')
            peak = Decimal(state['peak_equity']); previous = Decimal(state['last_equity'])
            stamp = time(state['observed_at'])
            if (not peak.is_finite() or peak <= 0 or not previous.is_finite()
                    or not 0 <= previous <= peak or stamp > now):
                raise ValueError('invalid peak or observation')
            prior_breach = (peak-previous)/peak >= maximum_drawdown
            if prior_breach and not state['breach_latched']:
                raise ValueError('inconsistent breach latch')
            peak = max(peak, current_equity)
            decline = (peak-current_equity)/peak
            latched = state['breach_latched'] or decline >= maximum_drawdown
            updated = dict(state, peak_equity=format(peak, 'f'), last_equity=format(current_equity, 'f'),
                observed_at=now.astimezone(UTC).isoformat(), breach_latched=latched)
            write_json_report(state_path, updated)
            if latched:
                return ('portfolio drawdown breach latched; new entries paused pending reviewed recovery',)
            return ()
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        return ('portfolio drawdown state unavailable or invalid; new entries paused pending peak recovery',)
