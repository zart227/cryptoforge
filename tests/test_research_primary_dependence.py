"""Calendar overlap and concentration are descriptive, never inferred independence."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat

import pytest
from cryptoforge import research_primary_dependence as m
from cryptoforge.research_training_diagnostics import canonical, digest


def rows(minutes=(0, 5, 10, 15, 20, 25), pairs=('AAA/USDT', 'BBB/USDT')):
    start = datetime(2026, 10, 25, tzinfo=timezone.utc)
    return [{'pair': p, 'open_time': (start+timedelta(minutes=t)).isoformat(),
        'label_end_time': (start+timedelta(minutes=t+20)).isoformat(), 'label': i % 2, 'short_label': (i+1) % 2}
        for i, t in enumerate(minutes) for p in pairs]


def test_parallel_assets_and_three_overlapping_returns_do_not_create_independent_trials():
    r = m.summarize(rows())
    assert r['nominal_examples'] == 12 and r['unique_input_anchors'] == 6 and r['pair_count'] == 2
    assert r['maximum_overlapping_time_label_windows'] == 3
    assert r['maximum_overlapping_example_label_windows'] == 6
    assert r['maximum_count_nonoverlapping_time_label_windows'] == 2
    assert r['pair_concentration']['hhi_fraction'] == ['1', '2']
    assert r['time_concentration']['hhi_fraction'] == ['1', '6']
    assert not r['nonoverlapping_count_is_independent_sample_size']
    assert not r['time_concentration']['inverse_hhi_is_statistical_effective_sample_size']


def test_touching_economic_label_windows_are_disjoint_using_reference_close_not_open():
    r = m.summarize(rows((0, 15), ('AAA/USDT',)))
    assert r['maximum_overlapping_time_label_windows'] == 1
    assert r['maximum_count_nonoverlapping_time_label_windows'] == 2
    assert r['label_return_window_seconds'] == 900


def test_gaps_and_input_order_do_not_change_descriptive_result():
    original = rows((0, 30, 60)); r = m.summarize(original)
    assert r['maximum_overlapping_time_label_windows'] == 1
    assert r['maximum_count_nonoverlapping_time_label_windows'] == 3
    assert m.summarize(list(reversed(original))) == r


def test_unbalanced_pair_coverage_and_time_concentration_are_measured_separately():
    data = rows((0, 5, 10)); data.pop()
    r = m.summarize(data)
    assert r['pair_concentration']['hhi_fraction'] == ['13', '25']
    assert r['time_concentration']['hhi_fraction'] == ['9', '25']
    assert r['examples_per_anchor_minimum'] == 1 and r['examples_per_anchor_maximum'] == 2


@pytest.mark.parametrize('change', [
    lambda r: r.append(deepcopy(r[0])), lambda r: r[0].update(label=True),
    lambda r: r[0].update(short_label=2), lambda r: r[0].update(open_time='2026-10-25T00:01:00Z'),
    lambda r: r[0].update(label_end_time='2026-10-25T00:15:00Z'),
])
def test_duplicate_malformed_labels_or_horizons_refused(change):
    data = rows(); change(data)
    with pytest.raises(ValueError): m.summarize(data)


@pytest.mark.parametrize('data', [[], None, [{}]*10001])
def test_fixed_nonempty_row_bound(data):
    with pytest.raises(ValueError): m.summarize(data)


def test_report_keeps_descriptive_counts_separate_from_effectiveN_significance_and_admission():
    data = rows(); snapshot = {'splits': {s: data for s in m.primary.SPLITS}}
    report = {'audit_sha256': 'a'*64, 'candidate_artifact_sha256': 'b'*64,
        'splits': {s: {'count': len(data)} for s in m.primary.SPLITS}}
    result = m.compose({'audit_sha256': 'a'*64}, snapshot, report)
    for k in ('statistical_effective_sample_size_estimated', 'independence_verified',
        'significance_test_or_bootstrap_performed', 'confidence_intervals_computed', 'training_data_admitted',
        'model_prediction_performed', 'fit_performed', 'provider_called', 'production_promotion_authorized'):
        assert result[k] is False
    report['splits']['test']['count'] += 1
    with pytest.raises(ValueError): m.compose({'audit_sha256': 'a'*64}, snapshot, report)


def test_private_binding_replay_and_rehashed_confidence_claim_refusal(tmp_path, monkeypatch):
    data = rows(); snapshot = {'splits': {s: data for s in m.primary.SPLITS}}
    report = {'audit_sha256': 'a'*64, 'candidate_artifact_sha256': 'b'*64,
        'splits': {s: {'count': len(data)} for s in m.primary.SPLITS}}
    bound = ({'directory': str(tmp_path/'input'), 'audit_sha256': 'a'*64}, snapshot, report)
    monkeypatch.setattr(m, 'bind', lambda *_: bound)
    result = m.prepare(tmp_path/'pack', tmp_path/'input')
    assert m.verify(tmp_path/'pack') == result
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in (tmp_path/'pack').iterdir())
    with pytest.raises(ValueError): m.prepare(tmp_path/'pack', tmp_path/'input')
    changed = json.loads((tmp_path/'pack/audit.json').read_text()); changed['confidence_intervals_computed'] = True
    changed['audit_sha256'] = digest({k: v for k, v in changed.items() if k != 'audit_sha256'})
    (tmp_path/'pack/audit.json').write_text(canonical(changed))
    with pytest.raises(ValueError): m.verify(tmp_path/'pack')


def test_fixed_config_and_safe_cli_refusal(tmp_path, capsys):
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-primary-dependence-v1.json').read_text()) == m.POLICY
    assert m.main(['verify', '--directory', str(tmp_path/'secret')]) == 2
    assert 'secret' not in capsys.readouterr().out
