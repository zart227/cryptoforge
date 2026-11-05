import json
from pathlib import Path
from decimal import Decimal
import scripts.audit_stop_case_minutes as module


def test_resource_deferral_does_not_read_missing_ingestion_or_create_a_completed_report(tmp_path,monkeypatch):
    output=tmp_path/'audit.json'
    monkeypatch.setattr(module,'prepare_research',lambda *args:(_ for _ in ()).throw(ValueError('insufficient resources: defer research')))
    monkeypatch.setattr(module.argparse.ArgumentParser,'parse_args',lambda self:__import__('types').SimpleNamespace(ingestion=tmp_path/'missing.json',output=output,resource_protocol=tmp_path/'protocol.json'))
    module.main()
    assert not output.exists()
    status=json.loads(output.with_name('audit-status.json').read_bytes())
    assert not status['completed'] and status['status']=='deferred_resource_or_worker_guard'


def test_source_window_decoder_preserves_recorded_observation_time():
    raw={'pair':'ETH/USDT','symbol':'ETHUSDT','open_time':'2026-10-01 00:00:00+00:00',
        'open':'100','high':'101','low':'99','close':'100','volume':'20','cache_observed_at':'2026-10-10T00:00:00+00:00'}
    row=module.candle(raw)
    assert row.open==Decimal(100) and row.cache_observed_at.day==10
