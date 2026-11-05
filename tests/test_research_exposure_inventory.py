"""Retained M48/M52/M64 exposure inventory. No network, database or training."""
from copy import deepcopy
import pytest
from cryptoforge import research_exposure_inventory as inventory


ROOT = inventory.Path(__file__).parents[1]


def test_retained_manifests_are_incomplete_and_not_admitted():
    report = inventory.inventory(ROOT)
    assert report['schema_version'] == inventory.SCHEMA
    assert report['coverage_complete'] is False
    assert report['coverage']['complete'] is False
    assert report['training_admitted'] is False
    assert report['holdout_independence_attested'] is False
    assert report['independence_proven'] is False
    assert report['network_database_fit_or_provider_actions'] == 0
    assert report['coverage']['m48_native_pair_coverage'] == 0.65
    assert report['coverage']['m64_accepted_pairs'] == 13
    assert report['coverage']['m64_requested_pairs'] == 20
    assert len(report['coverage']['m64_pairs_absent_from_examples']) == 7
    assert {record['id'] for record in report['records']} == {'M48', 'M52', 'M64'}
    for record in report['records']:
        assert record['absence_of_a_flag_or_mismatch_proves_independence'] is False
        for observation in record['mismatch_observations']:
            assert observation['absence_or_zero_proves_holdout_independence'] is False
    digest = report['report_sha256']
    again = inventory.inventory(ROOT)
    assert again['report_sha256'] == digest


def test_zero_mismatch_and_missing_flag_do_not_prove_independence():
    observed = inventory._mismatch({'wire_numeric_scalar_mismatches': 0, 'independent_feature_components': 91})
    assert observed['observed'] == {'wire_numeric_scalar_mismatches': 0}
    assert observed['absence_or_zero_proves_holdout_independence'] is False
    missing = inventory._mismatch({})
    assert missing['observed'] == {}
    assert missing['absence_or_zero_proves_holdout_independence'] is False
    flags = inventory.flags_from({'independent_feature_components': 91, 'independent_label_windows': 13})
    assert all(flag['present'] is False or flag['value'] is False for flag in flags)
    inventory.reject_admitted_flags([{'id': 'synthetic', 'flags': flags}])


@pytest.mark.parametrize('key', sorted(inventory.ADMISSION_KEYS | inventory.INDEPENDENCE_KEYS))
def test_true_admission_or_independence_flag_is_rejected(key):
    flags = inventory.flags_from({key: True})
    with pytest.raises(ValueError, match='reviewed_exposure_admits_training_or_independence'):
        inventory.reject_admitted_flags([{'id': 'synthetic', 'flags': flags}])


def test_false_flags_remain_readable():
    flags = inventory.flags_from({'training_admitted': False, 'holdout_independence_attested': False})
    inventory.reject_admitted_flags([{'id': 'synthetic', 'flags': flags}])
    present = {flag['key']: flag for flag in flags if flag['present']}
    assert present['training_admitted']['value'] is False
    assert present['holdout_independence_attested']['value'] is False


def test_non_boolean_admission_flag_is_rejected():
    with pytest.raises(ValueError, match='boolean exposure flag required'):
        inventory.flags_from({'training_admitted': 1})


def test_inventory_rejects_a_tampered_true_flag(tmp_path, monkeypatch):
    source = inventory.inventory(ROOT)
    assert source['training_admitted'] is False
    relative = inventory.BINDINGS[2]['companions'][1]
    original = inventory._load(ROOT, relative)
    tampered = deepcopy(original[0])
    tampered['training_admission_enabled'] = True

    def load(root, path):
        if path == relative:
            return tampered, 'tampered'
        return original_load(root, path)

    original_load = inventory._load
    monkeypatch.setattr(inventory, '_load', load)
    with pytest.raises(ValueError, match='reviewed_exposure_admits_training_or_independence'):
        inventory.inventory(ROOT)
