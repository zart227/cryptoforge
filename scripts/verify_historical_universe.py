"""Replay a historical selection from hashed, strictly prior-day evidence."""
from datetime import datetime, UTC
from pathlib import Path
import hashlib
import json
import re

from cryptoforge.announcement_sources import article_tables
from cryptoforge.instrument_history import timestamp
from cryptoforge.universe_evidence import verify_probe


def main():
    source=Path('.local/archive-stage1/sources/minimum-jan2025.next.json')
    decision=Path('.local/state/historical-universe-20251001.json')
    baseline=source.read_bytes();saved=decision.read_bytes();document=json.loads(saved)
    article=json.loads(baseline)['articleDetail'];protocol=document['protocol']
    at=timestamp(protocol['as_of'])
    if timestamp(article['date'])>=at or at.hour or at.minute or at.second or at.microsecond:
        raise ValueError('dated baseline and UTC midnight selection required')
    if (protocol['minimum_prior_turnover_usdt'],protocol['minimum_prior_range_fraction'],
        protocol['maximum_selected_pairs'],protocol['ranking'],protocol['current_universe_used'],
        protocol['future_returns_used']) != ('1000000','0.01',20,'prior_day_turnover_only',False,False):
        raise ValueError('selection protocol mismatch')
    candidates=sorted({row[0] for row in article_tables(article)
                       if row and re.fullmatch(r'[A-Z0-9]+USDT',row[0])})
    results=document['results']
    if candidates!=protocol['candidate_symbols'] or sorted(row['symbol'] for row in results)!=candidates:
        raise ValueError('baseline candidate coverage mismatch')
    unavailable=[row for row in results if row['status']=='probe_unavailable']
    if any(row.get('liquidity_eligible') for row in unavailable):
        raise ValueError('unavailable evidence cannot be eligible')
    verified=[verify_probe(row,as_of_ms=int(at.timestamp()*1000)) for row in results
              if row['status']!='probe_unavailable']
    selected=[row['symbol'] for row in sorted((r for r in verified if r['eligible']),
                                             key=lambda r:(-r['turnover'],r['symbol']))[:20]]
    if selected!=document['selected_symbols']:raise ValueError('selection replay mismatch')
    report={'verified_at':datetime.now(UTC).isoformat(),'as_of':at.isoformat(),
            'baseline_sha256':hashlib.sha256(baseline).hexdigest(),
            'decision_sha256':hashlib.sha256(saved).hexdigest(),'verified_probes':len(verified),
            'unavailable_probes':len(unavailable),'candidate_count':len(candidates),
            'eligible':sum(row['eligible'] for row in verified),'selected_symbols':selected,
            'replay_matches':True,'scope':'partial_historical_baseline','live_eligible':False}
    output=Path('.local/state/historical-universe-evidence-quality.json')
    output.write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
