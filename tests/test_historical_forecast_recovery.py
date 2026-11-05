from datetime import timedelta
from decimal import Decimal as D
import sqlite3

from scripts.recover_historical_forecast_outcomes import freeze,recover_batch
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.supabase_executor import CandleRow
from test_primary_forecast_memory import NOW,forecast


def setup(tmp_path):
    memory=PrimaryForecastMemory(tmp_path/'memory.sqlite',clock=lambda:NOW,minimum_free_disk_mb=0)
    key=memory.record(forecast())['forecast_id']
    memory.clock=lambda:NOW+timedelta(days=2)
    directory=tmp_path/'recovery'
    manifest=freeze(memory,directory,now=memory.clock())
    return memory,key,directory,manifest


def test_historical_recovery_is_observed_now_and_repeat_preserves_outcome(tmp_path,monkeypatch):
    import scripts.recover_historical_forecast_outcomes as module
    import shutil
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:shutil._ntuple_diskusage(10**12,0,10**12))
    memory,key,directory,manifest=setup(tmp_path)
    class Reader:
        calls=0
        def read_target_candle(self,pair,*,target):
            self.calls+=1
            return CandleRow(pair,'ETHUSDT',target-timedelta(minutes=5),D(100),D(102),D(99),D(101),D(100),cache_observed_at=memory.clock())
    reader=Reader();result=recover_batch(memory,directory,manifest,reader)
    assert result['resolved_count']==1 and result['remaining_count']==0
    assert memory.available_outcome(key,as_of=NOW+timedelta(hours=1)) is None
    assert memory.available_outcome(key,as_of=memory.clock())['label_available_at']==memory.clock().isoformat()
    repeated=recover_batch(memory,directory,manifest,reader)
    assert reader.calls==1 and repeated['counts']=={'already_resolved':1}
    with sqlite3.connect(memory.path) as db:
        assert db.execute('select count(*) from primary_forecast_outcomes').fetchone()[0]==1


def test_missing_candle_remains_unresolved_with_reason(tmp_path,monkeypatch):
    import scripts.recover_historical_forecast_outcomes as module
    import shutil,json
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:shutil._ntuple_diskusage(10**12,0,10**12))
    memory,key,directory,manifest=setup(tmp_path)
    class Reader:
        def read_target_candle(self,*args,**kwargs):return None
    result=recover_batch(memory,directory,manifest,Reader())
    assert result['remaining']==[key]
    assert json.loads((directory/'receipts'/(key+'.json')).read_text())['status']=='missing_exact_target_candle'


def test_frozen_scope_excludes_forecasts_added_after_snapshot(tmp_path,monkeypatch):
    import scripts.recover_historical_forecast_outcomes as module
    import shutil
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:shutil._ntuple_diskusage(10**12,0,10**12))
    memory,key,directory,manifest=setup(tmp_path)
    memory.clock=lambda:NOW
    later=memory.record({**forecast(),'artifact_sha256':'b'*64})['forecast_id']
    memory.clock=lambda:NOW+timedelta(days=2)
    resumed=freeze(memory,directory,now=memory.clock())
    assert [r['forecast_id'] for r in resumed['forecasts']]==[key]
    assert later not in [r['forecast_id'] for r in resumed['forecasts']]


def test_changed_original_is_rejected_before_network_or_outcome(tmp_path,monkeypatch):
    import scripts.recover_historical_forecast_outcomes as module
    import shutil,json
    monkeypatch.setattr(module.shutil,'disk_usage',lambda _:shutil._ntuple_diskusage(10**12,0,10**12))
    memory,key,directory,manifest=setup(tmp_path)
    with sqlite3.connect(memory.path) as db:
        db.execute("update primary_forecasts set payload=json_set(payload,'$.reference_close','200') where id=?",(key,))
    class Reader:
        def read_target_candle(self,*args,**kwargs):raise AssertionError('must not fetch changed forecast')
    report=recover_batch(memory,directory,manifest,Reader())
    receipt=json.loads((directory/'receipts'/(key+'.json')).read_text())
    assert report['remaining_count']==1 and receipt['reason']=='original forecast changed or missing'
    assert memory.available_outcome(key,as_of=memory.clock()) is None
