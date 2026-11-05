"""A logical fit must not hide optimizer heads or create a new numerical allowance."""
from pathlib import Path
import json

import pytest
from cryptoforge import research_training_cost as m


def test_real_saved_primary_counts_expand_to_four_heads_and_separate_probability_passes():
    r = m.estimate({'train': 5180, 'validation': 1060, 'test': 1140}, 450)
    single = r['single_bundle']
    assert single['optimizer_head_fits'] == 4 and single['train_standardizer_fits'] == 1
    assert single['optimizer_training_row_presentations_and_sigmoid_evaluations'] == 9324000
    assert single['validation_selection_probability_evaluations'] == 3180
    assert single['selected_long_short_split_metric_probability_evaluations'] == 14760
    assert single['selected_long_short_diagnostic_probability_evaluations'] == 14760
    assert single['probability_function_calls_outside_optimization'] == 32700
    assert not r['elapsed_time_memory_energy_or_actual_consumption_measured']
    assert not r['promotion_incumbent_evaluation_data_preparation_and_provider_work_included']
    assert not r['training_or_prediction_executed_to_estimate']


def test_seven_bundle_draft_is_arithmetic_only_with_old_history_unchanged():
    work = m.estimate({'train': 5180, 'validation': 1060, 'test': 1140}, 450, logical_bundles=7)
    r = m.proposal(work)
    assert work['expanded']['optimizer_head_fits'] == 28
    assert work['expanded']['optimizer_training_row_presentations_and_sigmoid_evaluations'] == 65268000
    assert work['expanded']['probability_function_calls_outside_optimization'] == 228900
    assert r['status'] == 'review_only_not_approved' and len(r['unknown_or_unapproved']) == 9
    for k in ('new_fit_or_prediction_or_provider_allowance_created', 'old_numeric_ledger_or_caps_may_change',
              'historical_expenses_may_be_refunded', 'operational_command_available', 'production_promotion_authorized'):
        assert r[k] is False
    assert r['old_numeric_lifetime'] == '3/3 completed-cache-only'


@pytest.mark.parametrize('counts,epochs,bundles', [
    ({'train': True, 'validation': 1, 'test': 1}, 1, 1),
    ({'train': 0, 'validation': 1, 'test': 1}, 1, 1),
    ({'train': 10001, 'validation': 1, 'test': 1}, 1, 1),
    ({'train': 1, 'validation': 1}, 1, 1),
    ({'train': 1, 'validation': 1, 'test': 1}, True, 1),
    ({'train': 1, 'validation': 1, 'test': 1}, 10001, 1),
    ({'train': 1, 'validation': 1, 'test': 1}, 1, True),
    ({'train': 1, 'validation': 1, 'test': 1}, 1, 101),
])
def test_unknown_empty_noninteger_or_unbounded_work_count_refused(counts, epochs, bundles):
    with pytest.raises(ValueError): m.estimate(counts, epochs, logical_bundles=bundles)


@pytest.mark.parametrize('source', ['', 'raise RuntimeError("must never execute")', 'import os; os.abort()', ' '*131073])
def test_unreviewed_or_hostile_source_is_never_executed(source):
    with pytest.raises(ValueError): m.inspect_source(source)


def test_policy_changes_require_review_and_missing_cli_does_not_expose_path(tmp_path, monkeypatch, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-primary-training-cost-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out
    monkeypatch.setitem(m.POLICY, 'long_l2_trials', [0.0])
    with pytest.raises(ValueError): m.estimate({'train': 1, 'validation': 1, 'test': 1}, 1)
