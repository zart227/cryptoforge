import pytest
from datetime import timedelta
from decimal import Decimal as D
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.primary_forecast_outcomes import collect_primary_forecast_outcomes
from cryptoforge.supabase_executor import CandleRow
from test_primary_forecast_memory import NOW,forecast


def test_collector_shares_one_cached_pair_read_and_never_adds_cash_buys(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    memory.record(forecast());memory.record({**forecast(),'artifact_sha256':'b'*64})
    as_of=NOW+timedelta(minutes=11);memory.clock=lambda:as_of
    class Reader:
        calls=0
        def read_candles(self,pair,**kwargs):
            self.calls+=1
            return [CandleRow(pair,'ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))]
    reader=Reader();report=collect_primary_forecast_outcomes(memory,reader,as_of=as_of)
    assert reader.calls==1 and report['counts']['observed_price_outcome_version_recorded']==2
    assert report['cash_training_rows_added']==0 and not report['realized_portfolio_income_established']
    repeated=collect_primary_forecast_outcomes(memory,reader,as_of=as_of)
    assert repeated['counts']['original_price_outcome_preserved']==2


def test_missing_endpoint_is_not_a_negative_label(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    receipt=memory.record(forecast());as_of=NOW+timedelta(minutes=11);memory.clock=lambda:as_of
    class Reader:
        def read_candles(self,pair,**kwargs):return []
    report=collect_primary_forecast_outcomes(memory,Reader(),as_of=as_of)
    assert report['counts']['missing_target_candle']==1
    assert memory.available_outcome(receipt['forecast_id'],as_of=as_of) is None


def test_one_partial_cached_endpoint_does_not_exclude_a_valid_later_endpoint(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    memory.record(forecast())
    memory.record({**forecast(),'input_bar_open_time':(NOW-timedelta(minutes=15)).isoformat()})
    as_of=NOW+timedelta(minutes=11);memory.clock=lambda:as_of
    class Reader:
        def read_candles(self,pair,**kwargs):
            return [CandleRow(pair,'ETHUSDT',NOW,D(100),D(102),D(99),D(101),D(100),cache_observed_at=NOW+timedelta(minutes=4)),
                CandleRow(pair,'ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))]
    report=collect_primary_forecast_outcomes(memory,Reader(),as_of=as_of)
    assert report['counts']['invalid_price_endpoint_evidence']==1
    assert report['counts']['observed_price_outcome_version_recorded']==1
    assert report['selected_forecast_accounting_matches']
    assert report['forecast_errors'][0]['reason']=='endpoint_not_known_closed_at_observation'


def test_pending_pair_runs_before_resolved_rows_of_an_earlier_pair(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    memory.record(forecast());memory.record({**forecast(),'artifact_sha256':'b'*64})
    memory.record({**forecast(),'pair':'BTC/USDT'})
    as_of=NOW+timedelta(minutes=11);memory.clock=lambda:as_of
    candle=CandleRow('ETH/USDT','ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100))
    # ETH has both pending and resolved rows. BTC must run before ETH corrections.
    eth=[r for r in memory.rows() if r['pair']=='ETH/USDT']
    memory.record_outcome(eth[0]['forecast_id'],candle)
    class Reader:
        def read_candles(self,pair,**kwargs):
            return [CandleRow(pair,pair.replace('/',''),candle.open_time,D(100),D(102),D(99),D(101),D(100))]
    calls=[];record=memory.record_outcome
    def traced(forecast_id,*args,**kwargs):
        calls.append(forecast_id);return record(forecast_id,*args,**kwargs)
    memory.record_outcome=traced
    report=collect_primary_forecast_outcomes(memory,Reader(),as_of=as_of,maximum_pairs=2)
    assert calls[-1]==eth[0]['forecast_id']
    assert report['counts']['observed_price_outcome_version_recorded']==2
    assert report['counts']['original_price_outcome_preserved']==1
    assert report['read_pairs']==2 and report['selected_forecast_accounting_matches']


@pytest.mark.parametrize('partial_cache',[False,True])
def test_missing_and_partial_cache_recover_with_observation_now(tmp_path,partial_cache):
    from cryptoforge.primary_forecast_outcomes import BybitPrimaryEndpointReader
    from cryptoforge.market_data import Candle
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    receipt=memory.record(forecast());as_of=NOW+timedelta(minutes=11);memory.clock=lambda:as_of
    class Reader:
        def read_candles(self,pair,**kwargs):
            if not partial_cache:return []
            return [CandleRow(pair,'ETHUSDT',NOW+timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100),cache_observed_at=NOW)]
    class Public:
        calls=0
        def get_klines(self,symbol,interval,limit,**kwargs):
            self.calls+=1
            assert interval=='5' and limit==1
            assert kwargs['end_ms']-kwargs['start_ms']==299999
            return [Candle(symbol,interval,kwargs['start_ms'],D(100),D(102),D(99),D(101),D(100),D(10000))]
    public=Public();endpoint=BybitPrimaryEndpointReader(public,clock=lambda:as_of)
    report=collect_primary_forecast_outcomes(memory,Reader(),as_of=as_of,endpoint_reader=endpoint)
    assert report['counts']['observed_price_outcome_version_recorded']==1
    assert report['public_endpoint_requests']==1 and public.calls==1
    assert report['public_endpoint_evidence'][0]['observed_at']==as_of.isoformat()
    assert memory.available_outcome(receipt['forecast_id'],as_of=as_of-timedelta(seconds=1)) is None
    assert memory.available_outcome(receipt['forecast_id'],as_of=as_of)['label_available_at']==as_of.isoformat()


def test_public_wrong_endpoint_is_rejected(tmp_path):
    import pytest
    from cryptoforge.primary_forecast_outcomes import BybitPrimaryEndpointReader
    from cryptoforge.market_data import Candle
    class Public:
        def get_klines(self,symbol,interval,limit,**kwargs):
            return [Candle(symbol,interval,kwargs['start_ms']-300000,D(100),D(102),D(99),D(101),D(100),D(10000))]
    reader=BybitPrimaryEndpointReader(Public(),clock=lambda:NOW+timedelta(hours=1))
    with pytest.raises(ValueError,match='identity mismatch'):
        reader.read_target_candle('ETH/USDT',target=NOW)
