from datetime import datetime, timedelta, timezone
import copy
import json

import pytest

from cryptoforge.model_training import FEATURE_NAMES
from cryptoforge.llm_training_study import freeze_study, run_study


def inputs(tmp_path):
    def rows(day):
        start = datetime(2025, 1, day, tzinfo=timezone.utc)
        return [{'pair': 'BTC/USDT', 'open_time': (start+timedelta(minutes=5*i)).isoformat(),
            'label_end_time': (start+timedelta(minutes=5*i+1)).isoformat(),
            'features': [float(i%2)]*7, 'label': i%2} for i in range(8)]
    path = tmp_path/'development.json'
    path.write_text(json.dumps({'schema_version': 'llm-development-examples-v1',
        'target_version': 'fixed-future-return-v1', 'feature_version': 'candle-v1',
        'feature_names': list(FEATURE_NAMES), 'train': rows(1), 'validation': rows(2)}))
    proposal = {'schema_version': 'llm-training-proposal-v1', 'hypothesis_id': 'check-l2',
        'evidence_ids': ['overall'], 'parameter': 'l2', 'value': 0.1,
        'rationale': 'Check regularization.', 'expected_effect': 'Lower development loss.',
        'falsification': 'Reject if validation degrades.'}
    return path, proposal


def test_replay_has_fresh_equal_attempts_and_no_efficacy_claim(tmp_path):
    path, proposal = inputs(tmp_path)
    study = freeze_study(path, [proposal], version='synthetic-replay', epochs=3)
    directory = tmp_path/'replay'
    result = run_study(path, study, directory)
    assert result['arms']['control']['attempts'] == result['arms']['llm']['attempts'] == 2
    assert result['api_calls_during_replay'] == 0
    assert not result['independent_evidence'] and not result['profitability_evaluated']
    assert result['conclusion'] == 'development_replay_only_no_efficacy_conclusion'
    assert (directory/'result.json').stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        run_study(path, study, directory)


def test_control_order_deterministic_and_frozen(tmp_path):
    path, proposal = inputs(tmp_path)
    assert freeze_study(path, [proposal], version='v1', seed=42) == freeze_study(path, [proposal], version='v1', seed=42)
    study = freeze_study(path, [proposal], version='v1', seed=42)
    study['control'][0]['value'] = 0.123
    with pytest.raises(ValueError, match='comparison, source or dataset changed'):
        run_study(path, study, tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


@pytest.mark.parametrize('kind', ['duplicate', 'unchanged', 'history', 'unknown-evidence'])
def test_invalid_proposals_rejected_before_search(kind, tmp_path):
    path, proposal = inputs(tmp_path)
    proposals = [proposal]
    if kind == 'duplicate':
        proposals.append(copy.deepcopy(proposal))
    elif kind == 'unchanged':
        proposal['value'] = 0.01
    elif kind == 'history':
        proposal.update(parameter='lookback_candles', value=500)
    else:
        proposal['evidence_ids'] = ['test']
    with pytest.raises(ValueError):
        freeze_study(path, proposals, version='v1')


def test_study_cannot_claim_independence_or_hide_more_budget(tmp_path):
    path, proposal = inputs(tmp_path)
    study = freeze_study(path, [proposal], version='v1')
    study['independent_evidence'] = True
    with pytest.raises(ValueError, match='development replay required'):
        run_study(path, study, tmp_path/'bad')
    study['independent_evidence'] = False
    study['protocol']['maximum_per_family'] = 50
    with pytest.raises(ValueError, match='comparison, source or dataset changed'):
        run_study(path, study, tmp_path/'bad')


def test_real_pair_evidence_is_preserved_in_frozen_suggestions(tmp_path):
    path, proposal = inputs(tmp_path)
    proposal['evidence_ids'] = ['overall', 'pair:BTC/USDT']
    study = freeze_study(path, [proposal], version='pair-evidence-v1', epochs=3)
    assert study['llm'][0]['evidence_ids'] == ['overall', 'pair:BTC/USDT']
    result = run_study(path, study, tmp_path/'pair-replay')
    assert result['arms']['llm']['attempts'] == 2
