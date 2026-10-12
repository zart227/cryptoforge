"""Source-backed partial Spot history. Unknowns never become today's rules."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from urllib.parse import urlparse

RULE_FIELDS={'minimum_quantity','minimum_order_value_api','minimum_order_value_non_api','quantity_step','tick_size',
             'maximum_market_quantity','maximum_limit_quantity','maximum_post_only_quantity'}


def timestamp(value: str) -> datetime:
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone-aware timestamp required')
    return result


@dataclass(frozen=True)
class InstrumentEvent:
    symbol: str
    kind: str
    effective_at: str
    announced_at: str
    source_url: str
    source_sha256: str
    values: dict
    venue: str = 'bybit_global'
    market: str = 'spot'
    evidence_scope: str = 'documented_event_partial_history'

    def validate(self):
        if self.venue!='bybit_global' or self.market!='spot':
            raise ValueError('global Spot history only; do not mix EU/derivatives')
        source=urlparse(self.source_url)
        if source.scheme!='https' or source.hostname not in {'announcements.bybit.com','announcements.bybit.global'} or not source.path.startswith('/en/article/'):
            raise ValueError('official global announcement source required')
        if self.kind not in {'listing','delisting','rule_change','availability_observation','suspension_observation'}:
            raise ValueError('unsupported historical event')
        if not self.symbol.isalnum() or not self.symbol.endswith('USDT'):
            raise ValueError('USDT symbol required')
        timestamp(self.effective_at);timestamp(self.announced_at)
        if len(self.source_sha256)!=64 or any(c not in '0123456789abcdef' for c in self.source_sha256):
            raise ValueError('source checksum required')
        if set(self.values)-RULE_FIELDS:
            raise ValueError('unknown rule fields')
        for value in self.values.values():
            amount=Decimal(value)
            if not amount.is_finite() or amount<=0:
                raise ValueError('finite positive rule value required')

    @property
    def event_id(self):
        return hashlib.sha256(json.dumps(self.__dict__,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def state_at(events: list[InstrumentEvent],symbol: str,at: datetime) -> dict:
    if at.tzinfo is None:
        raise ValueError('timezone-aware as-of time required')
    relevant=[]
    for event in events:
        event.validate()
        if event.symbol==symbol and timestamp(event.announced_at)<=at and timestamp(event.effective_at)<=at:
            relevant.append(event)
    relevant.sort(key=lambda event:(timestamp(event.effective_at),timestamp(event.announced_at),event.event_id))
    rules={};provenance={};availability='unknown'
    for event in relevant:
        if event.kind=='listing':
            availability='documented_listing'
        elif event.kind=='delisting':
            availability='documented_delisting'
        elif event.kind=='suspension_observation':
            availability='observed_suspended'
        elif event.kind=='availability_observation' and availability=='unknown':
            availability='observed_in_official_rule_table'
        for name,value in event.values.items():
            rules[name]=value;provenance[name]=event.event_id
    missing=sorted(RULE_FIELDS-set(rules))
    return {'symbol':symbol,'as_of':at.isoformat(),'availability':availability,'rules':rules,
            'rule_event_ids':provenance,'missing_rule_fields':missing,
            'can_certify_historical_execution':False,
            'coverage':'partial_no_exhaustive_change_or_revision_history',
            'known_delisting_blocks_entry':availability=='documented_delisting',
            'known_suspension_blocks_entry':availability=='observed_suspended',
            'known_unavailable_blocks_entry':availability in {'documented_delisting','observed_suspended'}}


def minimum_rule_table(article: dict) -> list[dict]:
    """Read the six-column API/non-API baseline without inferring qty steps."""
    from cryptoforge.announcement_sources import article_tables
    import re
    rows=article_tables(article)
    header=['Spot/Trading Pair','Before','Adjusted','Before',
            'Adjusted for Non-API Users','Adjusted for API Users']
    if len(rows)<4 or rows[2]!=header:
        raise ValueError('minimum-order table headers require review')
    result=[];seen=set()
    for row in rows[3:]:
        if not row or not re.fullmatch(r'[A-Z0-9]+USDT',row[0]):continue
        if len(row)!=6 or row[0] in seen:
            raise ValueError('incomplete or duplicate minimum-order row')
        values={'minimum_quantity':row[2],'minimum_order_value_non_api':row[4],
                'minimum_order_value_api':row[5]}
        if not all(Decimal(value).is_finite() and Decimal(value)>0 for value in values.values()):
            raise ValueError('invalid baseline minimum-order values')
        result.append({'symbol':row[0],'values':values});seen.add(row[0])
    if not result:raise ValueError('no USDT baseline rules')
    return result
