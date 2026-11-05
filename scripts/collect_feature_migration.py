"""Collect fixed-model/ML-free future price comparisons; no broker orders."""
import argparse,json,time,sqlite3
from datetime import UTC,datetime,timedelta
from decimal import Decimal
from pathlib import Path
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.feature_migration_study import FeatureMigrationStudy
from cryptoforge.market_data import BybitPublicClient
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.supabase_executor import CandleRow
from cryptoforge.primary_forecast_report import primary_forecast_report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--protocol',type=Path,required=True)
    args=parser.parse_args(argv);receipt=json.loads(args.protocol.read_bytes())
    root=args.protocol.parent;study=FeatureMigrationStudy(root.parent/'registry.sqlite')
    study.verified_protocol(receipt)
    memory=PrimaryForecastMemory(root/'price-forecasts.sqlite');client=BybitPublicClient(timeout=2,max_retries=0)
    started=time.monotonic();counts={};errors={};processed=0;matured=memory.matured_batch(as_of=datetime.now(UTC),limit=40)
    for pair in receipt['protocol']['pairs']:
        if time.monotonic()-started>20:break
        processed+=1
        try:
            bars=client.get_klines(pair.replace('/',''),interval='5',limit=500)
            observed=datetime.now(UTC)
            rows=[CandleRow(pair,bar.symbol,datetime.fromtimestamp(bar.start_ms/1000,UTC),
                Decimal(bar.open),Decimal(bar.high),Decimal(bar.low),Decimal(bar.close),Decimal(bar.volume),
                cache_observed_at=observed) for bar in bars]
            rows.sort(key=lambda row:row.open_time)
            study.verified_protocol(receipt)
            endpoints={row.open_time+timedelta(minutes=5):row for row in rows}
            for forecast in (forecast for forecast in matured if forecast['pair']==pair):
                if time.monotonic()-started>20:break
                with sqlite3.connect(memory.path.resolve().as_uri()+'?mode=ro',uri=True) as db:
                    table=db.execute("SELECT 1 FROM sqlite_master WHERE name='primary_forecast_outcomes'").fetchone()
                    done=table and db.execute('SELECT 1 FROM primary_forecast_outcomes WHERE forecast=? LIMIT 1',(forecast['forecast_id'],)).fetchone()
                if done:continue
                endpoint=endpoints.get(datetime.fromisoformat(forecast['target_information_end']))
                if endpoint is None:
                    counts['missing_mature_endpoint']=counts.get('missing_mature_endpoint',0)+1;continue
                memory.record_outcome(forecast['forecast_id'],endpoint)
                counts['mature_price_endpoint_recorded']=counts.get('mature_price_endpoint_recorded',0)+1
            result=study.record(receipt,rows,source_observed_at=observed,memory=memory)
            counts[result['status']]=counts.get(result['status'],0)+1
        except Exception as exc:errors[pair]=type(exc).__name__
    result={'as_of':datetime.now(UTC).isoformat(),'statuses':counts,'errors':errors,
        'declared_pairs':len(receipt['protocol']['pairs']),'processed_pairs':processed,
        'scope':'paired_future_price_diagnostics_no_cash_fills','live_promotion_allowed':False}
    write_json_report(root/'collection-status.json',result)
    report=primary_forecast_report(memory,as_of=datetime.now(UTC),maximum_rows=10000)
    report['migration_protocol_sha256']=receipt['protocol_sha256']
    write_json_report(root/'price-comparison-report.json',report)
    print(json.dumps(result));return 0


if __name__=='__main__':raise SystemExit(main())
