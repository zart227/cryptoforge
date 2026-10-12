from dataclasses import replace
from datetime import UTC,datetime
import pytest

from cryptoforge.instrument_history import InstrumentEvent,state_at


def event(**kwargs):
    base=InstrumentEvent('BTCUSDT','rule_change','2025-01-21T08:00:00+00:00',
        '2025-01-06T14:09:21+00:00','https://announcements.bybit.com/en/article/test/',
        'a'*64,{'minimum_quantity':'0.000011','minimum_order_value_api':'5'})
    return replace(base,**kwargs)


def test_rules_never_backdate_or_invent_quantity_step():
    change=event();before=state_at([change],'BTCUSDT',datetime(2025,1,20,tzinfo=UTC))
    assert before['rules']=={}
    after=state_at([change],'BTCUSDT',datetime(2025,1,22,tzinfo=UTC))
    assert after['rules']['minimum_quantity']=='0.000011'
    assert 'quantity_step' in after['missing_rule_fields']
    assert after['can_certify_historical_execution'] is False
    late=replace(change,announced_at='2025-02-01T00:00:00+00:00')
    assert state_at([late],'BTCUSDT',datetime(2025,1,22,tzinfo=UTC))['rules']=={}


def test_delisting_boundary_and_later_relisting():
    listing=event(kind='listing',values={})
    delisting=event(kind='delisting',effective_at='2026-05-28T08:00:00+00:00',
                    announced_at='2026-05-22T00:00:00+00:00',values={})
    before=state_at([listing,delisting],'BTCUSDT',datetime(2026,5,28,7,59,tzinfo=UTC))
    assert before['known_delisting_blocks_entry'] is False
    after=state_at([listing,delisting],'BTCUSDT',datetime(2026,5,28,8,tzinfo=UTC))
    assert after['known_delisting_blocks_entry'] is True
    relist=replace(listing,effective_at='2026-06-01T00:00:00+00:00',announced_at='2026-05-30T00:00:00+00:00')
    assert not state_at([listing,delisting,relist],'BTCUSDT',datetime(2026,6,2,tzinfo=UTC))['known_delisting_blocks_entry']


@pytest.mark.parametrize('change',[{'market':'linear'},{'venue':'bybit_eu'},
 {'source_url':'https://announcements.bybit.global/en-EU/article/test/'},
 {'values':{'quantity_step':'-1'}},{'announced_at':'2025-01-06'}])
def test_mixed_markets_and_invalid_evidence_rejected(change):
    with pytest.raises(ValueError):event(**change).validate()


def test_suspension_blocks_only_after_observation_until_explicit_relisting():
    suspend=event(kind='suspension_observation',values={},
        effective_at='2025-11-22T23:47:45+00:00',announced_at='2025-11-22T23:47:45+00:00')
    before=state_at([suspend],'BTCUSDT',datetime(2025,11,22,23,47,44,tzinfo=UTC))
    assert not before['known_unavailable_blocks_entry']
    observed=state_at([suspend],'BTCUSDT',datetime(2025,11,23,tzinfo=UTC))
    assert observed['known_suspension_blocks_entry'] and observed['known_unavailable_blocks_entry']
    generic=event(kind='availability_observation',values={},
        effective_at='2025-11-24T00:00:00+00:00',announced_at='2025-11-24T00:00:00+00:00')
    assert state_at([suspend,generic],'BTCUSDT',datetime(2025,11,25,tzinfo=UTC))['known_unavailable_blocks_entry']
    relist=event(kind='listing',values={},effective_at='2025-11-26T00:00:00+00:00',
        announced_at='2025-11-25T00:00:00+00:00')
    assert not state_at([suspend,relist],'BTCUSDT',datetime(2025,11,27,tzinfo=UTC))['known_unavailable_blocks_entry']


def minimum_table(rows):
    headers=[['','Adjusted Minimum Single Order Value/Quantity','','','',''],
             ['','Min. Single Order Qty','','Min. Single Order Value','',''],
             ['Spot/Trading Pair','Before','Adjusted','Before','Adjusted for Non-API Users','Adjusted for API Users']]
    return {'content_html':'<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in headers+rows)+'</table>'}


def test_baseline_keeps_api_minimum_distinct_and_never_infers_step():
    from cryptoforge.instrument_history import minimum_rule_table
    result=minimum_rule_table(minimum_table([['AAAUSDT','10','12','1','2','5'],['ETHMNT','1','1','1','1','1']]))
    assert len(result)==1 and result[0]['values']=={
        'minimum_quantity':'12','minimum_order_value_non_api':'2','minimum_order_value_api':'5'}
    assert 'quantity_step' not in result[0]['values']


def test_duplicate_or_shifted_baseline_columns_are_rejected():
    from cryptoforge.instrument_history import minimum_rule_table
    row=['AAAUSDT','10','12','1','2','5']
    with pytest.raises(ValueError,match='duplicate'):
        minimum_rule_table(minimum_table([row,row]))
    with pytest.raises(ValueError,match='headers'):
        minimum_rule_table({'content_html':minimum_table([row])['content_html'].replace('Adjusted for API Users','Unknown')})
