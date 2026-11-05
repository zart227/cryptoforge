import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from scripts.reconcile_exchange_history import reconcile
from test_live_trade_journal import fill


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('CRYPTOFORGE_DATA_DIR', str(tmp_path))
    key = 'test-key'
    cache = tmp_path / ('live-journal-' + hashlib.sha256(key.encode()).hexdigest()[:16] + '.sqlite')
    buy, sell = fill('b', 'Buy', '1', '100'), fill('s', 'Sell', '1', '101', time=2000)
    with sqlite3.connect(cache) as db:
        db.execute('create table executions(exec_id text primary key,payload text)')
        db.execute('create table journal_state(id integer,start_ms integer,cursor_ms integer)')
        db.execute('insert into journal_state values(1,0,3000)')
        db.executemany('insert into executions values(?,?)', [(r['execId'], json.dumps(r)) for r in [buy, sell]])
    client = Mock(api_key=key)
    client.get_spot_executions.return_value = [buy, sell]
    client.get_unified_transactions.return_value = [dict(id='tx', currency='ETH', type='TRADE',
                                                        transactionTime='1000', cashBalance='1', change='1')]
    client.get_small_conversion_history.return_value = []
    client.get_unified_wallet_coins_for.return_value = [dict(coin='ETH', walletBalance='0')]
    return client, cache, tmp_path/'evidence'


def test_fresh_history_and_wallet_without_changing_source(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    before = cache.read_bytes()
    report = reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    assert report['status'] == 'reconciled'
    assert report['net_pnl_quote'] == '1'
    assert report['new_execution_ids'] == report['missing_cached_execution_ids'] == []
    assert cache.read_bytes() == before
    assert not report['remote_writes'] and not report['historical_completeness_certified']
    client.get_spot_executions.assert_called_once_with(start_ms=0, end_ms=3000)
    assert not client.create_spot_market_order.called
    with pytest.raises(ValueError, match='new evidence'):
        reconcile(client, cache, output)


def test_empty_exchange_response_does_not_certify_or_erase_cache(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.get_spot_executions.return_value = []
    report = reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    assert report['status'] == 'discrepancy'
    assert report['missing_cached_execution_ids'] == ['b', 's']
    with sqlite3.connect(cache) as db:
        assert db.execute('select count(*) from executions').fetchone()[0] == 2


def test_partial_fetch_preserves_evidence_and_incomplete_status(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.get_unified_transactions.side_effect = TimeoutError('secret transport details')
    with pytest.raises(TimeoutError):
        reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    report = json.loads((output/'report.json').read_text())
    assert report['status'] == 'incomplete'
    assert report['error_type'] == 'TimeoutError'
    assert 'secret' not in (output/'report.json').read_text()
    assert len(json.loads((output/'inputs.json').read_text())['windows'][0]['executions']) == 2


def test_changed_fill_cannot_pass_with_matching_wallet(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.get_spot_executions.return_value[0]['execPrice'] = '99'
    with pytest.raises(ValueError):
        reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    assert json.loads((output/'report.json').read_text())['status'] == 'incomplete'


def test_seven_day_windows_have_no_gaps(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.get_spot_executions.side_effect = [client.get_spot_executions.return_value, []]
    reconcile(client, cache, output, now=datetime.fromtimestamp(8*86400, UTC))
    assert [c.kwargs for c in client.get_spot_executions.call_args_list] == [
        dict(start_ms=0, end_ms=7*86400000-1), dict(start_ms=7*86400000, end_ms=8*86400000)]


def test_foreign_account_cache_rejected_before_network(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.api_key = 'other-key'
    with pytest.raises(ValueError, match='API key'):
        reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    assert not client.get_spot_executions.called
    assert not output.exists()


def test_current_wallet_mismatch_is_a_discrepancy(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.get_unified_wallet_coins_for.return_value = [dict(coin='ETH', walletBalance='1')]
    report = reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    assert report['status'] == 'discrepancy'
    assert not report['inventory']['consistent']


def test_nontrade_movement_cannot_be_hidden_by_matching_wallet(tmp_path, monkeypatch):
    client, cache, output = setup(tmp_path, monkeypatch)
    client.get_unified_transactions.return_value.append(dict(id='transfer', currency='ETH',
        type='TRANSFER_IN', transactionTime='2500', change='1', cashBalance='1'))
    report = reconcile(client, cache, output, now=datetime.fromtimestamp(3, UTC))
    assert report['inventory']['consistent']
    assert report['status'] == 'discrepancy'
    assert report['unmodeled_movement_ids'] == ['transfer']
