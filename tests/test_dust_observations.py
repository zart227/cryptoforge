from cryptoforge.dust_observations import observe_pairs


class Public:
    def __init__(self,size=25):self.calls=[];self.size=size
    def _get_json(self,path,query):
        self.calls.append((path,query))
        if 'instruments' in path:
            return {'result':{'list':[{'symbol':f'COIN{i}USDT','status':'Trading',
                'lotSizeFilter':{'basePrecision':'.01','minOrderAmt':'5'}} for i in range(self.size)]}}
        return {'result':{'list':[{'symbol':f'COIN{i}USDT','bid1Price':'1.25'} for i in range(self.size)]}}


def test_more_than_twenty_pairs_use_two_requests_without_alphabetic_exclusion():
    client=Public();pairs=[f'COIN{i}/USDT' for i in range(25)]
    result,errors=observe_pairs(client,pairs)
    assert len(result)==25 and errors=={} and len(client.calls)==2
    assert all(query=={'category':'spot'} for _,query in client.calls)
    assert result['COIN24/USDT']['bid_price']=='1.25'


def test_missing_pair_is_not_filled_with_some_other_instrument():
    result,errors=observe_pairs(Public(1),['COIN0/USDT','MISSING/USDT'])
    assert len(result)==1 and errors['MISSING/USDT']=='missing_public_instrument_or_quote'


def test_failed_request_does_not_publish_partly_known_observations():
    class Broken(Public):
        def _get_json(self,path,query):
            if 'tickers' in path:raise TimeoutError()
            return super()._get_json(path,query)
    result,errors=observe_pairs(Broken(),['COIN0/USDT'])
    assert not result and errors=={'COIN0/USDT':'TimeoutError'}


def test_empty_scope_makes_no_request():
    client=Public();assert observe_pairs(client,[])==({},{});assert not client.calls
