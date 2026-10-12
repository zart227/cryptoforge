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
