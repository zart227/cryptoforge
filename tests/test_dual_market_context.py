from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from cryptoforge.dual_market_context import dual_context_snapshots,FEATURE_VERSION,FEATURE_NAMES
from test_trade_simulator import history


def fixture():
    rows=history('SOL/USDT',count=160)
    def series(pair,multiplier):
        return [replace(row,pair=pair,symbol=pair.replace('/',''),open=D(100)+D(i%7)*multiplier,
            close=D(100)+D(i%7)*multiplier,high=D(105),low=D(95)) for i,row in enumerate(rows)]
    return series('SOL/USDT',D('.2')),series('BTC/USDT',D('.1')),series('ETH/USDT',D('.3'))


def test_dual_market_schema_keeps_existing_dimensions_separate():
    own,btc,eth=fixture();now=own[-1].open_time+timedelta(minutes=5)
    values,quality=dual_context_snapshots('SOL/USDT',own,btc,eth,as_of=now)
    assert values and len(FEATURE_NAMES)==29 and len(values[0].features)==29
    assert all(v.feature_version==FEATURE_VERSION for v in values)
    assert all(-1<=v.features[-1]<=1 and -1<=v.features[-2]<=1 for v in values)
    assert not quality['live_model_input_allowed'] and not quality['unknown_context_filled']


def test_future_eth_changes_do_not_change_past_dual_context():
    own,btc,eth=fixture();now=own[100].open_time+timedelta(minutes=5)
    before=dual_context_snapshots('SOL/USDT',own,btc,eth,as_of=now)[0]
    changed=eth[:101]+[replace(row,open=D(200),close=D(200),high=D(201),low=D(199)) for row in eth[101:]]
    assert dual_context_snapshots('SOL/USDT',own,btc,changed,as_of=now)[0]==before


def test_late_eth_observation_is_not_backdated():
    own,btc,eth=fixture();now=own[-1].open_time+timedelta(minutes=5)
    eth[0]=replace(eth[0],cache_observed_at=now)
    values,_=dual_context_snapshots('SOL/USDT',own,btc,eth,as_of=now)
    assert values and all(value.feature_available_at==now for value in values)


def test_missing_eth_and_undefined_correlation_are_excluded():
    own,btc,eth=fixture();now=own[-1].open_time+timedelta(minutes=5)
    values,quality=dual_context_snapshots('SOL/USDT',own,btc,eth[:80],as_of=now)
    assert quality['excluded']['missing_aligned_eth_context']>0
    assert all(v.open_time<=eth[79].open_time for v in values)
    flat=[replace(row,open=D(100),close=D(100)) for row in eth]
    values,quality=dual_context_snapshots('SOL/USDT',own,btc,flat,as_of=now)
    assert not values and quality['excluded']['undefined_return_correlation']>0
    assert not quality['undefined_correlation_filled']
