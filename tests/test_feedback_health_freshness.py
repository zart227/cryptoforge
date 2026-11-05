from datetime import datetime, UTC, timedelta
import pytest
from cryptoforge.live_feedback import accounting_health_verified

NOW=datetime(2026,10,14,5,tzinfo=UTC)


def health(stamp):
    return {'status':'ok','observed_at':stamp,'payload':{'accounting_version':2,'inventory_verified':True}}


@pytest.mark.parametrize('seconds',[0,1800,3600])
def test_recent_verified_journal_can_confirm_accounting(seconds):
    assert accounting_health_verified(health((NOW-timedelta(seconds=seconds)).isoformat()),observed_at=NOW)


@pytest.mark.parametrize('stamp',[(NOW-timedelta(seconds=3601)).isoformat(),
    (NOW+timedelta(seconds=1)).isoformat(),'2026-10-14T05:00:00','broken',None])
def test_stale_future_naive_or_missing_clock_cannot_confirm_accounting(stamp):
    assert not accounting_health_verified(health(stamp),observed_at=NOW)


@pytest.mark.parametrize('version',[True,'2',None,1])
def test_accounting_version_is_a_known_integer(version):
    value=health(NOW.isoformat());value['payload']['accounting_version']=version
    assert not accounting_health_verified(value,observed_at=NOW)


@pytest.mark.parametrize('payload',[['ok'],'ok',1])
def test_malformed_health_payload_is_unverified(payload):
    value=health(NOW.isoformat());value['payload']=payload
    assert not accounting_health_verified(value,observed_at=NOW)
