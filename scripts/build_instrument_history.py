"""Build reviewed factual events from captured official announcements."""
from dataclasses import asdict
from datetime import UTC,datetime,timedelta
from html.parser import HTMLParser
import hashlib
import json
import re
from pathlib import Path

from cryptoforge.instrument_history import InstrumentEvent,state_at,minimum_rule_table
from cryptoforge.announcement_sources import article_tables,extract_article

DIRECTORY=Path('.local/archive-stage1/sources')
BASKET={'BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','LTCUSDT','DOTUSDT'}
SLUGS={
 'minimum-jan2025':'update-on-minimum-single-order-value-and-quantity-for-spot-and-margin-trading-pairs-blt96f1cea87db75db9',
 'tick-nov2025':'updates-on-tick-size-for-spot-pairs-bltb24e3aeb8029170f',
 'tick-jun2026':'updates-on-tick-size-for-spot-pairs-jun-26-2026-8-00am-utc--blt4f859a69f6600b94',
 'delist-sep2026':'bybit-to-delist-4-token-s-on-sep-24-2026--art1a1071a0dd4e',
 'tick-apr1-2026':'updates-on-tick-size-for-spot-pairs-apr-1-2026-10-00am-utc--bltdc47ad37a9df200a',
 'tick-apr2026':'updates-on-tick-size-for-spot-pairs-apr-20-2026-7-00am-utc--blt1d751e461e90bafa',
 'delist-may2026':'delisting-of-ami-bdxn-one-sis-xem-and-insp-bltdf4d2a49c410bf3f',
 'listing-mon2025':'bybit-to-list-monad-mon-on-spot-blt92fd8d600e619238',
 'maximum-oct2025':'changes-to-maximum-order-size-for-limit-and-market-orders-blt6ac479804a794c46',
}


def text(node):
    return node.get('text','')+''.join(text(child) for child in node.get('children',[]))


def walk(node):
    if isinstance(node,dict):
        yield node
        for child in node.get('children',[]):yield from walk(child)


class TextHTML(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)


