"""Independent identities, causal source binding, strict comparison and cleanup."""
from copy import deepcopy
from decimal import getcontext, localcontext
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import stat
import subprocess

import pytest

from cryptoforge import research_feature_oracle as m
from cryptoforge import research_feature_reference as ref
from cryptoforge.training_diagnostics import canonical, digest
from test_research_revision_bridge import native_fixture
from test_research_value_audit import value_base


def flat(price='100', volume='1'):
    return [[price, price, price, price, volume] for _ in range(120)]


def linear_rows():
    return [[str(100+i)]*4+['1'] for i in range(120)]


def test_flat_zero_denominators_have_declared_conventions():
    assert ref.reference(flat(volume='0')) == [float(v).hex() for v in (0, 0, 0, 0, 0, 1, 0)]
    assert ref.reference(flat()) == [float(v).hex() for v in (0, 0, 0, 1, 0, 1, 0)]


@pytest.mark.parametrize('period', [12, 36])
def test_ema_closed_sum_agrees_with_independently_derived_linear_identity(period):
    closes = [Fraction(100+i) for i in range(120)]
    ratio = Fraction(period-1, period+1)
    expected = 219-Fraction(period-1, 2)*(1-ratio**119)
    assert ref.weighted_ema(closes, period) == expected


def test_all_components_from_hand_derived_linear_identity():
    result = ref.reference(linear_rows())
    fast = 219-Fraction(11, 2)*(1-Fraction(11, 13)**119)
    slow = 219-Fraction(35, 2)*(1-Fraction(35, 37)**119)
    expected = [Fraction(1, 218), Fraction(3, 216), Fraction(11, 219),
                Fraction(1), (fast-slow)/219, Fraction(1), Fraction()]
    assert result == [float(value).hex() for value in expected]


def test_simple_rsi_last14_deltas_excludes_earlier_history():
    rows = flat()
    for index in range(106, 120):
        rows[index] = ['101' if index % 2 == 0 else '100']*4+['1']
    assert ref.reference(rows)[5] == .5.hex()
    rows[0] = ['1000']*4+['1']
    assert ref.reference(rows)[5] == .5.hex()
    descending = [[str(220-i)]*4+['1'] for i in range(120)]
    assert ref.reference(descending)[5] == float(0).hex()


def test_range_volume_and_body_use_their_declared_boundaries():
    rows = flat(); rows[107][1] = '1000'; rows[108][1] = '120'; rows[108][2] = '90'
    rows[99][4] = '10000'; rows[119][4] = '21'; rows[119][0] = '95'; rows[119][2] = '95'
    result = ref.reference(rows)
    assert result[2] == float(Fraction(30, 100)).hex()
    assert result[3] == float(Fraction(420, 40)).hex()
    assert result[6] == float(Fraction(5, 100)).hex()


def test_reference_does_not_depend_on_decimal_context():
    expected = ref.reference(linear_rows())
    with localcontext() as context:
        context.prec = 3
        assert ref.reference(linear_rows()) == expected
    assert getcontext().prec == 28


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-1', '1e2', '01', '0.0000000000000000001', '1'*65, 1, True, None])
def test_quote_numeric_lexeme_and_magnitude_bounds(value):
    with pytest.raises(ValueError): ref.quote(value)


@pytest.mark.parametrize('change', [
    lambda rows: rows.pop(), lambda rows: rows.append(rows[0]),
    lambda rows: rows[0].append('0'), lambda rows: rows[0].__setitem__(0, '101'),
    lambda rows: rows[0].__setitem__(4, '-1'), lambda rows: rows[0].__setitem__(3, '0'),
])
def test_invalid_windows_rejected(change):
    rows = flat(); change(rows)
    with pytest.raises(ValueError): ref.reference(rows)


@pytest.fixture(scope='module')
def oracle_base(value_base, tmp_path_factory):
    _, _, binding, source, selection, native = value_base
    directory = tmp_path_factory.mktemp('native-value-pack')/'pack'; directory.mkdir(mode=0o700)
    report = m.values.compose(binding, source, selection, m.values.TARGET, native)
    for name, value in (('policy.json', m.values.POLICY), ('binding.json', binding), ('selection.json', selection),
                        ('target.json', m.values.TARGET), ('native.json', native), ('audit.json', report)):
        m.values.files._write(directory, name, value)
    bound = m.bind(directory)
    temporary = tmp_path_factory.mktemp('independent-oracle-values')
    oracle = m._worker(bound[1], bound[2], temporary)
    return directory, bound, oracle


def test_independent_original_version_reader_matches_all_synthetic_windows(oracle_base):
    _, bound, oracle = oracle_base
    report = m.compose(*bound, oracle)
    assert report['feature_windows_checked'] == 4
    assert report['source_rows_read'] == 480
    assert report['components_checked'] == 28
    assert report['component_mismatches'] == 0
    assert report['status'] == 'reference_matches'
    for key in ('training_data_admitted', 'candidate_numeric_worker_executed', 'provider_called', 'fit_performed',
                'model_prediction_performed', 'production_promotion_authorized',
                'actual_main_trainer_source_selection_verified', 'cross_environment_qualification_complete',
                'statistical_patch_validation_complete'):
        assert report[key] is False


def test_one_ulp_disagreement_is_not_hidden(oracle_base):
    _, bound, oracle = oracle_base; oracle = deepcopy(oracle)
    number = float.fromhex(oracle['samples'][0]['feature_hex'][0])
    oracle['samples'][0]['feature_hex'][0] = math.nextafter(number, math.inf).hex()
    report = m.compose(*bound, oracle)
    assert report['component_mismatches'] == 1 and report['status'] == 'blocked'
    assert report['samples'][0]['components'][0]['exact_match'] is False


