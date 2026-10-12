from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from cryptoforge.context_features import context_snapshots,FEATURE_NAMES,FEATURE_VERSION
from test_trade_simulator import history


def fixture():
    eth=history(count=160);btc=[replace(row,pair='BTC/USDT',symbol='BTCUSDT') for row in eth]
    return eth,btc


def test_context_schema_is_explicit_and_all_observations_are_available():
    eth,btc=fixture();as_of=eth[-1].open_time+timedelta(minutes=5)
    values,quality=context_snapshots('ETH/USDT',eth,btc,as_of=as_of)
    assert values and len(FEATURE_NAMES)==24 and len(values[0].features)==24
    assert values[0].feature_version==FEATURE_VERSION and not quality['live_model_input_allowed']
    assert all(value.feature_available_at<=as_of and value.regime=='range' for value in values)
    assert all(value.features[15]==0 for value in values)  # identical series have zero relative return


def test_future_btc_and_hour_prices_do_not_change_past_context():
    eth,btc=fixture();as_of=eth[100].open_time+timedelta(minutes=5)
    before=context_snapshots('ETH/USDT',eth,btc,as_of=as_of)[0]
    changed=btc[:101]+[replace(row,open=D(200),close=D(200),low=D(199),high=D(201)) for row in btc[101:]]
    assert context_snapshots('ETH/USDT',eth,changed,as_of=as_of)[0]==before
    assert context_snapshots('ETH/USDT',eth[:101],btc[:101],as_of=as_of)[0]==before


def test_missing_aligned_market_context_is_excluded_not_zero_filled():
    eth,btc=fixture();as_of=eth[-1].open_time+timedelta(minutes=5)
    values,quality=context_snapshots('ETH/USDT',eth,btc[:80],as_of=as_of)
    assert quality['excluded']['missing_aligned_btc_context']>0
    assert all(value.open_time<=btc[79].open_time for value in values)


def test_delayed_btc_revision_is_not_backdated_or_used_to_select_future_hours():
    eth,btc=fixture();as_of=eth[-1].open_time+timedelta(minutes=5)
    original=context_snapshots('ETH/USDT',eth,btc,as_of=as_of)[0]
    btc[0]=replace(btc[0],cache_observed_at=as_of)
    revised=context_snapshots('ETH/USDT',eth,btc,as_of=as_of)[0]
    assert [v.features for v in revised]==[v.features for v in original]
    assert all(v.feature_available_at==as_of for v in revised)
