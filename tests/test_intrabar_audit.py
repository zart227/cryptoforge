from dataclasses import replace
from datetime import UTC,datetime,timedelta
from decimal import Decimal as D
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.intrabar_audit import audit_barrier_order

START=datetime(2026,10,1,tzinfo=UTC)


def rows():
    prices=[(100,101,99,101),(101,105,100,104),(104,104,97,98),(98,100,98,99),(99,101,99,100)]
    return [CandleRow('ETH/USDT','ETHUSDT',START+timedelta(minutes=i),*(D(v) for v in p),D(20)) for i,p in enumerate(prices)]


def audit(fine):
    coarse=CandleRow('ETH/USDT','ETHUSDT',START,D(100),D(105),D(97),D(100),D(100))
    return audit_barrier_order(coarse,fine,entry_price=D(100),stop_fraction=D('.02'),target_fraction=D('.04'),as_of=START+timedelta(minutes=5))


def test_complete_fine_order_resolves_target_before_later_stop_without_changing_simulator():
    result=audit(rows())
    assert result['first_barrier']=='target' and result['raw_price']=='104.00'
    assert result['first_touch_minute']==(START+timedelta(minutes=1)).isoformat()
    assert not result['trade_policy_changed'] and not result['can_certify_real_fill']


def test_missing_minute_or_price_mismatch_preserves_adverse_unresolved_result():
    assert audit(rows()[:2]+rows()[3:])['status']=='unresolved_incomplete_fine_history'
    changed=rows();changed[1]=replace(changed[1],high=D(106))
    assert audit(changed)['status']=='unresolved_fine_coarse_price_mismatch'
    assert audit(changed)['first_barrier']=='stop'


def test_both_levels_in_one_minute_remain_unknown_and_use_stop():
    changed=rows();changed[0]=replace(changed[0],high=D(105),low=D(97))
    result=audit(changed)
    assert result['first_barrier']=='stop' and result['status']=='unresolved_same_fine_bar_adverse_stop'


def test_cached_partial_duplicate_does_not_override_the_valid_closed_minute_path():
    fine=rows();partial=replace(fine[0],high=D(105),low=D(97),cache_observed_at=START+timedelta(seconds=10))
    result=audit([partial,*fine])
    assert result['first_barrier']=='target'
    assert result['first_touch_minute']==(START+timedelta(minutes=1)).isoformat()


def test_shuffled_complete_minutes_preserve_chronological_first_touch():
    result=audit(list(reversed(rows())))
    assert result['first_barrier']=='target'
    assert result['first_touch_minute']==(START+timedelta(minutes=1)).isoformat()


def test_coarse_revision_cannot_be_used_before_it_was_observed():
    import pytest
    coarse=CandleRow('ETH/USDT','ETHUSDT',START,D(100),D(105),D(97),D(100),D(100),cache_observed_at=START+timedelta(minutes=10))
    kwargs={'entry_price':D(100),'stop_fraction':D('.02'),'target_fraction':D('.04')}
    with pytest.raises(ValueError,match='known closed'):
        audit_barrier_order(coarse,rows(),as_of=START+timedelta(minutes=5),**kwargs)
    result=audit_barrier_order(coarse,rows(),as_of=START+timedelta(minutes=11),**kwargs)
    assert result['information_available_at']==(START+timedelta(minutes=10)).isoformat()
