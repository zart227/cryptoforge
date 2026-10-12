"""Discover official source candidates; never infer events from URL titles."""
from datetime import UTC,datetime
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin,urlparse
from urllib.request import Request,urlopen
import time


class Links(HTMLParser):
    def __init__(self):super().__init__();self.hrefs=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            self.hrefs.extend(value for key,value in attrs if key=='href' and value)


def main():
    directory=Path('.local/archive-stage1/sources/linkmaps');directory.mkdir(parents=True,exist_ok=True)
    sources=[];candidates={}
    for page in range(1,8):
        url=f'https://announcements.bybit.com/linkmap/{page}/'
        raw=urlopen(Request(url,headers={'User-Agent':'CryptoForge historical-source-inventory'}),timeout=20).read()
        digest=hashlib.sha256(raw).hexdigest();snapshot=directory/(str(page)+'-'+digest[:16]+'.html')
        if not snapshot.exists():snapshot.write_bytes(raw)
        parser=Links();parser.feed(raw.decode())
        count=0
        for href in parser.hrefs:
            target=urljoin(url,href);parts=urlparse(target);slug=parts.path.lower()
            if '/article/' not in slug or parts.hostname not in {'announcements.bybit.com','announcements.bybit.global'}:
                continue
            if any(term in slug for term in ('perpetual','futures','alpha','convert','pre-market')):
                continue
            if not any(term in slug for term in ('on-spot','spot-pair','spot-trading','delisting','minimum-single-order','minimum-order-value','maximum-order-size')):
                continue
            # Normalize language-specific links to global English for later review.
            if '/en-EU/' in parts.path or 'eu/' in parts.path.lower():continue
            tail=parts.path.split('/article/',1)[1]
            canonical='https://announcements.bybit.com/en/article/'+tail
            if canonical not in candidates:
                candidates[canonical]={'url':canonical,'discovered_in':url,'status':'unreviewed_candidate',
                                       'published_at':None,'effective_at':None,'market_classification':'unconfirmed',
                                       'no_event_imported':True}
            count+=1
        sources.append({'url':url,'sha256':digest,'snapshot_path':str(snapshot.resolve()),'candidate_links':count})
        print(json.dumps({'index_page':page,'candidate_links':count}),flush=True)
        time.sleep(0.2)
    output=Path('.local/state/historical-source-inventory.json')
    output.write_text(json.dumps({'captured_at':datetime.now(UTC).isoformat(),'sources':sources,
              'candidates':list(candidates.values()),'index_completeness_proven':False,
              'events_imported':0,'live_eligible':False},indent=2))
    print(json.dumps({'unique_candidates':len(candidates),'events_imported':0,'index_completeness_proven':False}))


if __name__=='__main__':
    main()
