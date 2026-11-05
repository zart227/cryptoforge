"""Reproduce observed account fee receipts; no inference about past executions."""
from datetime import datetime,timedelta
from pathlib import Path
from cryptoforge.execution_market_evidence import _load
from cryptoforge.fee_observation import normalize_fee_observation
from cryptoforge.bybit_private import BybitPrivateClient
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources


def verify_fee_observation(reference,*,account_scope,as_of,maximum_age=timedelta(hours=1)):
    receipt=_load(reference)
    if receipt.get('schema_version')!='observed-account-spot-fees-v1' or receipt.get('account_scope')!=account_scope:
        raise ValueError('original account fee scope required')
    observed=datetime.fromisoformat(receipt['observed_at']);started=datetime.fromisoformat(receipt['request_started_at'])
    if as_of.tzinfo is None or observed.tzinfo is None or not started<=observed<=as_of:
        raise ValueError('observed account fee chronology required')
    if maximum_age<=timedelta(0) or as_of-observed>maximum_age:raise ValueError('stale observed account fees')
    dependencies={'adapter':BybitPrivateClient,'normalizer':normalize_fee_observation,
        'runner':Path(__file__).resolve().parents[2]/'scripts/capture_spot_account_fees.py'}
    assert_source_dependencies(receipt['implementation_hashes'],dependencies)
    load_runtime_sources(receipt['runtime_source_bundle'],receipt['implementation_hashes'])
    source=_load(receipt['original_source'])
    if type(source.get('time')) is not int or abs(source['time']-int(observed.timestamp()*1000))>60000:
        raise ValueError('original server fee clock required')
    original=normalize_fee_observation(source,symbol=receipt['symbol'],started_at=started,observed_at=observed,now=observed)
    if any(receipt.get(key)!=value for key,value in original.items()):
        raise ValueError('observed fee receipt differs from original response')
    return {'symbol':receipt['symbol'],'observed_at':receipt['observed_at'],'rates':receipt['rates'],
        'original_source_and_runtime_verified':True,'actual_fill_fee_asset_verified':False,
        'historical_fees_verified':False,'execution_settings_changed':False,'live_promotion_allowed':False}
