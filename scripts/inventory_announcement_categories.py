"""Discover study-period source candidates from official paginated categories."""
from datetime import datetime,UTC
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request,urlopen

START=int(datetime(2025,10,1,tzinfo=UTC).timestamp());END=int(datetime(2026,10,1,tzinfo=UTC).timestamp())
ROOT=Path('.local/archive-stage1/sources/category-indexes')
OUTPUT=Path('.local/state/historical-category-inventory.json')


def relevant_title(title):
    title=title.casefold()
    if any(t in title for t in ('perpetual','futures','alpha','convert','pre-market','p2p')):return False
    return ('delist' in title or ('spot' in title and ('list' in title or 'tick size' in title or 'trading pair' in title or 'launch' in title)) or
            any(t in title for t in ('minimum order','minimum single order','maximum order','maximum single order')))


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    inventory=Path('.local/state/historical-source-inventory.json')
    original=json.loads(inventory.read_text())
    candidates={c['url']:c for c in original['candidates']}
    previous=json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {}
    pages=list(previous.get('pages',[]))
    completed={c['category']:c for c in previous.get('categories',[]) if c['stop_reason'] in {'passed_study_start','end_of_index'}}
    categories=[]
    for category in ('delistings','new_crypto','latest_bybit_news',''):
        label=category or 'all'
        if label in completed:
            categories.append(completed[label]);continue
        prior=[p for p in pages if p['category']==label]
        start_page=max((p['page'] for p in prior),default=0)+1
        seen=set();summary={'category':label,'stop_reason':'page_budget_reached','pages':start_page-1}
        for page in range(start_page,201):
            url='https://announcements.bybit.com/en/?'+urlencode({'category':category,'page':page})
            raw=urlopen(Request(url,headers={'User-Agent':'CryptoForge official-source-inventory'}),timeout=20).read()
            match=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',raw.decode(),re.S)
            if not match:raise ValueError('announcement index has no structured data')
            props=json.loads(match.group(1))['props']['pageProps']
            if int(props.get('initialPage',-1))!=page:raise ValueError('pagination parameter ignored')
            entity=props['articleInitEntity'];rows=entity['list']
            signature=tuple(row['objectID'] for row in rows)
            if signature in seen:
                summary['stop_reason']='repeated_page_no_coverage_claim';break
            seen.add(signature)
            digest=hashlib.sha256(raw).hexdigest();snapshot=ROOT/(digest+'.html')
            if not snapshot.exists():snapshot.write_bytes(raw)
            dates=[];added=0
            for row in rows:
                published=int(row.get('date_timestamp') or row.get('publish_time') or 0)
                if not row.get('is_top') and published:dates.append(published)
                if not START<=published<END or not relevant_title(row.get('title','')):continue
                tail=row['url'].split('/article/',1)[-1].split('?',1)[0]
                target='https://announcements.bybit.com/en/article/'+tail
                if target not in candidates:
                    candidates[target]={'url':target,'discovered_in':url,'status':'unreviewed_candidate',
                        'index_publication_timestamp':published,'index_object_id':row['objectID'],
                        'published_at':None,'effective_at':None,'market_classification':'unconfirmed','no_event_imported':True}
                    added+=1
            pages.append({'category':category or 'all','page':page,'url':url,'sha256':digest,
                         'snapshot_path':str(snapshot.resolve()),'index_total':entity['total'],
                         'items':len(rows),'oldest_nonpinned_timestamp':min(dates) if dates else None,
                         'newest_nonpinned_timestamp':max(dates) if dates else None,'new_candidates':added})
            summary['pages']=page
            if added or page%10==0:
                print(json.dumps({'category':category or 'all','page':page,'new_candidates':added,'candidate_total':len(candidates)}),flush=True)
            if not rows:
                summary['stop_reason']='end_of_index';break
            if dates and max(dates)<START:
                summary['stop_reason']='passed_study_start';break
            if page*len(rows)>=int(entity['total']):
                summary['stop_reason']='end_of_index';break
            time.sleep(.2)
        categories.append(summary)
        OUTPUT.write_text(json.dumps({'captured_at':datetime.now(UTC).isoformat(),'pages':pages,'categories':categories,
            'candidate_total':len(candidates),'index_completeness_proven':False,
            'scope':'observed_paginated_indexes_not_a_revision_archive','events_imported':0},indent=2))
        inventory.write_text(json.dumps({**original,'candidates':list(candidates.values()),
            'additional_category_inventory':str(OUTPUT),'index_completeness_proven':False},indent=2))
    print(json.dumps({'categories':categories,'total_candidates':len(candidates),'events_imported':0}))


if __name__=='__main__':main()
