from unittest.mock import Mock
from scripts.analyze_live_feedback import audit_tracked_inventory
from test_live_trade_journal import fill


def test_feedback_requests_explicit_tracked_coins_including_zero_balances():
    client=Mock()
    client.get_unified_wallet_coins_for.return_value=[{'coin':'ETH','walletBalance':'0'}]
    fills=[fill('b','Buy','1','100'),fill('s','Sell','1','101',time=2000)]
    transactions=[{'currency':'ETH','transactionTime':'1000','id':'t','cashBalance':'1','change':'1'}]
    report=audit_tracked_inventory(client,fills,transactions)
    client.get_unified_wallet_coins_for.assert_called_once_with(['ETH'])
    client.get_unified_wallet_coins.assert_not_called()
    assert report['consistent']
    assert report['coins'][0]['wallet_inventory']=='0'


def test_empty_tracked_inventory_does_not_query_or_certify_account():
    client=Mock();report=audit_tracked_inventory(client,[],[])
    client.get_unified_wallet_coins_for.assert_not_called()
    assert not report['consistent']
