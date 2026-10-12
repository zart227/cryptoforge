"""Collect future candle diagnostics; no orders, fitting or cash labels."""
from datetime import UTC,datetime
import argparse,json,os,tempfile,hashlib
from pathlib import Path
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.primary_forecast_outcomes import collect_primary_forecast_outcomes
from cryptoforge.supabase_executor import SupabaseMarketReader
from cryptoforge.supabase_market import SupabaseRestClient


def original_policy_resolver(directory):
    cache={}
    def resolve(sha):
        if sha in cache:return cache[sha]
        result=None
        for path in directory.glob('pure-python-logistic-*'+sha[:12]+'.json'):
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=sha:continue
            artifact=json.loads(raw);config=artifact.get('config') or {}
            if (artifact.get('model_family')!='pure-python-logistic' or artifact.get('feature_version')!='candle-v1'
                or config.get('timeframe','5m')!='5m' or config.get('horizon_candles',3)!=3
                or config.get('target_version','fixed-future-return-v1')!='fixed-future-return-v1'
                or config.get('min_label_return') is None or config.get('round_trip_cost') is None):continue
            result={'artifact_sha256':sha,'trained_at':artifact['trained_at'],
                'min_label_return':config['min_label_return'],'round_trip_cost':config['round_trip_cost']};break
        cache[sha]=result;return result
    return resolve


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maximum-forecasts',type=int,default=400)
    parser.add_argument('--maximum-pairs',type=int,default=20)
    parser.add_argument('--wall-seconds',type=float,default=20)
    args=parser.parse_args();now=datetime.now(UTC)
    path=Path(os.environ.get('CRYPTOFORGE_PRIMARY_FORECAST_LEDGER','.local/state/primary-forecast-memory.sqlite'))
    memory=PrimaryForecastMemory(path)
    if not memory.path.exists() or not memory.matured_batch(as_of=now,limit=1):
        report={'status':'waiting_for_mature_primary_forecasts','as_of':now.isoformat(),
            'cash_training_rows_added':0,'live_promotion_allowed':False}
    else:
        client=SupabaseRestClient.from_env(timeout_seconds=2)
        report=collect_primary_forecast_outcomes(memory,SupabaseMarketReader(client),as_of=now,
            maximum_forecasts=args.maximum_forecasts,maximum_pairs=args.maximum_pairs,wall_seconds=args.wall_seconds,
            policy_resolver=original_policy_resolver(Path('.local/models')))
    output=Path('.local/state/primary-forecast-outcome-report.json');output.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',dir=output.parent,delete=False) as stream:
            temporary=Path(stream.name);json.dump(report,stream,indent=2)
        os.replace(temporary,output)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    print(json.dumps(report))


if __name__=='__main__':main()
