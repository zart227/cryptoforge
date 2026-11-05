from copy import deepcopy
import hashlib

import pytest
from cryptoforge.legacy_decision_overwrite import diagnose_case


def evidence(*, legacy=False):
    pair='ETH/USDT';candle='2026-10-07T17:15:00+00:00'
    def link(value):
        digest=hashlib.sha256(value.encode()).hexdigest()
        return 'cf-'+digest[:28] if legacy else 'cf-owner123-'+digest[:20]
    return {'case': {'pair':pair,'exit_order':'123','closed_at':'2026-10-07T17:17:26+00:00','net_return_pct':'-1'},
            'exchange_order_response': {'result': {'list': [
                {'orderId':'123','side':'Sell','symbol':'ETHUSDT','orderLinkId':link(f'{pair}:exit:{candle}')}]}},
            'nearby_decisions': [{'pair':pair,'mode':'live','decision':'hold',
                'features':{'latest_open_time':candle,'order':{}},'reasons':['ignored_dust=0.1'],
                'idempotency_key':link(f'{pair}:{candle}'),
                'created_at':'2026-10-07T17:17:26.2+00:00','decided_at':'2026-10-07T17:22:00+00:00'}]}


@pytest.mark.parametrize('legacy',[False,True])
def test_exact_legacy_candle_collision_does_not_recover_reasons(legacy):
    result=diagnose_case(evidence(legacy=legacy))
    assert result['exact_exit_candle_hash_match']
    assert result['created_minus_execution_seconds']==.2
    assert not result['original_exit_reasons_recovered']
    assert not result['surviving_reasons_are_exit_reasons']


@pytest.mark.parametrize('mutation',['foreign_key','foreign_order','other_candle','earlier_record','order_context_present'])
def test_nearby_time_alone_never_proves_collision(mutation):
    raw=deepcopy(evidence());row=raw['nearby_decisions'][0]
    if mutation=='foreign_key':row['idempotency_key']='cf-other-key'
    elif mutation=='foreign_order':raw['exchange_order_response']['result']['list'][0]['orderId']='456'
    elif mutation=='other_candle':row['features']['latest_open_time']='2026-10-07T17:10:00+00:00'
    elif mutation=='earlier_record':row['decided_at']='2026-10-07T17:16:00+00:00'
    else:row['features']['order']={'result':{'orderId':'456'}}
    with pytest.raises(ValueError):diagnose_case(raw)
