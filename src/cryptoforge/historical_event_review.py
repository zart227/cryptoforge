"""Strict source-local event proposals; ambiguous evidence stays pending."""
from datetime import datetime,UTC,timedelta
from decimal import Decimal,InvalidOperation
import re

from cryptoforge.announcement_sources import classify_article,article_tables
from cryptoforge.instrument_history import InstrumentEvent,timestamp

DATE_PATTERN=r'(?:\d{4}-\d{1,2}-\d{1,2}[ T](?:\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}\s*(?:AM|PM))|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\s*,?\s*(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)\s*UTC'
DATE_RE=re.compile(DATE_PATTERN,re.I)
TIME_FIRST_RE=re.compile(r'\b\d{1,2}(?::\d{2})?\s*(?:AM|PM)\s+UTC\s+on\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b',re.I)
PAIR_RE=re.compile(r'\b([A-Z0-9]{1,20})(?:\s*/\s*USDT|USDT)\b')


def explicit_utc(value: str) -> datetime:
    value=re.sub(r'\s+',' ',value.strip()).replace('Sept ','Sep ')
    first=re.fullmatch(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM)) UTC on (.+)',value,re.I)
    if first:value=first.group(2)+' '+first.group(1)+' UTC'
    value=re.sub(r'\bat\s+','',value,flags=re.I)
    value=re.sub(r'(\d)\s+(AM|PM)',r'\1\2',value,flags=re.I)
    for pattern in ('%b %d, %Y, %I:%M%p UTC','%b %d, %Y, %I%p UTC',
                    '%b %d, %Y, %H:%M UTC','%b %d, %Y %I:%M%p UTC','%b %d, %Y %I%p UTC',
                    '%b %d, %Y %H:%M UTC','%Y-%m-%d %H:%M:%S UTC','%Y-%m-%d %H:%M UTC','%Y-%m-%d %I%p UTC'):
        try:return datetime.strptime(value,pattern).replace(tzinfo=UTC)
        except ValueError:pass
    raise ValueError('unrecognized explicit UTC event time')


