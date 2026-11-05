"""Forward observed account fee rates, separate from actual fill fee assets."""
from datetime import datetime,timedelta
from decimal import Decimal
import json
from cryptoforge.training_snapshot import _save_raw


def normalize_fee_observation(payload,*,symbol,started_at,observed_at,now):
    if any(stamp.tzinfo is None for stamp in (started_at,observed_at,now)) or not started_at<=observed_at<=now or now-observed_at>timedelta(seconds=5):
        raise ValueError('actual recent fee response observation required')
    result=payload.get('result') or {};rows=result.get('list')
    if payload.get('retCode')!=0 or result.get('category')!='spot' or not isinstance(rows,list) or len(rows)!=1 or rows[0].get('symbol')!=symbol:
        raise ValueError('explicit requested Spot fee identity required')
    if not isinstance(symbol,str) or not symbol.isascii() or not symbol.isalnum() or symbol!=symbol.upper() or not symbol.endswith('USDT'):
        raise ValueError('explicit USDT Spot symbol required')
    rates={}
    for field in ('makerFeeRate','takerFeeRate'):
        value=Decimal(str(rows[0][field]))
        if not value.is_finite() or not -1<value<1:raise ValueError('finite observed fee fraction required')
        rates[field]=str(value)
    return {'symbol':symbol,'market':'spot','request_started_at':started_at.isoformat(),'observed_at':observed_at.isoformat(),
        'rates':rates,'source_endpoint':'GET /v5/account/fee-rate category=spot symbol='+symbol,
        'fee_asset_known':False,'historical_fee_schedule_known':False,'actual_fill_cost_verified':False,
        'live_promotion_allowed':False}


def save_fee_observation(directory,payload,*,symbol,started_at,observed_at,now,account_scope,implementation_hashes,runtime_source_bundle):
    receipt=normalize_fee_observation(payload,symbol=symbol,started_at=started_at,observed_at=observed_at,now=now)
    raw=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    receipt.update(schema_version='observed-account-spot-fees-v1',account_scope=account_scope,
        original_source=_save_raw(directory/'sources',raw(payload)),implementation_hashes=implementation_hashes,
        runtime_source_bundle=runtime_source_bundle)
    return _save_raw(directory/'receipts',raw(receipt)),receipt
