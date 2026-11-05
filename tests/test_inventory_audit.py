from cryptoforge.inventory_audit import verify_inventory
from test_live_trade_journal import fill


def test_missing_conversion_and_unknown_opening_are_not_certified():
    fills=[fill('buy','Buy','10','2',fee='.1',currency='ETH')]
    tx=[{'currency':'ETH','transactionTime':'1000','id':'first','cashBalance':'9.9','change':'9.9'}]
    assert verify_inventory(fills,tx,[{'coin':'ETH','walletBalance':'9.9'}])['consistent']
    assert not verify_inventory(fills,tx,[{'coin':'ETH','walletBalance':'0'}])['consistent']
    tx[0]['cashBalance']='19.9'
    assert not verify_inventory(fills,tx,[{'coin':'ETH','walletBalance':'9.9'}])['consistent']


def test_overlap_duplicates_do_not_change_verified_inventory():
    row=fill('buy','Buy','10','2',fee='.1',currency='ETH')
    tx=[{'currency':'ETH','transactionTime':'1000','id':'first','cashBalance':'9.9','change':'9.9'}]
    wallet=[{'coin':'ETH','walletBalance':'9.9'}]
    assert verify_inventory([row,row],tx,wallet)==verify_inventory([row],tx,wallet)


def test_unknown_fees_and_missing_wallet_coin_are_not_zero_inventory_proof():
    row=fill('buy','Buy','10','2',currency='ETH');row.pop('execFee')
    tx=[{'currency':'ETH','transactionTime':'1000','id':'first','cashBalance':'10','change':'10'}]
    assert not verify_inventory([row],tx,[{'coin':'ETH','walletBalance':'10'}])['consistent']
    row['execFee']='0'
    assert not verify_inventory([row],tx,[])['consistent']


def test_nonfinite_wallet_or_duplicate_coin_cannot_certify_inventory():
    import pytest
    row=fill('buy','Buy','10','2')
    for wallet in ([{'coin':'ETH','walletBalance':'NaN'}],[{'coin':'ETH','walletBalance':'10'}]*2):
        with pytest.raises(ValueError):verify_inventory([row],[],wallet)
