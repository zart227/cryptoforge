"""Audit known execution filters without treating partial evidence as certification."""
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from cryptoforge.instrument_history import InstrumentEvent, state_at, timestamp

MARKET_REQUIRED_FIELDS = frozenset({'minimum_quantity','minimum_order_value_api',
                                    'quantity_step','tick_size','maximum_market_quantity'})


def load_fact_events(path: Path) -> tuple[dict, list[InstrumentEvent]]:
    ledger=json.loads(path.read_bytes())
    if ledger.get('conflicting_numeric_facts'):
        raise ValueError('conflicting numeric history must be reviewed')
    verified_sources=set();events=[]
    for fact in ledger['facts']:
        semantic={key:fact[key] for key in ('symbol','kind','effective_at','values','venue','market')}
        digest=hashlib.sha256(json.dumps(semantic,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=fact['fact_id']:raise ValueError('fact ledger semantic checksum mismatch')
        if not fact['source_evidence']:raise ValueError('historical fact has no source evidence')
        for evidence in fact['source_evidence']:
            event=InstrumentEvent(**{key:evidence[key] for key in InstrumentEvent.__dataclass_fields__ if key in evidence})
            event.validate()
            if (event.symbol,event.kind,timestamp(event.effective_at).astimezone(UTC).isoformat(),
                event.values,event.venue,event.market)!=(fact['symbol'],fact['kind'],fact['effective_at'],
                                                        fact['values'],fact['venue'],fact['market']):
                raise ValueError('historical fact differs from its evidence')
            source=(evidence['snapshot_path'],event.source_sha256)
            if source not in verified_sources:
                if hashlib.sha256(Path(source[0]).read_bytes()).hexdigest()!=source[1]:
                    raise ValueError('historical source checksum mismatch')
                verified_sources.add(source)
            events.append(event)
    directory=path.parent.parent/'archive-stage1'/'sources'
    for record in ledger.get('source_coverage_gaps',[])+ledger.get('unconfirmed_sources',[]):
        digest=record['source_sha256']
        candidates=[directory/'captured'/(digest+'.html'),directory/'inventory-captured'/(digest+'.html')]
        source=next((candidate for candidate in candidates if candidate.exists()),None)
        if source is None or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise ValueError('coverage limitation source checksum mismatch')
    return ledger,events


def execution_coverage(events: list[InstrumentEvent], symbols: list[str], *,
                       start: datetime, end: datetime) -> dict:
    if start.tzinfo is None or end.tzinfo is None or start>=end:
        raise ValueError('ordered timezone-aware coverage range required')
    if not symbols or len(set(symbols))!=len(symbols):
        raise ValueError('nonempty unique symbol scope required')
    grouped=defaultdict(list)
    for event in events:
        event.validate();grouped[event.symbol].append(event)
    segments=[];known_seconds=defaultdict(Decimal);total_seconds=Decimal(0)
    for symbol in symbols:
        selected=grouped[symbol]
        boundaries={start,end}
        for event in selected:
            activation=max(timestamp(event.effective_at),timestamp(event.announced_at))
            if start<activation<end:boundaries.add(activation)
        ordered=sorted(boundaries)
        for left,right in zip(ordered,ordered[1:]):
            state=state_at(selected,symbol,left)
            missing=sorted(MARKET_REQUIRED_FIELDS-set(state['rules']))
            duration=Decimal(str((right-left).total_seconds()));total_seconds+=duration
            for field in MARKET_REQUIRED_FIELDS:
                if field in state['rules']:known_seconds[field]+=duration
            segments.append({'symbol':symbol,'start':left.isoformat(),'end_exclusive':right.isoformat(),
                'availability':state['availability'],'rules':state['rules'],
                'rule_event_ids':state['rule_event_ids'],'missing_required_market_fields':missing,
                'known_unavailable_blocks_entry':state['known_unavailable_blocks_entry'],
                'all_required_numeric_fields_observed':not missing,
                'can_certify_historical_execution':False})
    return {'schema_version':'historical-execution-coverage-v1','start':start.isoformat(),
        'end_exclusive':end.isoformat(),'symbols':symbols,'segments':segments,
        'required_market_fields':sorted(MARKET_REQUIRED_FIELDS),
        'last_documented_value_fraction_of_symbol_time':{field:format(known_seconds[field]/total_seconds,'f')
                                              for field in sorted(MARKET_REQUIRED_FIELDS)},
        'segments_with_all_numeric_fields':sum(row['all_required_numeric_fields_observed'] for row in segments),
        'certified_execution_segments':0,'can_certify_historical_execution':False,
        'numeric_presence_is_not_exhaustive_change_history':True,
        'live_eligible':False}
