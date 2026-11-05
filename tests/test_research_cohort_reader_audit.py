"""Actual reader/loader functions over saved rows keep late replay distinct from live service parity."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import subprocess

import pytest
from test_research_local_cohort_audit import base
from cryptoforge import research_cohort_reader_audit as m
from cryptoforge.training_diagnostics import timestamp


@pytest.fixture(scope='module')
def scenario(base):
    plan, sources = deepcopy(base); late = deepcopy(sources[1])
    late['client_observed_at'] = (timestamp(plan['label_information_end'])+timedelta(minutes=1)).isoformat()
    for source in sources:
        source['rows'] = [r for r in source['rows'] if timestamp(r['open_time']) < timestamp(plan['decision_anchor'])]
    _, selected = m.late.select(plan, sources, late)
    packet = {'wire_kind': m.POLICY['wire_kind'], 'pairs': plan['pairs'], 'as_of': late['client_observed_at'],
        'anchor': plan['decision_anchor'], 'rows': [{k:r[k] for k in m.FIELDS} for r in late['rows']]}
    return plan, packet, selected


@pytest.fixture(scope='module')
def native_case(scenario, tmp_path_factory):
    plan, packet, selected = scenario
    native = m._native(Path(plan['project']), packet, tmp_path_factory.mktemp('cohort-reader-native'))
    return plan, packet, selected, native


def test_actual_reader_and_loader_values_match_original_features_and_late_labels_without_real_transport(native_case):
    _, packet, selected, native = native_case
    result = m.compose({}, packet, selected, native)
    assert result['status'] == 'native_loader_values_compatible_on_available_original_windows'
    assert result['scalar_fields_checked'] == 1230 and result['scalar_mismatch_count'] == 0
    assert result['independent_feature_components'] == 14 and result['independent_label_windows'] == 2
    assert result['native_all_examples'] == 2 and result['native_source_admission']['coverage_fraction'] == 1
    assert result['all_native_examples_equal_exact_numeric_parser']
    for k in ('original_HTTP_wire_captured', 'production_service_reader_configuration_qualified',
              'late_data_proves_original_deadline_availability', 'model_fit_or_prediction_performed',
              'training_data_admitted', 'new_numerical_allowance_created'):
        assert result[k] is False
    assert result['actual_local_REST_or_SQL_requests'] == 0


def test_numeric_wire_precision_loss_is_counted_even_when_feature_value_does_not_change(scenario, tmp_path):
    plan, packet, selected = deepcopy(scenario); packet['rows'][0]['volume'] = '12345678901234.123456789012'
    native = m._native(Path(plan['project']), packet, tmp_path)
    assert native['scalar_mismatch_count'] == 1 and native['scalar_mismatch_examples'][0]['field'] == 'volume'
    report = m.compose({}, packet, selected, native)
    assert report['status'] == 'blocked'


def test_gap_before_selected_window_excludes_pair_under_real_full_history_loader(scenario, tmp_path):
    plan, packet, selected = deepcopy(scenario); older = deepcopy(packet['rows'][0])
    older['open_time'] = (timestamp(older['open_time'])-timedelta(minutes=20)).isoformat();packet['rows'].append(older)
    native = m._native(Path(plan['project']), packet, tmp_path);report = m.compose({}, packet, selected, native)
    assert native['native']['source_admission']['coverage_fraction'] == .5
    assert report['original_comparable_windows'] == 2 and report['native_missing_comparable_windows'] == 1
    assert report['status'] == 'blocked' and report['independent_label_windows'] == 1


def test_late_cache_cannot_recover_original_missing_features(scenario, tmp_path):
    plan, packet, selected = deepcopy(scenario); selected[0]['features'] = None; selected[0]['missing_feature_candles'] = 1
    native = m._native(Path(plan['project']), packet, tmp_path);report = m.compose({}, packet, selected, native)
    assert report['original_comparable_windows'] == report['independent_label_windows'] == 1
    assert report['samples'][0]['late_native_loader_example_available']
    assert not report['samples'][0]['original_predecision_feature_window_available']
    assert not report['samples'][0]['original_features_recovered_from_late_source']


@pytest.mark.parametrize('change', [
    lambda n:n.update(fit_or_prediction_performed=True), lambda n:n.update(actual_HTTP_or_database_requests=True),
    lambda n:n.update(original_HTTP_wire_captured=True), lambda n:n.update(scalar_fields_checked=True),
    lambda n:n.update(real_credentials_loaded=True), lambda n:n.update(packet_sha256='0'*64),
])
def test_worker_cannot_escalate_scope_identity_or_hide_row_counts(native_case, change):
    _, packet, selected, native = deepcopy(native_case);change(native)
    with pytest.raises(ValueError):m.compose({}, packet, selected, native)


def test_native_label_mismatch_is_recorded_as_failure(native_case):
    _, packet, selected, native = deepcopy(native_case);native['native']['selected'][0]['example']['long_label'] ^= 1
    report=m.compose({},packet,selected,native)
    assert report['status']=='blocked' and report['sample_value_mismatches']==1


def test_offline_verify_does_not_reexecute_reader_worker(native_case,tmp_path,monkeypatch):
    plan,packet,selected,native=native_case
    bound=({'project':plan['project'],'late_pack_directory':str(tmp_path)},packet,selected)
    monkeypatch.setattr(m,'load',lambda *_:bound);monkeypatch.setattr(m,'_native',lambda *_:native)
    report=m.prepare(tmp_path/'pack',tmp_path)
    monkeypatch.setattr(m,'_native',lambda *_:pytest.fail('offline verify cannot invoke worker'))
    assert m.verify(tmp_path/'pack')==report


@pytest.mark.parametrize('interrupt',[False,True])
def test_fixed_reader_worker_timeout_or_interrupt_kills_group_and_reaps(tmp_path,monkeypatch,interrupt):
    observed={}
    class Process:
        pid=34567;calls=0
        def wait(self,timeout=None):
            self.calls+=1
            if self.calls==1:
                if interrupt:raise KeyboardInterrupt()
                raise subprocess.TimeoutExpired('fixed',25)
            return 0
    process=Process()
    monkeypatch.setattr(m.subprocess,'Popen',lambda a,**kw:observed.update(args=a,**kw)or process)
    monkeypatch.setattr(m.os,'killpg',lambda pid,sig:observed.update(killed=pid))
    with pytest.raises(KeyboardInterrupt if interrupt else subprocess.TimeoutExpired):m._native(Path('/tmp'),{},tmp_path)
    assert observed['killed']==34567 and process.calls==2 and observed['start_new_session']


def test_policy_and_safe_missing_input(tmp_path,capsys,monkeypatch):
    root=Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-cohort-reader-v1.json').read_text())==m.POLICY
    assert m.main(['verify','--directory',str(tmp_path/'secret')])==2
    assert 'secret'not in capsys.readouterr().out
    monkeypatch.setitem(m.POLICY,'actual_HTTP_or_SQL_enabled',True)
    with pytest.raises(ValueError):m._guard()
