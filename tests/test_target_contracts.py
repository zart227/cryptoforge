import pytest
from cryptoforge.target_contracts import require_artifact_target


def test_net_contract_is_explicit_and_never_migrated_from_price_values():
    target='spot-long-trade-net-v2'
    result=require_artifact_target({'config':{'target_version':target}},expected_target=target)
    assert not result['target_migration_performed'] and not result['short_labels_allowed']
    with pytest.raises(ValueError,match='migration'):
        require_artifact_target({},expected_target=target,allow_legacy_price=True)


def test_legacy_price_fallback_is_limited_to_primary_context():
    assert require_artifact_target({},expected_target='fixed-future-return-v1',allow_legacy_price=True)['legacy_primary_price_target_inferred']
    with pytest.raises(ValueError):require_artifact_target({},expected_target='fixed-future-return-v1')


def test_explicit_price_name_cannot_hide_cash_provenance():
    with pytest.raises(ValueError,match='provenance'):
        require_artifact_target({'config':{'target_version':'fixed-future-return-v1',
            'source':'observed_real_cash_recovery_memory'}},expected_target='fixed-future-return-v1')
