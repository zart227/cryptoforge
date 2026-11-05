"""Threshold-invariant fitting, objective equivalence and complete dependency keys."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest
from cryptoforge import research_fit_graph as m
from cryptoforge.research_training_diagnostics import build_diagnostics


@pytest.fixture
def dataset(tmp_path):
    def row(day, minute, label, shift):
        return {'pair': 'BTC/USDT', 'open_time': f'2026-10-{day:02d}T00:{minute:02d}:00Z',
            'label_end_time': f'2026-10-{day:02d}T00:{minute+1:02d}:00Z',
            'features': [shift, 0., .01, 1., 0., .5, 0.], 'label': label}
    data = {'schema_version': m.planner.DATA_VERSION, 'target_version': 'fixed-future-return-v1',
        'feature_version': m.planner.model_training.FEATURE_VERSION, 'feature_names': list(m.planner.model_training.FEATURE_NAMES),
        'train': [row(1, 0, 0, 0.), row(1, 5, 1, .1)], 'validation': [row(2, 0, 0, 0.), row(2, 5, 1, .1)]}
    path = tmp_path/'development.json'; path.write_text(json.dumps(data)); return path


def test_existing_seven_single_parameter_configurations_need_only_four_fit_dependencies(dataset):
    graph = m.analyze(dataset); count = graph['conditional_operation_counts']
    assert count['logical_configuration_evaluations_unchanged'] == 7
    assert count['naive_long_head_fits'] == 7 and count['proposed_unique_long_head_fits'] == 4
    assert count['naive_standardizer_fits'] == 7 and count['proposed_shared_standardizer_fits'] == 1
    assert count['naive_optimizer_training_row_presentations'] == 700 and count['proposed_optimizer_training_row_presentations'] == 400
    assert count['naive_train_validation_probability_evaluations'] == 28 and count['proposed_cached_train_validation_probability_evaluations'] == 16
    baseline = [e for e in graph['logical_evaluations'] if e['configuration']['l2'] == .01]
    assert len(baseline) == 4 and len({e['fit_key'] for e in baseline}) == 1
    assert len({e['configuration_key'] for e in baseline}) == 4
    assert all(e['logical_evaluation_and_budget_charge_still_required'] for e in baseline)
    assert not graph['execution_command_available'] and not graph['ledger_mutations_or_refunds_or_new_allowance']
    assert graph['old_numeric_lifetime'] == '3/3 completed-cache-only'


def test_threshold_changes_decisions_but_not_existing_primary_Brier_or_logloss():
    source = {'partition': 'validation', 'dataset_sha256': 'a'*64, 'source_sha256': 'b'*64,
        'development_end': '2026-10-02T00:10:00Z', 'rows': [
            {'pair': 'BTC/USDT', 'open_time': '2026-10-02T00:00:00Z', 'label_end_time': '2026-10-02T00:01:00Z', 'probability': .6, 'label': 1},
            {'pair': 'BTC/USDT', 'open_time': '2026-10-02T00:05:00Z', 'label_end_time': '2026-10-02T00:06:00Z', 'probability': .9, 'label': 0}]}
    low = build_diagnostics(source, threshold=.55)['evidence']['overall']; high = build_diagnostics(source, threshold=.7)['evidence']['overall']
    assert low['brier_score'] == high['brier_score'] and low['log_loss'] == high['log_loss']
    assert low['recall'] != high['recall'] and low['precision'] != high['precision']


def test_data_or_optimization_changes_invalidate_every_reuse_key(dataset):
    original = m.analyze(dataset)
    changed = m.analyze(dataset, epochs=51)
    assert original['standardizer_key'] != changed['standardizer_key']
    assert {n['fit_key'] for n in original['fit_nodes']}.isdisjoint({n['fit_key'] for n in changed['fit_nodes']})
    data = json.loads(dataset.read_text()); data['validation'][0]['features'][0] = .01; dataset.write_text(json.dumps(data))
    changed = m.analyze(dataset)
    assert {n['fit_key'] for n in original['fit_nodes']}.isdisjoint({n['fit_key'] for n in changed['fit_nodes']})


def test_graph_and_replay_never_invoke_model_functions_worker_or_journal(dataset, tmp_path, monkeypatch):
    def forbidden(*a, **k): pytest.fail('planning cannot perform model, worker or journal action')
    for name in ('fit_standardizer', 'fit_logistic_head', 'predict_probability'):
        monkeypatch.setattr(m.planner.model_training, name, forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(m.planner, 'ResearchAttempts', forbidden)
    graph = m.prepare(tmp_path/'pack', dataset); assert m.verify(tmp_path/'pack') == graph
    assert graph['actual_model_fits_predictions_provider_requests'] == 0 and not graph['old_artifacts_or_fit_cache_reused']


@pytest.mark.parametrize('epochs', [True, 0, 101, '50'])
def test_epoch_scope_is_not_silently_changed(dataset, epochs):
    with pytest.raises(ValueError): m.analyze(dataset, epochs=epochs)


def test_source_dependency_change_refuses_reuse_without_repinning(dataset, monkeypatch):
    monkeypatch.setattr(m, 'source_profile', lambda: {**m.REVIEWED, 'model_training.py': '0'*64})
    with pytest.raises(ValueError, match='dependency_contract_changed'): m.analyze(dataset)


def test_exact_dataset_or_report_changes_are_refused(dataset, tmp_path):
    pack = tmp_path/'pack'; m.prepare(pack, dataset)
    with pytest.raises(ValueError): m.prepare(pack, dataset)
    data = json.loads(dataset.read_text()); data['train'][0]['features'][0] = .2; dataset.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='dataset_changed'): m.verify(pack)


def test_policy_and_redacted_missing_input(tmp_path, capsys):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-fit-graph-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'private-name')]) == 2
    assert 'private-name' not in capsys.readouterr().out
