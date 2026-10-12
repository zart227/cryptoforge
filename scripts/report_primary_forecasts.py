"""Report prospective primary price diagnostics, never select or publish a model."""
from datetime import UTC,datetime
import json,os
from pathlib import Path
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.primary_forecast_report import primary_forecast_report
from cryptoforge.atomic_reports import write_json_report


def main():
    memory=PrimaryForecastMemory(Path(os.environ.get('CRYPTOFORGE_PRIMARY_FORECAST_LEDGER','.local/state/primary-forecast-memory.sqlite')))
    result=primary_forecast_report(memory,as_of=datetime.now(UTC))
    write_json_report(Path('.local/state/primary-forecast-quality-report.json'),result)
    print(json.dumps(result))


if __name__=='__main__':main()
