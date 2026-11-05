"""Independent source refusal parity, exact coverage and no unnecessary LLM calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest
from test_research_cohort_http_audit import scenario, capture
from test_research_value_audit import value_base
from test_research_revision_bridge import native_fixture
from cryptoforge import research_source_diagnostics as m


def rows(count=123, *, latest='2026-10-26T10:00:00+00:00', ingested='2026-10-26T10:05:10+00:00'):
    start = datetime.fromisoformat(latest)
    return [{'open_time': (start-timedelta(minutes=5*i)).isoformat(), 'ingested_at': ingested} for i in range(count)]


def evidence(scenario):
    _, directory, native = scenario
    report = m.source.compose(directory, native); _, retained, _, _ = m.source.inspect_capture(directory)
    return retained, report


def test_exact_minimum_source_gate_never_authorizes_proposals_or_training(scenario):
    retained, audit = evidence(scenario); report = m.compose(retained, audit)
    assert report['native_examples'] == 40 and report['coverage']['minimum_satisfied'] is True
    assert report['proposal_route'] == 'review_research_protocol' and report['source_blocking_reasons'] == []
    assert report['eligible_model_parameter_proposals'] == []
    assert not report['provider_request_authorized'] and not report['training_admission_authorized']
    assert report['error_attribution']['model_prediction_quality'] == 'not_evaluated'
    assert not report['quality_status_is_current_at_verify_time']


@pytest.mark.parametrize('microseconds,stale', [(0, False), (1, True), (-1, False)])
def test_freshness_boundary_is_exact_inclusive_900_seconds(microseconds, stale):
    cutoff = datetime(2026, 10, 26, 10, 20, tzinfo=timezone.utc)+timedelta(microseconds=microseconds)
    result = m.pair_diagnostics('AERO/USDT', rows(123), cutoff.isoformat())
    assert (result['expected_native_exclusion'] == 'stale closed training source') is stale
    assert result['latest_known_closed_age_microseconds'] == 900000000+microseconds


def test_ingest_boundary_and_disjoint_reason_counts():
    cutoff = '2026-10-26T10:05:00+00:00'
    source = [
        {'open_time': '2026-10-26T10:05:00Z', 'ingested_at': cutoff},
        {'open_time': '2026-10-26T10:00:00Z', 'ingested_at': '2026-10-26T10:04:59.999999Z'},
        {'open_time': '2026-10-26T09:55:00Z', 'ingested_at': '2026-10-26T10:05:00.000001Z'},
        {'open_time': '2026-10-26T09:50:00Z', 'ingested_at': '2026-10-26T09:55:00Z'},
        {'open_time': '2026-10-26T09:45:00Z', 'ingested_at': cutoff}]
    result = m.pair_diagnostics('AERO/USDT', source, cutoff)
    assert result['eligibility'] == {'not_closed_by_cutoff': 1, 'ingested_before_close': 1, 'ingested_after_cutoff': 1, 'known_closed': 2}
    assert sum(result['eligibility'].values()) == result['rows']
    assert result['latest_known_closed_at'] == '2026-10-26T09:55:00+00:00'


@pytest.mark.parametrize('count,expected', [(0, 'no known closed source candles'), (1, 'insufficient closed history for complete labels'),
    (122, 'insufficient closed history for complete labels'), (123, None), (500, None)])
def test_complete_history_requirement_and_example_counts(count, expected):
    result = m.pair_diagnostics('AERO/USDT', rows(count), '2026-10-26T10:05:12Z')
    assert result['expected_native_exclusion'] == expected
    assert result['expected_native_examples'] == (count-122 if expected is None else 0)


def test_gap_refusal_precedes_staleness_and_short_history():
    source = rows(3); source.pop(1)
    report = m.pair_diagnostics('AERO/USDT', source, '2026-10-26T12:00:00Z')
    assert report['expected_native_exclusion'] == 'duplicate, unordered or gapped training candles'
    assert report['known_closed_missing_intervals'] == 1
    assert report['latest_known_closed_age_microseconds'] > 900000000


@pytest.mark.parametrize('change', [
    lambda a:a['native_source_admission'].update(accepted_pairs=[]),
    lambda a:a['native_source_admission'].update(coverage_fraction=True),
    lambda a:a['native_source_admission'].update(examples=True),
    lambda a:a.update(native_all_examples=True),
    lambda a:a['native_source_admission'].update(status='admitted'),
    lambda a:a['native_source_admission'].update(minimum_source_coverage=.65),
])
def test_independent_counts_cannot_be_replaced_by_loader_status_or_forged_values(scenario, change):
    retained, audit = evidence(scenario); audit = deepcopy(audit); change(audit)
    with pytest.raises(ValueError): m.compose(retained, audit)


def rewrite_capture(directory, pair, transform):
    index = m.POLICY['pairs'].index(pair); saved = json.loads((directory/'capture.json').read_text())
    name = saved['responses'][pair]['file']; values = json.loads((directory/name).read_text()); values = transform(values)
    raw = m.canonical(values).encode(); (directory/name).write_bytes(raw)
    saved['responses'][pair].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (directory/f'receipt-{index:02d}.json').write_text(m.canonical(saved['responses'][pair]))
    (directory/'capture.json').write_text(m.canonical(saved))


def test_actual_native_closed_snapshot_gap_precedence_matches_independent_diagnosis(scenario, tmp_path):
    project, original, _ = scenario; copied = tmp_path/'captures'; shutil.copytree(original, copied)
    rewrite_capture(copied, 'AERO/USDT', lambda records: [r for i, r in enumerate(records) if i != 2])
    native = m.source._native(project, copied, 'replay', tmp_path/'native.json')
    audit = m.source.compose(copied, native); _, retained, _, _ = m.source.inspect_capture(copied)
    report = m.compose(retained, audit)
    assert report['excluded_pairs'] == {'AERO/USDT': 'duplicate, unordered or gapped training candles'}
    assert report['native_examples'] == 38


def test_actual_native_65percent_source_routes_to_data_review_not_model_search(scenario, tmp_path):
    project, original, _ = scenario; copied = tmp_path/'captures'; shutil.copytree(original, copied)
    for pair in m.POLICY['pairs'][:7]:
        rewrite_capture(copied, pair, lambda records:[{**r, 'ingested_at': r['open_time']} for r in records])
    native = m.source._native(project, copied, 'replay', tmp_path/'native.json')
    audit = m.source.compose(copied, native); _, retained, _, _ = m.source.inspect_capture(copied)
    report = m.compose(retained, audit)
    assert report['coverage'] == {'accepted_pairs': 13, 'requested_pairs': 20, 'numerator': 13, 'denominator': 20,
        'minimum_numerator': 4, 'minimum_denominator': 5, 'minimum_satisfied': False}
    assert report['proposal_route'] == 'review_source_data'
    assert report['source_blocking_reasons'] == ['minimum_pair_coverage_not_met']
    assert not report['provider_request_authorized']


@pytest.mark.parametrize('delta,expected', [(3, True), (4, True), (5, False)])
def test_native_exact_pair_coverage_boundary(scenario, tmp_path, delta, expected):
    project, original, _ = scenario; copied = tmp_path/'captures'; shutil.copytree(original, copied)
    for pair in m.POLICY['pairs'][:delta]:
        rewrite_capture(copied, pair, lambda records:[])
    native = m.source._native(project, copied, 'replay', tmp_path/'native.json')
    audit = m.source.compose(copied, native); _, retained, _, _ = m.source.inspect_capture(copied)
    assert m.compose(retained, audit)['coverage']['minimum_satisfied'] is expected


def test_policy_and_redacted_error_no_child(tmp_path, capsys, monkeypatch):
    assert json.loads((Path(m.__file__).parents[2]/'config/research-source-diagnostics-v1.json').read_text()) == m.POLICY
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k:pytest.fail('read-only diagnostics cannot start child'))
    assert m.main(['verify', '--directory', str(tmp_path/'private-name')]) == 2
    assert 'private-name' not in capsys.readouterr().out
