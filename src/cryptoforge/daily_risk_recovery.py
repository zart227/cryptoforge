"""Explicit same-UTC-day daily baseline transfer; never infer a new baseline."""
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

from cryptoforge.execution_controls import unique_fields


SCHEMA = 'daily-equity-backup-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require_sha(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in '0123456789abcdef' for char in value)):
        raise ValueError('explicit lowercase SHA256 required')
    return value


def utc_now(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware recovery clock required')
    return now.astimezone(UTC)


def validate_daily_state(raw, *, now):
    """Transfer only the current UTC day's original, strictly valid state."""
    now = utc_now(now)
    state = json.loads(raw, object_pairs_hook=unique_fields)
    if (not isinstance(state, dict) or set(state) - {'date', 'start_equity', 'timezone'}
            or not isinstance(state.get('date'), str)
            or not isinstance(state.get('start_equity'), str)
            or state.get('timezone', 'UTC') != 'UTC'):
        raise ValueError('invalid daily baseline schema')
    day = date.fromisoformat(state['date'])
    baseline = Decimal(state['start_equity'])
    if (day.isoformat() != state['date'] or day != now.date()
            or not baseline.is_finite() or baseline < 0):
        raise ValueError('reviewed same-UTC-day finite baseline required')
    return state


@contextmanager
def daily_state_lock(path):
    # Same stable sidecar as daily_equity_blockers; refuse concurrent rollover.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + '.lock').open('a') as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def publish_new(path, raw):
    """Atomic no-clobber publication; an existing/corrupt state is never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def create_daily_backup(*, state_path, backup_path, account_scope, reviewed_state_sha256, now):
    now = utc_now(now)
    require_sha(account_scope)
    require_sha(reviewed_state_sha256)
    state_path, backup_path = Path(state_path), Path(backup_path)
    with daily_state_lock(state_path):
        raw = state_path.read_bytes()
        if digest(raw) != reviewed_state_sha256:
            raise ValueError('baseline differs from independently reviewed state SHA256')
        validate_daily_state(raw, now=now)
        bundle = dict(schema_version=SCHEMA, account_scope=account_scope,
            captured_at=now.isoformat(), state_sha256=digest(raw), state_json=raw.decode('utf-8'),
            identity_assurance='operator_asserted_scope_not_verified_exchange_uid')
        encoded = json.dumps(bundle, sort_keys=True, allow_nan=False).encode('utf-8')
        publish_new(backup_path, encoded)
    return dict(backup_sha256=digest(encoded), state_sha256=digest(raw),
        account_scope=account_scope, live_admission_granted=False)


def restore_daily_backup(*, backup_path, state_path, account_scope, expected_backup_sha256, now):
    now = utc_now(now)
    require_sha(account_scope)
    require_sha(expected_backup_sha256)
    encoded = Path(backup_path).read_bytes()
    if digest(encoded) != expected_backup_sha256:
        raise ValueError('backup SHA256 mismatch')
    bundle = json.loads(encoded, object_pairs_hook=unique_fields)
    keys = {'schema_version', 'account_scope', 'captured_at', 'state_sha256',
        'state_json', 'identity_assurance'}
    if (not isinstance(bundle, dict) or set(bundle) != keys
            or bundle['schema_version'] != SCHEMA or bundle['account_scope'] != account_scope
            or bundle['identity_assurance'] != 'operator_asserted_scope_not_verified_exchange_uid'
            or not isinstance(bundle['state_json'], str) or not isinstance(bundle['captured_at'], str)):
        raise ValueError('incompatible backup scope or schema')
    captured = utc_now(datetime.fromisoformat(bundle['captured_at']))
    if captured > now or captured.date() != now.date():
        raise ValueError('backup must be observed in the same UTC day, not in the future')
    raw = bundle['state_json'].encode('utf-8')
    if digest(raw) != require_sha(bundle['state_sha256']):
        raise ValueError('original baseline SHA256 mismatch')
    validate_daily_state(raw, now=now)
    state_path = Path(state_path)
    with daily_state_lock(state_path):
        publish_new(state_path, raw)
    return dict(restored_state_sha256=digest(raw), backup_sha256=digest(encoded),
        account_scope=account_scope, live_admission_granted=False)
