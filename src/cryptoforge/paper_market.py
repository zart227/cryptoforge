"""Normalize fresh public Spot orderbook and explicit instrument limits for paper."""
from datetime import UTC,datetime
import hashlib
import json
from urllib.parse import urlparse

from cryptoforge.paper_wallet import _number


def observe_market(client,pair,*,clock=None):
    clock=clock or (lambda:datetime.now(UTC))
    if urlparse(client.base_url).scheme!='https' or urlparse(client.base_url).hostname!='api.bybit.com':
        raise ValueError('global production public market source required')
    if not pair.endswith('/USDT'):raise ValueError('USDT paper market only')
    symbol=pair.replace('/','')
    instrument=client._get_json('/v5/market/instruments-info',{'category':'spot','symbol':symbol})
    instrument_at=clock()
    book=client._get_json('/v5/market/orderbook',{'category':'spot','symbol':symbol,'limit':1})
    book_at=clock()
    return normalize_market(pair,instrument,book,instrument_at=instrument_at,book_at=book_at)


def normalize_market(pair,instrument,book,*,instrument_at,book_at):
    if instrument_at.tzinfo is None or book_at.tzinfo is None or instrument_at>book_at:
        raise ValueError('ordered receipt times required')
    if instrument.get('retCode')!=0 or book.get('retCode')!=0:raise ValueError('market request failed')
    rows=instrument['result']['list'];symbol=pair.replace('/','')
    if len(rows)!=1 or rows[0]['symbol']!=symbol or book['result']['s']!=symbol:
        raise ValueError('public market identity mismatch')
    raw=rows[0]
    if raw.get('quoteCoin')!='USDT' or raw.get('status')!='Trading':
        raise ValueError('Trading USDT Spot instrument required')
    source_age=int(book['time'])-int(book['result']['ts'])
    clock_skew=abs(int(book_at.timestamp()*1000)-int(book['time']))
    if not -1000<=source_age<=10000 or clock_skew>60000:
        raise ValueError('stale or implausible server orderbook timestamp')
    bids=book['result']['b'];asks=book['result']['a']
    if not bids or not asks or len(bids[0])!=2 or len(asks[0])!=2:
        raise ValueError('both sides of displayed book required')
    bid,bid_qty=map(_number,bids[0]);ask,ask_qty=map(_number,asks[0])
    if bid>ask:raise ValueError('crossed public book')
    lot=raw['lotSizeFilter']
    step=_number(lot['basePrecision']);minimum=_number(lot['minOrderAmt']);maximum=_number(lot['maxMarketOrderQty'])
    quote={'pair':pair,'market':'spot','venue':'bybit_global','observed_at':book_at.isoformat(),
        'bid':str(bid),'ask':str(ask),'bid_qty':str(bid_qty),'ask_qty':str(ask_qty),
        'source_server_timestamp_ms':book['result']['ts'],'source_update_id':book['result'].get('u'),
        'source_sha256':hashlib.sha256(json.dumps(book,sort_keys=True).encode()).hexdigest(),
        'raw_orderbook':book,'source':'GET /v5/market/orderbook category=spot limit=1'}
    filters={'pair':pair,'market':'spot','venue':'bybit_global','status':'Trading',
        'observed_at':instrument_at.isoformat(),'quantity_step':str(step),
        'minimum_notional':str(minimum),'maximum_market_quantity':str(maximum),
        'source_sha256':hashlib.sha256(json.dumps(instrument,sort_keys=True).encode()).hexdigest(),
        'raw_instrument':raw,'source':'GET /v5/market/instruments-info category=spot'}
    return quote,filters