def main():
    captured=datetime.now(UTC).isoformat();events=[];sources={}
    immutable=DIRECTORY/'captured';immutable.mkdir(exist_ok=True)
    for key,slug in SLUGS.items():
        payload=json.loads((DIRECTORY/(key+'.next.json')).read_text())
        article=payload['articleDetail']
        raw=(DIRECTORY/(key+'.html')).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',raw.decode(),re.S)
        if not match or json.loads(match.group(1))['props']['pageProps']!=payload:
            raise ValueError('parsed source cache differs from captured official HTML')
        snapshot=immutable/(digest+'.html')
        if snapshot.exists() and snapshot.read_bytes()!=raw:
            raise ValueError('immutable official source snapshot corrupted')
        if not snapshot.exists():snapshot.write_bytes(raw)
        domain='announcements.bybit.global' if key=='delist-may2026' else 'announcements.bybit.com'
        url=f'https://{domain}/en/article/{slug}/'
        sources[key]={'url':url,'published_at':article['date'],'captured_at':captured,
                      'sha256':digest,'snapshot_path':str(snapshot.resolve()),
                      'historical_page_revision_verified':False}
        announced=datetime.fromisoformat(article['date'].replace('Z','+00:00'))
        if announced.hour==announced.minute==announced.second==0:
            announced+=timedelta(days=1)
            sources[key]['publication_precision']='date_only_conservative_next_day_bound'
        else:
            sources[key]['publication_precision']='metadata_timestamp'
        root=(article.get('content') or {}).get('json')
        rows=article_tables(article)
        def add(symbol,kind,effective,values):
            event=InstrumentEvent(symbol,kind,effective,announced.isoformat(),url,digest,values)
            event.validate();events.append(event)
        if key=='minimum-jan2025':
            body=extract_article(raw)['body']
            if 'Jan 21, 2025, 8AM UTC' not in body:
                raise ValueError('baseline effective date missing from captured source')
            baseline=minimum_rule_table(article)
            if not BASKET.issubset({row['symbol'] for row in baseline}):
                raise ValueError('baseline table does not cover original basket')
            sources[key]['baseline_usdt_pairs']=len(baseline)
            for row in baseline:
                add(row['symbol'],'rule_change','2025-01-21T08:00:00+00:00',row['values'])
                add(row['symbol'],'availability_observation','2025-01-21T08:00:00+00:00',{})
        elif key in ('tick-nov2025','tick-apr2026','tick-apr1-2026','tick-jun2026'):
            # Dates independently reviewed from body, never guessed from title alone.
            body=extract_article(raw)['body']
            effective={'tick-apr2026':'2026-04-20T07:00:00+00:00',
                       'tick-nov2025':'2025-11-17T10:00:00+00:00',
                       'tick-apr1-2026':'2026-04-01T10:00:00+00:00',
                       'tick-jun2026':'2026-06-26T08:00:00+00:00'}[key]
            if key=='tick-apr1-2026' and 'Apr 1, 2026, 10:00AM UTC' not in body:
                raise ValueError('tick effective time missing from source body')
            selected=[row for row in rows[1:] if row and row[0] in BASKET]
            sources[key]['basket_rows']=len(selected)
            sources[key]['effective_at_reviewed']=effective
            if key=='tick-jun2026' and ('Jun 26, 2026, 8:00AM UTC' not in body or rows[0]!=['Spot Pair','Tick Size (Before)','Tick Size (Adjusted)']):
                raise ValueError('June tick date/table must be reviewed')
            if effective:
                for row in selected:add(row[0],'rule_change',effective,{'tick_size':row[2]})
        elif key=='delist-may2026':
            parsed=TextHTML();parsed.feed(article['content_html']);body=' '.join(parsed.parts)
            if 'May 28, 2026' not in body or '8AM UTC' not in body:raise ValueError('delisting time not verified in body')
            for symbol in ('AMIUSDT','BDXNUSDT','ONEUSDT','SISUSDT','XEMUSDT','INSPUSDT'):
                if symbol not in body:raise ValueError('delisted symbol absent from source')
                add(symbol,'delisting','2026-05-28T08:00:00+00:00',{})
        elif key=='delist-sep2026':
            body=extract_article(raw)['body']
            if 'Sep 24, 2026, 8:00AM UTC' not in body:
                raise ValueError('September Spot delisting date not verified')
            for symbol in ('NEONUSDT','SUNDOGUSDT','ICXUSDT','TACUSDT'):
                if symbol not in body:raise ValueError('delisted symbol absent from body')
                add(symbol,'delisting','2026-09-24T08:00:00+00:00',{})
        elif key=='listing-mon2025':
            body=text(root)
            if 'Nov 24, 2025, 3:00PM UTC' not in body or 'MON/USDT' not in body:
                raise ValueError('Spot listing time and symbol not verified')
            add('MONUSDT','listing','2025-11-24T15:00:00+00:00',{})
        else:
            sources[key]['status']='documented_general_rule_change_no_pair_specific_numeric_bounds_imported'
    data={'schema_version':'instrument-history-v1','captured_at':captured,'sources':sources,
          'events':[{**asdict(event),'event_id':event.event_id} for event in events],
          'coverage':'partial_official_events_not_full_historical_universe',
          'basket_state_at_archive_start':{symbol:state_at(events,symbol,datetime(2025,10,1,tzinfo=UTC)) for symbol in sorted(BASKET)},
          'can_certify_historical_execution':False,'live_eligible':False}
    output=Path('.local/state/instrument-history.json');output.write_text(json.dumps(data,indent=2))
    print(json.dumps({'events':len(events),'sources':len(sources),'baseline_usdt_rules':sources['minimum-jan2025']['baseline_usdt_pairs'],
                      'delisted_symbols':len({e.symbol for e in events if e.kind=='delisting'}),'listing_events':1,'coverage':data['coverage'],'output':str(output.resolve())}))


if __name__=='__main__':
    main()
