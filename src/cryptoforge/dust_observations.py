"""Bounded bulk public snapshots avoid alphabetic pair caps in label collection."""
from datetime import UTC,datetime
import hashlib
import json


def observe_pairs(client,pairs):
    pairs=sorted(set(pairs));observations={};errors={}
    if not pairs:return observations,errors
    try:
        instruments=client._get_json('/v5/market/instruments-info',{'category':'spot'})
        instrument_at=datetime.now(UTC).isoformat()
        tickers=client._get_json('/v5/market/tickers',{'category':'spot'})
        quote_at=datetime.now(UTC).isoformat()
        by_instrument=_unique(instruments['result']['list'])
        by_ticker=_unique(tickers['result']['list'])
    except Exception as exc:
        return {},{pair:type(exc).__name__ for pair in pairs}
    for pair in pairs:
        symbol=pair.replace('/','')
        if symbol not in by_instrument or symbol not in by_ticker:
            errors[pair]='missing_public_instrument_or_quote';continue
        raw=by_instrument[symbol];ticker=by_ticker[symbol]
        proof={'instrument':raw,'ticker':ticker}
        observations[pair]={'category':'spot','instrument':raw,'observed_at':instrument_at,
            'quote_observed_at':quote_at,'bid_price':ticker.get('bid1Price'),
            'ticker':ticker,'projection_sha256':hashlib.sha256(json.dumps(proof,sort_keys=True).encode()).hexdigest(),
            'source':'public_bulk_spot_response_projection_observation_only'}
    return observations,errors


def _unique(rows):
    result={}
    for row in rows:
        symbol=row['symbol']
        if symbol in result:raise ValueError('duplicate public instrument identity')
        result[symbol]=row
    return result
