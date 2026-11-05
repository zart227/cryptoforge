from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from types import SimpleNamespace

import pytest

from cryptoforge.account_verification import (AccountVerifiedOrderClient, SpotAccountPolicy,
    digest, load_account_policy, observe_account, verify_account_response)
from cryptoforge.execution_controls import OrderControlBlocked
from cryptoforge.order_submission_journal import JournaledOrderClient, OrderSubmissionJournal


NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def key_response(*, api_key='synthetic-api-key', now=NOW):
    return dict(retCode=0, time=int(now.timestamp()*1000), result=dict(apiKey=api_key, secret='',
        note='private-note-must-not-be-persisted', userID=101, parentUid='10', isMaster=False,
        readOnly=0, uta=1, type=1, isFixApi=False, ips=['192.0.2.1'],
        permissions=dict(Spot=['SpotTrade'], Wallet=[], ContractTrade=[], Derivatives=[], Options=[])))


def policy():
    return SpotAccountPolicy('101','10',('192.0.2.1',),10)


def write_policy(path):
    path.write_text(json.dumps(dict(schema_version='bybit-spot-account-policy-v1',expected_uid='101',
        expected_parent_uid='10',expected_ips=['192.0.2.1'],maximum_response_age_seconds=10)))
    return load_account_policy(path)


def verify(value, **changes):
    kwargs=dict(policy=policy(),client=SimpleNamespace(api_key='synthetic-api-key'),now=NOW)
    kwargs.update(changes)
    return verify_account_response(value,**kwargs)


def test_matching_authenticated_facts_are_projected_without_key_secret_note_or_raw_uids():
    source=key_response(); original=deepcopy(source)
    facts=verify(source)
    assert source==original
    assert facts['account_uid_matches_policy'] and facts['spot_trade_only']
    assert facts['uid_sha256']==digest(b'101')
    assert not facts['ownership_lease_upgraded'] and not facts['live_admission_granted']
    raw=json.dumps(facts)
    assert 'synthetic-api-key' not in raw and 'private-note' not in raw
    assert '"101"' not in raw and '"10"' not in raw


@pytest.mark.parametrize('field,value', [('apiKey','another-key'), ('secret','unexpected-secret'),
    ('userID',102),('userID','101'),('userID',True),('userIDInt64','102'),('parentUid','11'),
    ('parentUid',10),('isMaster',True),('isMaster','false'),('readOnly',1),('readOnly',False),
    ('uta',0),('uta',True),('type',2),('isFixApi',True),('isFixApi','false'),
    ('ips',[]),('ips',['*']),('ips',['192.0.2.2']),('ips',['192.0.2.1','192.0.2.1'])])
def test_identity_permissions_modes_and_whitelist_mismatches_fail_closed(field,value):
    response=key_response();response['result'][field]=value
    with pytest.raises(ValueError):verify(response)


@pytest.mark.parametrize('field', ['apiKey','secret','userID','parentUid','isMaster','readOnly',
    'uta','type','isFixApi','permissions','ips'])
def test_missing_original_fields_are_unknown_not_safe_defaults(field):
    response=key_response();del response['result'][field]
    with pytest.raises((ValueError,KeyError)):verify(response)


@pytest.mark.parametrize('name,values', [('Wallet',['Withdraw']),('Wallet',['AccountTransfer']),
    ('ContractTrade',['Order']),('Derivatives',['DerivativesTrade']),('Options',['OptionsTrade']),
    ('Earn',['Earn']),('FutureUnknown',['NewPermission']),('Spot',[]),('Spot',['SpotTrade','SpotTrade']),
    ('Wallet',None),('Spot','SpotTrade')])
def test_nonspot_unknown_or_malformed_permissions_cannot_be_approved(name,values):
    response=key_response();response['result']['permissions'][name]=values
    with pytest.raises(ValueError):verify(response)


def test_explicit_core_permissions_are_required_even_when_other_lists_empty():
    response=key_response();del response['result']['permissions']['Wallet']
    with pytest.raises(ValueError):verify(response)


@pytest.mark.parametrize('changes', [dict(retCode=True),dict(retCode=10003),dict(time='0'),dict(time=0),
    dict(time=int((NOW+timedelta(milliseconds=1)).timestamp()*1000)),
    dict(time=int((NOW-timedelta(seconds=11)).timestamp()*1000))])
def test_failed_stale_or_future_response_cannot_prove_account_identity(changes):
    response=key_response();response.update(changes)
    with pytest.raises(ValueError):verify(response)


@pytest.mark.parametrize('changes', [dict(expected_uid='0'),dict(expected_uid='0101'),
    dict(expected_uid=101),dict(expected_parent_uid='101'),dict(expected_ips=('0.0.0.0/0',)),
    dict(maximum_response_age_seconds=True),dict(maximum_response_age_seconds=31)])
