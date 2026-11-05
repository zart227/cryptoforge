import json
from pathlib import Path
from datetime import timedelta
import pytest
from test_paper_market import packets,NOW
from cryptoforge.paper_market import normalize_market
from cryptoforge.paper_wallet import _number
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import _save_raw,save_runtime_sources
from cryptoforge.execution_market_evidence import verify_execution_market_receipt


def fixture(tmp_path):
    raw=lambda value:json.dumps(value,sort_keys=True,separators=(',',':')).encode()
    instrument,book=packets();quote,filters=normalize_market('AAA/USDT',instrument,book,instrument_at=NOW,book_at=NOW)
    deps={'normalizer':normalize_market,'numeric_contract':_number,
          'runner':Path(__file__).resolve().parents[1]/'scripts/capture_execution_market_sources.py'}
    hashes=source_hashes(deps)
    receipt={'schema_version':'observed-execution-market-sources-v1','pair':'AAA/USDT','observed_at':NOW.isoformat(),
        'request_started_at':NOW.isoformat(),'quote':quote,'filters':filters,'implementation_hashes':hashes,
        'runtime_source_bundle':save_runtime_sources(tmp_path,deps,hashes),
        'instrument_source':_save_raw(tmp_path,raw(instrument)),'orderbook_source':_save_raw(tmp_path,raw(book))}
    for key in ('historical_rule_change_times_known','displayed_depth_proves_fill','fees_verified','partial_fill_model_verified','live_promotion_allowed'):receipt[key]=False
    return receipt,lambda:_save_raw(tmp_path,raw(receipt))


def test_raw_sources_reproduce_quote_without_certifying_execution(tmp_path):
    receipt,reference=fixture(tmp_path)
    result=verify_execution_market_receipt(reference(),as_of=NOW)
    assert result['spread_quote']=='1' and not result['execution_qualified']
    with pytest.raises(ValueError,match='stale'):
        verify_execution_market_receipt(reference(),as_of=NOW+timedelta(minutes=6))


def test_normalized_fields_cannot_replace_original_market_inputs(tmp_path):
    receipt,reference=fixture(tmp_path);receipt['quote']['bid']='100'
    with pytest.raises(ValueError,match='original sources'):verify_execution_market_receipt(reference(),as_of=NOW)


def test_current_book_cannot_be_claimed_as_historical_or_fill_proof(tmp_path):
    receipt,reference=fixture(tmp_path);receipt['displayed_depth_proves_fill']=True
    with pytest.raises(ValueError,match='certification'):verify_execution_market_receipt(reference(),as_of=NOW)
