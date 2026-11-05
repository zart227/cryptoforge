from datetime import UTC,datetime,timedelta
import pytest
from cryptoforge.fee_observation import normalize_fee_observation

NOW=datetime(2026,10,13,tzinfo=UTC)


def packet():return {'retCode':0,'result':{'category':'spot','list':[{'symbol':'APTUSDT','makerFeeRate':'0.001','takerFeeRate':'0.0018'}]}}


def normalize(payload,observed=NOW):
    return normalize_fee_observation(payload,symbol='APTUSDT',started_at=NOW-timedelta(seconds=1),observed_at=observed,now=NOW)


def test_observed_account_rate_is_not_historical_fill_fee_asset_proof():
    receipt=normalize(packet())
    assert receipt['rates']['takerFeeRate']=='0.0018'
    assert not receipt['fee_asset_known'] and not receipt['actual_fill_cost_verified']


@pytest.mark.parametrize('kind',['wrong_symbol','wrong_market','nan','future','backdate'])
def test_unsupported_or_backdated_fee_response_is_not_usable(kind):
    payload=packet();observed=NOW
    if kind=='wrong_symbol':payload['result']['list'][0]['symbol']='ETHUSDT'
    elif kind=='wrong_market':payload['result']['category']='linear'
    elif kind=='nan':payload['result']['list'][0]['takerFeeRate']='NaN'
    elif kind=='future':observed+=timedelta(seconds=1)
    else:observed-=timedelta(minutes=1)
    with pytest.raises(ValueError):normalize(payload,observed)
