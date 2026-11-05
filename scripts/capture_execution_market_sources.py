"""Observe current rules and displayed books, never backfill or simulate fills."""
import argparse,json,shutil
from datetime import UTC,datetime
from pathlib import Path
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.paper_market import normalize_market
from cryptoforge.paper_wallet import _number
from cryptoforge.training_snapshot import _save_raw,save_runtime_sources
from cryptoforge.source_contract import source_hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair',action='append',required=True)
    parser.add_argument('--directory',type=Path,default=Path('.local/execution-market-sources'))
    args=parser.parse_args()
    pairs=sorted(set(args.pair))
    if not pairs or len(pairs)>20 or any(not pair.endswith('/USDT') or len(pair.split('/'))!=2 for pair in pairs):
        parser.error('bounded explicit USDT basket required')
    if shutil.disk_usage('.').free<(2048+2)*1024**2:
        print(json.dumps({'status':'deferred_disk_reserve'}));return
    dependencies={'normalizer':normalize_market,'numeric_contract':_number,'runner':Path(__file__).resolve()}
    hashes=source_hashes(dependencies)
    runtime=save_runtime_sources(args.directory/'runtime',dependencies,hashes)
    client=BybitPublicClient(timeout=2,max_retries=0)
    receipts=[];errors={}
    for pair in pairs:
        try:
            started=datetime.now(UTC)
            instrument=client._get_json('/v5/market/instruments-info',{'category':'spot','symbol':pair.replace('/','')})
            instrument_at=datetime.now(UTC)
            book=client._get_json('/v5/market/orderbook',{'category':'spot','symbol':pair.replace('/',''),'limit':1})
            book_at=datetime.now(UTC)
            quote,filters=normalize_market(pair,instrument,book,instrument_at=instrument_at,book_at=book_at)
            raw=lambda payload:json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
            instrument_source=_save_raw(args.directory/'inputs',raw(instrument))
            book_source=_save_raw(args.directory/'inputs',raw(book))
            receipt={'schema_version':'observed-execution-market-sources-v1','pair':pair,
                'request_started_at':started.isoformat(),'observed_at':book_at.isoformat(),
                'instrument_source':instrument_source,'orderbook_source':book_source,
                'quote':quote,'filters':filters,'implementation_hashes':hashes,'runtime_source_bundle':runtime,
                'scope':'current_observed_rules_and_displayed_top_of_book',
                'historical_rule_change_times_known':False,'displayed_depth_proves_fill':False,
                'fees_verified':False,'partial_fill_model_verified':False,'live_promotion_allowed':False}
            ref=_save_raw(args.directory/'receipts',raw(receipt))
            receipts.append({'pair':pair,'receipt':ref})
        except Exception as exc:errors[pair]=type(exc).__name__
    print(json.dumps({'observed_pairs':len(receipts),'receipts':receipts,'errors':errors,'historical_backfill_performed':False}))


if __name__=='__main__':main()