def test_policy_requires_explicit_strict_reviewed_scope(changes):
    kwargs=dict(expected_uid='101',expected_parent_uid='10',expected_ips=('192.0.2.1',),maximum_response_age_seconds=10)
    kwargs.update(changes)
    with pytest.raises(ValueError):SpotAccountPolicy(**kwargs)


def test_policy_loader_preserves_sha_and_rejects_duplicate_or_extra_fields(tmp_path):
    path=tmp_path/'policy.json';loaded,sha=write_policy(path)
    assert loaded==policy() and sha==digest(path.read_bytes())
    source=json.loads(path.read_bytes());source['unexpected']=True;path.write_text(json.dumps(source))
    with pytest.raises(ValueError):load_account_policy(path)
    path.write_text('{"expected_uid":"101","expected_uid":"102"}')
    with pytest.raises(ValueError):load_account_policy(path)


def test_observation_uses_only_authenticated_get_and_checks_clock_after_response():
    calls=[]
    def get(path,params):
        calls.append((path,params))
        return key_response()
    client=SimpleNamespace(api_key='synthetic-api-key',_private_get=get)
    with pytest.raises(ValueError):observe_account(client,policy(),clock=lambda:NOW+timedelta(seconds=11))
    assert calls==[('/v5/user/query-api',{})]


def guard_case(tmp_path):
    path=tmp_path/'policy.json';loaded,sha=write_policy(path)
    source=key_response();sent=[]
    client=SimpleNamespace(api_key='synthetic-api-key',_private_get=lambda *a:source,
        create_spot_market_order=lambda **kw:sent.append(kw) or dict(retCode=0,result=dict(orderId='fake')))
    guard=AccountVerifiedOrderClient(client,policy=loaded,policy_path=path,policy_sha256=sha,clock=lambda:NOW)
    return guard,source,sent


def test_permissions_are_rechecked_each_buy_and_sells_do_not_depend_on_key_query(tmp_path):
    guard,source,sent=guard_case(tmp_path)
    guard.create_spot_market_order(side='Buy')
    source['result']['permissions']['Wallet']=['Withdraw']
    with pytest.raises(OrderControlBlocked):guard.create_spot_market_order(side='Buy')
    guard.client._private_get=lambda *a:pytest.fail('Sell queried entry identity')
    guard.create_spot_market_order(side='Sell')
    assert [row['side'] for row in sent]==['Buy','Sell']


def test_unknown_policy_or_midcycle_policy_change_cannot_enable_entry(tmp_path):
    guard,_,sent=guard_case(tmp_path)
    guard.policy_path.write_text('{}')
    with pytest.raises(OrderControlBlocked):guard.create_spot_market_order(side='Buy')
    assert sent==[]


def test_outage_after_prepared_intent_is_known_blocked_and_does_not_log_key(tmp_path):
    from decimal import Decimal
    guard,_,sent=guard_case(tmp_path)
    def outage(*a):raise OSError('sensitive-upstream-message synthetic-api-key')
    guard.client._private_get=outage
    journal=OrderSubmissionJournal(tmp_path/'orders.sqlite')
    with pytest.raises(OrderControlBlocked) as result:
        JournaledOrderClient(guard,journal).create_spot_market_order(
            symbol='HYPEUSDT',side='Buy',qty=Decimal('6'),order_link_id='test')
    assert 'synthetic-api-key' not in str(result.value) and sent==[]
    with sqlite3.connect(journal.path) as db:
        assert db.execute('SELECT status,last_error FROM order_submissions').fetchone()==('blocked','OrderControlBlocked')


def test_limit_buy_cannot_bypass_identity_check(tmp_path):
    guard,_,sent=guard_case(tmp_path)
    with pytest.raises(OrderControlBlocked):guard.create_spot_limit_order(side='Buy')
    assert sent==[]


def test_slow_key_query_cannot_extend_expired_runtime_approval(tmp_path):
    from test_runtime_approval import guard_case as runtime_case, BUY
    _,_,_,runtime,sent=runtime_case(tmp_path)
    path=tmp_path/'account-policy.json';loaded,sha=write_policy(path)
    clock=[NOW];runtime.clock=lambda:clock[0]
    def slow_query(*a):
        clock[0]=NOW+timedelta(hours=1)
        return key_response(api_key=runtime.client.api_key,now=clock[0])
    runtime.client._private_get=slow_query
    account=AccountVerifiedOrderClient(runtime,policy=loaded,policy_path=path,
        policy_sha256=sha,clock=lambda:clock[0])
    with pytest.raises(OrderControlBlocked,match='expired'):account.create_spot_market_order(**BUY)
    assert sent==[]
