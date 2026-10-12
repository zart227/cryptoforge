"""Capture candidate article metadata and review queue without inferring events."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

from cryptoforge.announcement_sources import extract_article,classify_article
from cryptoforge.instrument_history import timestamp

START=datetime(2025,10,1,tzinfo=UTC);END=datetime(2026,10,1,tzinfo=UTC)
ROOT=Path('.local/archive-stage1/sources/inventory-captured')
OUTPUT=Path('.local/state/historical-source-review.json')


def review(candidate):
    url=candidate['url'];record={'url':url,'events_imported':0}
    try:
        response=urlopen(Request(url,headers={'User-Agent':'CryptoForge historical-source-review'}),timeout=15)
        with response:
            final=response.geturl();parts=urlparse(final)
            if parts.hostname not in {'announcements.bybit.com','announcements.bybit.global'} or not parts.path.startswith('/en/article/'):
                raise ValueError('redirect is outside supported global English sources')
            raw=response.read()
        digest=hashlib.sha256(raw).hexdigest();path=ROOT/(digest+'.html')
        if not path.exists():path.write_bytes(raw)
        article=extract_article(raw)
        published=timestamp(article['published_at'])
        classification=classify_article(article['title'],article['body'])
        record.update(source_sha256=digest,snapshot_path=str(path.resolve()),final_url=final,
                      title=article['title'],published_at=article['published_at'],
                      publication_in_study_range=START<=published<END,
                      market_classification=classification,body_available=article['body_available'],
                      status='outside_study_publication_range' if not START<=published<END else classification,
                      historical_revision_verified=False)
    except Exception as exc:
        record.update(status='unavailable_requires_review',error=f'{type(exc).__name__}: {exc}')
    return record


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    inventory=json.loads(Path('.local/state/historical-source-inventory.json').read_text())
    previous=json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    existing={r['url']:r for r in previous.get('records',[]) if r['status']!='unavailable_requires_review'}
    for record in existing.values():
        raw=Path(record['snapshot_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['source_sha256']:
            raise ValueError('captured source checksum mismatch')
        article=extract_article(raw)
        classification=classify_article(article['title'],article['body'])
        record['market_classification']=classification
        record['status']=classification if record['publication_in_study_range'] else 'outside_study_publication_range'
    records=list(existing.values())
    pending=[c for c in inventory['candidates'] if c['url'] not in existing]
    def persist():
        OUTPUT.write_text(json.dumps({'captured_at':datetime.now(UTC).isoformat(),'study_start':START.isoformat(),
            'study_end':END.isoformat(),'records':sorted(records,key=lambda r:r['url']),
            'index_completeness_proven':False,'events_imported':sum(r.get('events_imported',0) for r in records),'live_eligible':False},indent=2))
    persist()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(review,c):c for c in pending}
        for future in as_completed(futures):
            records.append(future.result());persist()
            if len(records)%10==0:print(json.dumps({'reviewed':len(records),'total':len(inventory['candidates'])}),flush=True)
    from collections import Counter
    counts=dict(Counter(r['status'] for r in records))
    print(json.dumps({'reviewed':len(records),'status_counts':counts,'events_imported':sum(r.get('events_imported',0) for r in records)}))


if __name__=='__main__':
    main()
