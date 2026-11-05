import json
import sqlite3
from unittest.mock import Mock
import pytest
from scripts.audit_cached_wallet import audit
from test_live_trade_journal import fill
from cryptoforge.execution_market_evidence import _load
from scripts.replay_wallet_audit import replay


def test_current_zero_wallet_is_captured_without_certifying_cached_history(tmp_path):
    cache=tmp_path/'cache.sqlite';output=tmp_path/'audit.json'
    fills=[fill('b','Buy','1','100'),fill('s','Sell','1','101',time=2000)]
    tx={'currency':'ETH','transactionTime':'1000','id':'t','cashBalance':'1','change':'1'}
    with sqlite3.connect(cache) as db:
        db.execute('create table executions(exec_id text primary key,payload text)')
        db.execute('create table account_transactions(payload text)')
        db.executemany('insert into executions values(?,?)',[(row['execId'],json.dumps(row)) for row in fills])
        db.execute('insert into account_transactions values(?)',(json.dumps(tx),))
    client=Mock(api_key='test-account')
    client.get_unified_wallet_coins_for.return_value=[{'coin':'ETH','walletBalance':'0'}]
    report=audit(client,cache,output)
    client.get_unified_wallet_coins_for.assert_called_once_with(['ETH'])
    assert report['inventory_audit']['consistent']
    inputs=_load(report['input_reference'])
    assert inputs['requested_coins']==['ETH']
    assert inputs['normalized_wallet_coins'][0]['walletBalance']=='0'
    assert not report['cached_history_freshness_verified']
    assert not report['historical_fills_complete_certified']
    before=output.read_bytes()
    with pytest.raises(ValueError,match='immutable'):
        audit(client,cache,output)
    assert output.read_bytes()==before
    assert client.get_unified_wallet_coins_for.call_count==1
    assert replay(output)['replay_matches']
    modified=json.loads(output.read_bytes())
    modified['inventory_audit']['consistent']=False
    output.write_text(json.dumps(modified))
    with pytest.raises(ValueError,match='differs from source replay'):
        replay(output)
