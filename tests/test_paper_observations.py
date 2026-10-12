from datetime import UTC,datetime,timedelta
import pytest
from cryptoforge.paper_observations import SharedExitObservations


def test_roles_share_signal_without_sharing_mutable_reasons():
    now=datetime(2026,12,18,tzinfo=UTC);calls=[]
    def load(pair):calls.append(pair);return True,['exit']
    shared=SharedExitObservations(load,max_age_seconds=10,clock=lambda:now)
    first=shared('AAA/USDT');first[1].clear()
    assert shared('AAA/USDT')==(True,['exit']) and calls==['AAA/USDT']
    now+=timedelta(seconds=11);shared('AAA/USDT');assert len(calls)==2
    shared('BBB/USDT');assert calls[-1]=='BBB/USDT'


def test_roles_share_failure_until_observation_expires():
    now=datetime(2026,12,18,tzinfo=UTC);calls=[]
    def load(pair):calls.append(pair);raise ConnectionError('public data unavailable')
    shared=SharedExitObservations(load,max_age_seconds=10,clock=lambda:now)
    for _ in range(3):
        with pytest.raises(ConnectionError):shared('AAA/USDT')
    assert len(calls)==1
    now+=timedelta(seconds=11)
    with pytest.raises(ConnectionError):shared('AAA/USDT')
    assert len(calls)==2


def test_slow_fetch_and_clock_rewind_cannot_extend_freshness():
    now=datetime(2026,12,18,tzinfo=UTC);calls=[]
    def slow(pair):
        nonlocal now
        calls.append(pair);now+=timedelta(seconds=11);return False,[]
    shared=SharedExitObservations(slow,max_age_seconds=10,clock=lambda:now)
    with pytest.raises(TimeoutError):shared('AAA/USDT')
    assert not shared.cache
    shared.loader=lambda pair:(False,[])
    shared('AAA/USDT');now-=timedelta(seconds=1)
    shared.loader=lambda pair:(True,['new'])
    assert shared('AAA/USDT')==(True,['new'])
