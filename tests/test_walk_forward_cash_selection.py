from datetime import timedelta
import importlib.util
import json
from pathlib import Path

import pytest
from cryptoforge.walk_forward import folds
from cryptoforge.walk_forward_selection import fold_payload
from cryptoforge.walk_forward_cash_selection import cash_selection_status, freeze_cash_selection
from test_walk_forward import START


def test_observed_cash_abstention_has_no_fake_training_or_future_results(tmp_path):
    fold = folds(START, START + timedelta(days=365))[0]
    data = fold_payload(fold); path = tmp_path / 'cash.json'
    args = dict(fold=data, plan_sha256='a'*64, evidence_sha256='b'*64)
    for now in (fold.test_start-timedelta(seconds=1), fold.test_start+fold.embargo):
        with pytest.raises(ValueError, match='outside'):
            freeze_cash_selection(path, observed=now, **args)
        assert not path.exists()
    receipt = freeze_cash_selection(path, observed=fold.test_start, **args)
    assert 'trained_at' not in receipt and 'net_pnl' not in receipt
    assert not receipt['independent_profitability_established']
    assert freeze_cash_selection(path, observed=fold.test_end, **args) == receipt
    with pytest.raises(ValueError, match='differs'):
        freeze_cash_selection(path, observed=fold.test_end, **dict(args, evidence_sha256='c'*64))
    with pytest.raises(ValueError, match='unavailable'):
        freeze_cash_selection(path, observed=fold.test_start-timedelta(seconds=1), **args)
    assert cash_selection_status(data, fold.test_start) == 'ready_to_freeze'


def test_receipt_cannot_be_changed_to_live_permission(tmp_path):
    fold = folds(START, START+timedelta(days=365))[0]; path = tmp_path/'receipt.json'
    args = dict(fold=fold_payload(fold), plan_sha256='a'*64, evidence_sha256='b'*64, observed=fold.test_start)
    receipt = freeze_cash_selection(path, **args); receipt['live_promotion_allowed'] = True
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='invalid cash'):
        freeze_cash_selection(path, **args)


def test_forged_abstention_rejected_before_report_reads():
    spec = importlib.util.spec_from_file_location('cash_freezer', Path('scripts/freeze_walk_forward_cash_selection.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    import hashlib
    plan = json.dumps({'observed_at': START.isoformat()}).encode()
    evidence = json.dumps(dict(plan_sha256=hashlib.sha256(plan).hexdigest(), test_rewards_read=False,
        observed_at=START.isoformat(), winner={'threshold': '0.3'}, no_candidate_cash_only=True)).encode()
    with pytest.raises(ValueError, match='verified abstention'):
        module.verify_abstention(plan, evidence, Path('/nonexistent'))


def test_future_observation_cannot_be_replayed_as_available():
    from scripts.freeze_walk_forward_cash_selection import verify_abstention
    plan = json.dumps({'observed_at': START.isoformat()}).encode()
    evidence = json.dumps({'observed_at': (START+timedelta(hours=1)).isoformat()}).encode()
    with pytest.raises(ValueError, match='unavailable'):
        verify_abstention(plan, evidence, Path('/nonexistent'), observed=START)
