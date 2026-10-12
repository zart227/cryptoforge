"""Merge strictly source-backed explicit facts; retain provenance and unresolved gaps."""
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path

from cryptoforge.instrument_history import InstrumentEvent,timestamp


def main():
    base=json.loads(Path('.local/state/instrument-history.json').read_text())
    queue=json.loads(Path('.local/state/historical-event-queue.json').read_text())
    proofs=json.loads(Path('.local/state/listing-pair-evidence.json').read_text())['results']
    source_reviews={r['url']:r for r in json.loads(Path('.local/state/historical-source-review.json').read_text())['records']}
    raw_events=list(base['events'])+list(queue['event_proposals'])
    supplemental={}
    resolved_quote_urls=set()
    for proof in proofs:
        if not proof.get('pair_confirmed'):continue
        payload=Path(proof['snapshot_path']).read_bytes()
        if hashlib.sha256(payload).hexdigest()!=proof['source_sha256']:raise ValueError('pair proof checksum mismatch')
        source=source_reviews[proof['url']]
        announced=timestamp(source['published_at'])
        if announced.hour==announced.minute==announced.second==0:
            from datetime import timedelta
            announced+=timedelta(days=1)
        event=InstrumentEvent(proof['symbol'],'listing',proof['effective_at'],announced.isoformat(),
                proof['url'],source['source_sha256'],{},evidence_scope='token_listing_plus_historical_spot_pair_evidence')
        event.validate();row={**event.__dict__,'event_id':event.event_id}
        raw_events.append(row);supplemental[event.event_id]=proof;resolved_quote_urls.add(proof['url'])
    facts={};source_count={}
    for raw in raw_events:
        fields={key:raw[key] for key in InstrumentEvent.__dataclass_fields__ if key in raw}
        event=InstrumentEvent(**fields);event.validate()
        source=event.source_url
        # Every HTML source must exist and match its immutable content digest.
        candidates=[Path('.local/archive-stage1/sources/captured')/(event.source_sha256+'.html'),
                    Path('.local/archive-stage1/sources/inventory-captured')/(event.source_sha256+'.html')]
        file=next((p for p in candidates if p.exists()),None)
        if file is None or hashlib.sha256(file.read_bytes()).hexdigest()!=event.source_sha256:
            raise ValueError('event source unavailable or changed')
        semantic={'symbol':event.symbol,'kind':event.kind,'effective_at':timestamp(event.effective_at).astimezone(UTC).isoformat(),
                  'values':event.values,'venue':event.venue,'market':event.market}
        fact_id=hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        evidence={**event.__dict__,'event_id':event.event_id,'snapshot_path':str(file.resolve())}
        if event.event_id in supplemental:evidence['pair_evidence']=supplemental[event.event_id]
        fact=facts.setdefault(fact_id,{**semantic,'fact_id':fact_id,'source_evidence':[]})
        if event.event_id not in {e['event_id'] for e in fact['source_evidence']}:
            fact['source_evidence'].append(evidence)
        source_count[source]=True
    conflicts={}
    for fact in facts.values():
        for field,value in fact['values'].items():
            key=(fact['symbol'],fact['effective_at'],field)
            conflicts.setdefault(key,set()).add(value)
    conflict_rows=[{'symbol':k[0],'effective_at':k[1],'field':k[2],'values':sorted(v)} for k,v in conflicts.items() if len(v)>1]
    result={'schema_version':'historical-fact-ledger-v1','captured_at':datetime.now(UTC).isoformat(),
            'facts':list(facts.values()),'source_count':len(source_count),'conflicting_numeric_facts':conflict_rows,
            'pending_source_reviews':[r for r in queue['source_reviews'] if r['status'].startswith('pending') and r['url'] not in resolved_quote_urls],
            'source_coverage_gaps':[r for r in queue['source_reviews'] if r.get('coverage_gap')],
            'unconfirmed_sources':[r for r in queue['source_reviews'] if r['status']=='market_or_body_unconfirmed'],
            'coverage':'partial_source_backed_observed_index_history','baseline_rule_coverage_complete':False,
            'historical_page_revisions_verified':False,'live_eligible':False}
    Path('.local/state/historical-fact-ledger.json').write_text(json.dumps(result,indent=2))
    from collections import Counter
    print(json.dumps({'facts':len(facts),'kinds':dict(Counter(f['kind'] for f in facts.values())),
                      'sources':len(source_count),'conflicts':len(conflict_rows),
                      'pending_sources':len(result['pending_source_reviews']),
                      'documented_coverage_gaps':len(result['source_coverage_gaps']),
                      'unconfirmed_sources':len(result['unconfirmed_sources']),'baseline_complete':False}))


if __name__=='__main__':main()
