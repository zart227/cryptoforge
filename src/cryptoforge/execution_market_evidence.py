"""Verify saved observed market inputs without inventing historical fills."""
from datetime import datetime,timedelta
import gzip,hashlib,json
from pathlib import Path
from cryptoforge.paper_market import normalize_market
from cryptoforge.paper_wallet import _number
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources


def _load(reference):
    size=reference.get('uncompressed_bytes')
    if reference.get('compression')!='gzip' or type(size) is not int or not 0<size<=2*1024**2:
        raise ValueError('bounded canonical source reference required')
    with gzip.open(reference['path'],'rb') as stream:raw=stream.read(size+1)
    if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('observed market source checksum mismatch')
    return json.loads(raw)


def verify_execution_market_receipt(reference,*,as_of,maximum_age=timedelta(minutes=5)):
    receipt=_load(reference)
    if receipt.get('schema_version')!='observed-execution-market-sources-v1':raise ValueError('observed source schema required')
    observed=datetime.fromisoformat(receipt['observed_at'])
    started=datetime.fromisoformat(receipt['request_started_at'])
    instrument_at=datetime.fromisoformat(receipt['filters']['observed_at'])
    if any(stamp.tzinfo is None for stamp in (as_of,observed,started,instrument_at)) or not started<=instrument_at<=observed<=as_of:
        raise ValueError('observed source clock chronology required')
    if maximum_age<=timedelta(0) or as_of-observed>maximum_age:
        raise ValueError('stale observed source receipt')
    for flag in ('historical_rule_change_times_known','displayed_depth_proves_fill','fees_verified','partial_fill_model_verified','live_promotion_allowed'):
        if receipt.get(flag) is not False:raise ValueError('unsupported market execution certification')
    deps={'normalizer':normalize_market,'numeric_contract':_number,
          'runner':Path(__file__).resolve().parents[2]/'scripts/capture_execution_market_sources.py'}
    assert_source_dependencies(receipt['implementation_hashes'],deps)
    load_runtime_sources(receipt['runtime_source_bundle'],receipt['implementation_hashes'])
    instrument=_load(receipt['instrument_source']);book=_load(receipt['orderbook_source'])
    quote,filters=normalize_market(receipt['pair'],instrument,book,instrument_at=instrument_at,book_at=observed)
    if quote!=receipt['quote'] or filters!=receipt['filters']:
        raise ValueError('normalized observation differs from original sources')
    return {'pair':receipt['pair'],'observed_at':receipt['observed_at'],'original_inputs_and_runtime_verified':True,
        'spread_quote':str(_number(quote['ask'])-_number(quote['bid'])),
        'minimum_notional':filters['minimum_notional'],'quantity_step':filters['quantity_step'],
        'displayed_bid_quantity':quote['bid_qty'],'displayed_ask_quantity':quote['ask_qty'],
        'execution_qualified':False,'live_promotion_allowed':False}