@pytest.mark.parametrize('change', [
    lambda value: value.update(trainer_or_runtime_imported=True),
    lambda value: value.update(network_request_performed=True),
    lambda value: value.update(model_prediction_performed=True),
    lambda value: value.update(fit_performed=True),
    lambda value: value.update(reference_sha256='a'*64),
    lambda value: value.update(selection_sha256='a'*64),
    lambda value: value.update(source_rows_read=True),
    lambda value: value['samples'][0].update(selected_raw_sha256='a'*64),
    lambda value: value['samples'][0].update(id=True),
    lambda value: value['samples'][0].update(feature_hex=['nan']*7),
    lambda value: value['samples'].pop(),
])
def test_whole_result_contract_tampering_refused(oracle_base, change):
    _, bound, oracle = oracle_base; oracle = deepcopy(oracle); change(oracle)
    with pytest.raises(ValueError): m.compose(*bound, oracle)


@pytest.mark.parametrize('field,value', [
    ('known_at', '2026-10-23T00:00:00Z'), ('revision_sha256', 'a'*64),
    ('symbol', 'ETHUSDT'), ('open_time', '2026-10-22T00:01:00Z'),
    ('open_time', '2026-10-22T00:00:00.001Z'),
])
def test_source_worker_rejects_changed_availability_and_identity(oracle_base, tmp_path, field, value):
    _, bound, _ = oracle_base; selection = deepcopy(bound[2]); selection[0]['features'][0][field] = value
    with pytest.raises(ValueError, match='independent_feature_worker_refused'):
        m._worker(bound[1], selection, tmp_path)


def test_worker_rejects_database_pin_change(oracle_base, tmp_path):
    _, bound, _ = oracle_base; source = {**bound[1], 'database_sha256': 'a'*64}
    with pytest.raises(ValueError, match='independent_feature_worker_refused'):
        m._worker(source, bound[2], tmp_path)


def test_missing_features_remain_null(oracle_base, tmp_path):
    _, bound, _ = oracle_base; selection = deepcopy(bound[2]); selection[0]['features'] = None
    oracle = m._worker(bound[1], selection, tmp_path)
    changed = (*bound[:2], selection, *bound[3:])
    report = m.compose(*changed, oracle)
    assert report['components_checked'] == 21
    assert oracle['samples'][0]['feature_hex'] is None
    assert report['samples'][0]['components'] is None
    oracle['samples'][0]['feature_hex'] = ['0x0.0p+0']*7
    with pytest.raises(ValueError, match='missing_source_cannot_be_invented'): m.compose(*changed, oracle)


def test_private_artifact_replay_recomputes_reference_without_native(oracle_base, tmp_path, monkeypatch):
    directory, _, _ = oracle_base
    report = m.prepare(tmp_path/'pack', directory)
    monkeypatch.setattr(m.values, '_native', lambda *_: pytest.fail('native feature functions must not rerun'))
    original = m._worker; calls = []
    def observed(*args):
        calls.append(True); return original(*args)
    monkeypatch.setattr(m, '_worker', observed)
    assert m.verify(tmp_path/'pack') == report and calls == [True]
    assert stat.S_IMODE((tmp_path/'pack').stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in (tmp_path/'pack').iterdir())
    with pytest.raises(ValueError, match='new_oracle'): m.prepare(tmp_path/'pack', directory)
    value = json.loads((tmp_path/'pack/audit.json').read_text()); value['training_data_admitted'] = True
    value['audit_sha256'] = digest({key: val for key, val in value.items() if key != 'audit_sha256'})
    (tmp_path/'pack/audit.json').write_text(canonical(value)+'\n')
    with pytest.raises(ValueError, match='independent_oracle_audit_changed'): m.verify(tmp_path/'pack')


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('fixed', 15), KeyboardInterrupt()])
def test_worker_fixed_environment_deadline_and_reap(oracle_base, tmp_path, monkeypatch, failure):
    observed = {}
    class Process:
        pid = 43210; calls = 0
        def wait(self, timeout=None):
            self.calls += 1
            if self.calls == 1: raise failure
            return 0
    process = Process()
    def popen(args, **kwargs): observed.update(args=args, **kwargs); return process
    monkeypatch.setattr(m.subprocess, 'Popen', popen)
    monkeypatch.setattr(m.os, 'killpg', lambda pid, sig: observed.update(killed=pid))
    _, bound, _ = oracle_base
    with pytest.raises(type(failure)): m._worker(bound[1], bound[2], tmp_path)
    assert process.calls == 2 and observed['killed'] == 43210
    assert observed['stdin'] == subprocess.DEVNULL and observed['start_new_session'] is True
    assert set(observed['env']) == {'PATH', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE', 'PYTHONHASHSEED', 'LANG', 'TZ'}


def test_frozen_spec_and_policy_configs():
    root = Path(m.__file__).parents[2]
    assert json.loads((root/'config/research-feature-oracle-v1.json').read_text()) == m.POLICY
    assert json.loads((root/'config/research-feature-reference-v1.json').read_text()) == ref.SPEC
    assert 'model_training' not in Path(ref.__file__).read_text()


def test_safe_cli_refusal_has_no_private_path(tmp_path, capsys):
    assert m.main(['verify', '--directory', str(tmp_path/'private-secret-path')]) == 2
    assert 'private-secret-path' not in capsys.readouterr().out