def reviewed_proposals(parsed: dict,source_url: str,source_sha256: str) -> dict:
    title=parsed['title'];body=re.sub(r'[\u200b*]+','',parsed['body']);article=parsed['article']
    classification=classify_article(title,body)
    if classification!='spot_source_pending_event_review':return {'status':classification,'events':[]}
    announced=timestamp(parsed['published_at'])
    if announced.hour==announced.minute==announced.second==0:announced+=timedelta(days=1)
    def event(symbol,kind,effective,values):
        result=InstrumentEvent(symbol,kind,effective.isoformat(),announced.isoformat(),source_url,source_sha256,values)
        result.validate();return result
    lower=title.casefold()
    if 'aed spot' in lower:
        pairs=re.findall(r'\b([A-Z0-9]+)\s*/\s*([A-Z0-9]+)\b',body)
        if pairs and all(quote=='AED' for _,quote in pairs):
            return {'status':'excluded_non_usdt_aed_pairs','events':[],
                    'scope_evidence_pairs':[base+'/'+quote for base,quote in pairs]}
    if 'spot trading suspended' in lower:
        pairs=sorted(set(pair+'USDT' for pair in PAIR_RE.findall(title)))
        if pairs and re.search(r'trading.+?(?:have been|has been).+?suspended',body,re.I):
            observations=[InstrumentEvent(pair,'suspension_observation',announced.isoformat(),
                announced.isoformat(),source_url,source_sha256,{},
                evidence_scope='publication_observation_not_suspension_start') for pair in pairs]
            for observation in observations:observation.validate()
            return {'status':'verified_suspension_observation','events':observations,
                    'effective_time_policy':'known_suspended_by_publication_actual_start_unknown'}
    limitation_fields=['maximum_market_quantity','maximum_limit_quantity','maximum_post_only_quantity']
    limitations={
        'enabling automated adjustments for selected spot trading parameters':
            ('unannounced_automatic_changes','2026-03-20',limitation_fields),
        'changes to maximum order size for limit and market orders':
            ('separate_limit_and_market_sizes_numeric_baselines_missing','2025-10-16',limitation_fields),
        'introduction of postonlymaxlimitordersize for spot trading rules':
            ('pair_specific_post_only_limit_replaces_universal_multiplier','2025-11-11',['maximum_post_only_quantity']),
        'update on the maximum single order quantity for spot trading pairs':
            ('external_spreadsheet_requires_historical_revision_evidence',None,limitation_fields),
    }
    if lower in limitations:
        reason,date,fields=limitations[lower]
        anchors={'2026-03-20':r'starting\s+Mar\s+20,\s+2026',
                 '2025-10-16':r'Starting\s+Oct\s+16,\s+2025',
                 '2025-11-11':r'Effective Date:\s*Nov\s+11,\s+2025'}
        if date and not re.search(anchors[date],body,re.I):
            return {'status':'pending_numeric_gap_date_review','events':[]}
        return {'status':'documented_numeric_history_gap','events':[],
                'coverage_gap':{'reason':reason,'fields':fields,'announced_at':announced.isoformat(),
                    'documented_start_date':date,'start_time_precision':'day_only' if date else 'unknown',
                    'scope':'global_spot_pairs','numeric_values_reconstructed':False}}
    # Scope-only review: these table formats can prove that a notice has no
    # USDT instruments without inventing effective dates or numeric rules.
    if any(label in lower for label in ('quantity precision','minimum order value','minimum single order')):
        rows=article_tables(article)
        data=[]
        for row in rows:
            if len(row)!=3 or not re.fullmatch(r'[A-Z0-9]{3,30}',row[0]):continue
            try:
                numbers=[Decimal(value) for value in row[1:]]
                if not all(value.is_finite() and value>0 for value in numbers):continue
            except InvalidOperation:continue
            data.append(row)
        if data and not any(row and row[0].replace('/','').replace(' ','').endswith('USDT') for row in rows):
            return {'status':'excluded_non_usdt_rule_table','events':[],
                    'scope_evidence_pairs':[row[0] for row in data]}
    if 'tick size' in lower:
        segment=body[:min(len(body),body.find('Please refer') if 'Please refer' in body else 1000)]
        dates=DATE_RE.findall(segment)+TIME_FIRST_RE.findall(segment)
        rows=article_tables(article)
        if len(dates)!=1 or not rows or rows[0]!=['Spot Pair','Tick Size (Before)','Tick Size (Adjusted)']:
            return {'status':'pending_tick_time_or_table_review','events':[]}
        effective=explicit_utc(dates[0]);events=[]
        for row in rows[1:]:
            if len(row)!=3: return {'status':'pending_tick_row_shape_review','events':[]}
            pair=row[0].replace('/','').replace(' ','')
            if not re.fullmatch(r'[A-Z0-9]+USDT',pair):continue
            try:
                if Decimal(row[1])<=0 or Decimal(row[2])<=0:raise ValueError('nonpositive tick')
            except (InvalidOperation,ValueError):return {'status':'pending_numeric_review','events':[]}
            events.append(event(pair,'rule_change',effective,{'tick_size':row[2]}))
        return {'status':'verified_explicit_tick_table','events':events,'evidence_anchor':dates[0]}
    if 'delist' in lower:
        if 'on-chain earn' in lower:return {'status':'excluded_non_spot_earn_notice','events':[]}
        title_pairs=re.findall(r'\b([A-Z0-9]+)\s*/\s*([A-Z0-9]+)\b',title)
        if title_pairs and all(quote!='USDT' for _,quote in title_pairs):
            return {'status':'excluded_non_usdt_pairs','events':[]}
        match=re.search(r'\bSpot\s*(?:[:\-•])?\s*Trading of\s+',body,re.I)
        if not match:
            match=re.search(r'\bSpot\s+Trading\s*[•:\-]?\s*Trading for\s+',body,re.I)
        if match:
            rest=body[match.end():]
            segment=re.split(r'\b(?:\d+\.\s*(?:Convert|Deposits|Withdrawals|DCA\s*Bot)\b|(?:Convert|Deposits|Withdrawals|DCA\s*Bot)\s*[:\-•])',rest,1,flags=re.I)[0]
        else:
            match=re.search(r'delist the following Spot trading pairs?\s+on\s+',body,re.I)
            if not match:return {'status':'pending_spot_delisting_section_review','events':[]}
            segment=re.split(r'Important notes',body[match.end():],1,flags=re.I)[0]
        dates=DATE_RE.findall(segment)
        pair_section=segment
        if not PAIR_RE.search(segment) and re.search(r'pairs listed above',segment,re.I):
            pair_section=body[:match.start()]
        symbols=sorted(set(pair+'USDT' for pair in PAIR_RE.findall(pair_section)))
        if len(dates)!=1:return {'status':'pending_delisting_time_review','events':[]}
        if not symbols:return {'status':'excluded_non_usdt_pairs','events':[]}
        effective=explicit_utc(dates[0])
        return {'status':'verified_explicit_spot_delisting','events':[event(pair,'delisting',effective,{}) for pair in symbols],
                'evidence_anchor':dates[0]}
    if 'list' in lower and 'spot' in lower:
        listings=list(re.finditer(r'\b([A-Z0-9]{1,20})\s*/\s*USDT\s+listing\s*:\s*',body,re.I))
        if not listings:
            listings=list(re.finditer(r'\b([A-Z0-9]{1,20})\s+listing\s*:\s*',body,re.I))
        if len(listings)!=1:return {'status':'pending_listing_line_review','events':[]}
        marker=listings[0];token=marker.group(1).upper()
        rest=body[marker.end():marker.end()+120];dates=DATE_RE.findall(rest)
        if not dates:return {'status':'pending_listing_time_review','events':[]}
        explicit_pair=bool(re.search(r'\b'+re.escape(token)+r'(?:\s*/\s*USDT|USDT)\b',body,re.I))
        if not explicit_pair:return {'status':'pending_listing_quote_pair_evidence','events':[],
                                     'token':token,'effective_at_candidate':explicit_utc(dates[0]).isoformat()}
        return {'status':'verified_explicit_spot_listing','events':[event(token+'USDT','listing',explicit_utc(dates[0]),{})],
                'evidence_anchor':dates[0]}
    return {'status':'pending_other_rule_or_scope_review','events':[]}
