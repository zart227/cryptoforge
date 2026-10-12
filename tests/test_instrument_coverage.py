from dataclasses import asdict, replace
from datetime import UTC, datetime
import hashlib
import json
import pytest

from cryptoforge.instrument_coverage import execution_coverage,load_fact_events,MARKET_REQUIRED_FIELDS
from cryptoforge.instrument_history import InstrumentEvent


def event(**changes):
    base=InstrumentEvent('AAAUSDT','rule_change','2025-01-01T00:00:00+00:00',
        '2025-01-01T00:00:00+00:00','https://announcements.bybit.com/en/article/test/',
        'a'*64,{'minimum_quantity':'1','minimum_order_value_api':'5'})
    return replace(base,**changes)


def test_missing_steps_and_limits_do_not_become_today_values():
    report=execution_coverage([event()],['AAAUSDT'],start=datetime(2025,1,2,tzinfo=UTC),end=datetime(2025,1,3,tzinfo=UTC))
    assert report['last_documented_value_fraction_of_symbol_time']['minimum_quantity']=='1'
    assert report['last_documented_value_fraction_of_symbol_time']['quantity_step']=='0'
    assert report['segments'][0]['missing_required_market_fields']==['maximum_market_quantity','quantity_step','tick_size']
    assert not report['can_certify_historical_execution']


def test_late_announced_filters_split_at_information_time():
    late=event(values={'tick_size':'.01'},announced_at='2025-01-02T12:00:00+00:00')
    report=execution_coverage([late],['AAAUSDT'],start=datetime(2025,1,2,tzinfo=UTC),end=datetime(2025,1,3,tzinfo=UTC))
    assert len(report['segments'])==2
    assert 'tick_size' not in report['segments'][0]['rules']
    assert report['segments'][1]['rules']['tick_size']=='.01'
    assert report['last_documented_value_fraction_of_symbol_time']['tick_size']=='0.5'


def test_even_all_numbers_are_not_exhaustive_historical_evidence():
    complete=event(values={field:'1' for field in MARKET_REQUIRED_FIELDS})
    report=execution_coverage([complete],['AAAUSDT'],start=datetime(2025,1,2,tzinfo=UTC),end=datetime(2025,1,3,tzinfo=UTC))
    assert report['segments_with_all_numeric_fields']==1
    assert report['certified_execution_segments']==0
    assert report['live_eligible'] is False


def test_ledger_rejects_source_or_semantic_tampering(tmp_path):
    source=tmp_path/'source.html';source.write_bytes(b'captured source')
    change=event(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    semantic=dict(symbol=change.symbol,kind=change.kind,effective_at=change.effective_at,
                  values=change.values,venue=change.venue,market=change.market)
    digest=hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    fact={**semantic,'fact_id':digest,'source_evidence':[{**asdict(change),'snapshot_path':str(source)}]}
    path=tmp_path/'ledger.json';path.write_text(json.dumps({'facts':[fact]}))
    assert len(load_fact_events(path)[1])==1
    source.write_bytes(b'altered')
    with pytest.raises(ValueError,match='source checksum'):load_fact_events(path)
    fact['values']={'minimum_quantity':'999'};path.write_text(json.dumps({'facts':[fact]}))
    with pytest.raises(ValueError,match='semantic checksum'):load_fact_events(path)


def test_documented_limitations_require_their_own_source_evidence(tmp_path):
    path=tmp_path/'state'/'ledger.json';path.parent.mkdir()
    path.write_text(json.dumps({'facts':[], 'source_coverage_gaps':[{'source_sha256':'a'*64}]}))
    with pytest.raises(ValueError,match='limitation source checksum'):
        load_fact_events(path)
