"""Explicit abstention receipts, without inventing a trained cash model."""
from datetime import timedelta
import json
import os
import tempfile

from cryptoforge.live_learning_protocol import time
from cryptoforge.walk_forward import Fold, validate_fold


def cash_selection_status(fold, observed):
    parsed = Fold(**{key: time(fold[key]) for key in (
        'train_start', 'train_end', 'validation_start', 'validation_end', 'test_start', 'test_end')},
        embargo=timedelta(seconds=fold['embargo']))
    validate_fold(parsed)
    if observed.tzinfo is None:
        raise ValueError('aware observation required')
    if observed < parsed.test_start:
        return 'waiting_selection_window'
    if observed >= parsed.test_start + parsed.embargo:
        return 'selection_deadline_missed'
    return 'ready_to_freeze'


def freeze_cash_selection(path, *, fold, observed, plan_sha256, evidence_sha256):
    """Caller must first revalidate the complete registered validation grid."""
    for digest in (plan_sha256, evidence_sha256):
        if len(digest) != 64 or any(char not in '0123456789abcdef' for char in digest):
            raise ValueError('SHA256 identity required')
    identity = dict(fold=fold, plan_sha256=plan_sha256, evidence_sha256=evidence_sha256)
    if path.exists():
        receipt = json.loads(path.read_bytes())
        if any(receipt.get(key) != value for key, value in identity.items()):
            raise ValueError('immutable cash selection differs')
        stamp = time(receipt['observed_at'])
        if stamp > observed or cash_selection_status(fold, stamp) != 'ready_to_freeze':
            raise ValueError('unavailable observed selection')
        if (receipt.get('schema_version') != 'walk-forward-cash-selection-v1'
                or receipt.get('policy') != 'no_candidate_cash_only'
                or receipt.get('live_promotion_allowed') is not False
                or receipt.get('independent_profitability_established') is not False):
            raise ValueError('invalid cash selection receipt')
        return receipt
    if cash_selection_status(fold, observed) != 'ready_to_freeze':
        raise ValueError('outside observed selection window')
    receipt = dict(identity, schema_version='walk-forward-cash-selection-v1',
        observed_at=observed.isoformat(), policy='no_candidate_cash_only',
        independent_profitability_established=False, live_promotion_allowed=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Link the fully flushed private file exclusively: a crash cannot expose a
    # truncated receipt, and concurrent runs cannot replace an observed choice.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
            temporary = stream.name
            json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return freeze_cash_selection(path, fold=fold, observed=observed,
                plan_sha256=plan_sha256, evidence_sha256=evidence_sha256)
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return receipt
