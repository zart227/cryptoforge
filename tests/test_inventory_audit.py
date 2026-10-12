from cryptoforge.inventory_audit import verify_inventory
from test_live_trade_journal import fill


def test_missing_conversion_and_unknown_opening_are_not_certified():
    fills=[fill('buy','Buy','10','2',fee='.1',currency='ETH')]
    tx=[{'currency':'ETH','transactionTime':'1000','id':'first','cashBalance':'9.9','change':'9.9'}]
    assert verify_inventory(fills,tx,[{'coin':'ETH','walletBalance':'9.9'}])['consistent']
    assert not verify_inventory(fills,tx,[{'coin':'ETH','walletBalance':'0'}])['consistent']
    tx[0]['cashBalance']='19.9'
    assert not verify_inventory(fills,tx,[{'coin':'ETH','walletBalance':'9.9'}])['consistent']
