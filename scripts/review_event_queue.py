"""Validate explicit source-local dates/sections; leave ambiguous notices pending."""
from dataclasses import asdict
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path
from collections import Counter

from cryptoforge.announcement_sources import extract_article
from cryptoforge.historical_event_review import reviewed_proposals


def main():
    records=json.loads(Path('.local/state/historical-source-review.json').read_text())['records']
    reviews=[];facts={};semantic={}
    for record in records:
        if not record.get('snapshot_path'):
            reviews.append({'url':record['url'],'status':'source_unavailable','events':[]});continue
        raw=Path(record['snapshot_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['source_sha256']:raise ValueError('captured source checksum mismatch')
        parsed=extract_article(raw)
        try:result=reviewed_proposals(parsed,record['url'],record['source_sha256'])
        except (ValueError,TypeError) as exc:result={'status':'pending_unsupported_source_format','events':[],'reason':str(exc)}
        payload={**result,'url':record['url'],'source_sha256':record['source_sha256'],
                 'events':[{**asdict(event),'event_id':event.event_id} for event in result['events']]}
        reviews.append(payload)
        for event in result['events']:
            key=(event.symbol,event.kind,event.effective_at,json.dumps(event.values,sort_keys=True))
            semantic.setdefault(key,[]).append(event.event_id)
            facts[event.event_id]={**asdict(event),'event_id':event.event_id}
    output={'schema_version':'source-event-review-v1','reviewed_at':datetime.now(UTC).isoformat(),
            'source_reviews':reviews,'event_proposals':list(facts.values()),
            'status_counts':dict(Counter(r['status'] for r in reviews)),
            'duplicate_semantic_groups':sum(len(ids)>1 for ids in semantic.values()),
            'events_admitted_to_registry':0,'can_certify_historical_execution':False,'live_eligible':False}
    Path('.local/state/historical-event-queue.json').write_text(json.dumps(output,indent=2))
    print(json.dumps({'sources':len(reviews),'proposals':len(facts),'status_counts':output['status_counts'],
                      'duplicate_semantic_groups':output['duplicate_semantic_groups']}))


if __name__=='__main__':main()
