"""Capture public current Spot rules for future historical audits, not old backfills."""
from datetime import UTC,datetime
import json,shutil
from pathlib import Path
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.instrument_observation_memory import InstrumentObservationMemory


def main():
    if shutil.disk_usage('.').free<2048*1024**2:
        print(json.dumps({'status':'deferred_disk_reserve','past_history_reconstructed':False}));return
    started=datetime.now(UTC);client=BybitPublicClient(timeout=8,max_retries=1)
    payload=client._get_json('/v5/market/instruments-info',{'category':'spot'})
    observed=datetime.now(UTC)
    receipt=InstrumentObservationMemory(Path('.local/archive-instruments')).remember(payload,
        request_started_at=started,response_observed_at=observed)
    print(json.dumps({'status':'public_spot_rules_observed','symbols':receipt['symbols_observed'],
        'observed_at':receipt['observed_at'],'response_has_more_pages':receipt['response_has_more_pages'],
        'can_certify_historical_execution':False,'past_history_reconstructed':False}))


if __name__=='__main__':main()
