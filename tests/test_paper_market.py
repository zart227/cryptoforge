from copy import deepcopy
from datetime import UTC,datetime
import pytest
from cryptoforge.paper_market import observe_market,normalize_market

NOW=datetime(2026,10,8,10,tzinfo=UTC);MILLIS=int(NOW.timestamp()*1000)


def packets():
    instrument={'retCode':0,'result':{'list':[{'symbol':'AAAUSDT','quoteCoin':'USDT','status':'Trading',
        'lotSizeFilter':{'basePrecision':'.0001','minOrderAmt':'5','maxMarketOrderQty':'10000'}}]}}
    book={'retCode':0,'time':MILLIS,'result':{'s':'AAAUSDT','b':[['99','100']],
        'a':[['100','200']],'ts':MILLIS-10,'u':123}}
    return instrument,book


def test_adapter_only_uses_two_public_spot_requests():
    class Public:
        base_url='https://api.bybit.com'
        def __init__(self):self.calls=[]
        def _get_json(self,path,query):
            self.calls.append((path,query));return packets()[1 if 'orderbook' in path else 0]
    client=Public();quote,filters=observe_market(client,'AAA/USDT',clock=lambda:NOW)
    assert len(client.calls)==2 and all(q['category']=='spot' for _,q in client.calls)
    assert quote['bid_qty']=='100' and filters['maximum_market_quantity']=='10000'
    assert len(quote['source_sha256'])==64


@pytest.mark.parametrize('failure',['wrong_pair','missing_limit','old_book','zero_size','halted','contract_quote'])
def test_unknown_or_wrong_market_data_never_gets_default_filters(failure):
    instrument,book=deepcopy(packets())
    if failure=='wrong_pair':book['result']['s']='BBBUSDT'
    elif failure=='missing_limit':instrument['result']['list'][0]['lotSizeFilter'].pop('maxMarketOrderQty')
    elif failure=='old_book':book['result']['ts']-=20000
    elif failure=='zero_size':book['result']['b'][0][1]='0'
    elif failure=='halted':instrument['result']['list'][0]['status']='PreLaunch'
    else:instrument['result']['list'][0]['quoteCoin']='USDC'
    with pytest.raises((ValueError,KeyError)):
        normalize_market('AAA/USDT',instrument,book,instrument_at=NOW,book_at=NOW)
