"""Bounded read-only calibration report using the original observed model freeze."""
import argparse,json
from datetime import UTC,datetime
from pathlib import Path
from contextlib import closing
from cryptoforge.feature_migration_study import FeatureMigrationStudy
from cryptoforge.primary_forecast_memory import PrimaryForecastMemory
from cryptoforge.migration_calibration import evaluate_migration_rows
from cryptoforge.classifier_diagnostics import probability_diagnostics
from cryptoforge.atomic_reports import write_json_report
from cryptoforge.source_contract import source_hashes
from cryptoforge.training_snapshot import save_runtime_sources,_save_raw


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('existing observed report is immutable; choose a new output')
    receipt=json.loads(args.protocol.read_bytes());root=args.protocol.parent.parent
    protocol=FeatureMigrationStudy(root/'registry.sqlite').verified_protocol(receipt)
    memory=PrimaryForecastMemory(args.protocol.parent/'price-forecasts.sqlite')
    now=datetime.now(UTC);rows=[]
    with closing(memory.iter_labeled_asof(as_of=now)) as items:
        for row in items:
            if len(rows)>=10000:raise ValueError('calibration snapshot exceeds bounded report')
            rows.append(row)
    artifact=json.loads(protocol['artifact_payload'])
    rate=artifact['probability_diagnostics']['long']['train']['train_positive_rate']
    dependencies={'evaluator':evaluate_migration_rows,'diagnostics':probability_diagnostics,'runner':Path(__file__).resolve()}
    hashes=source_hashes(dependencies)
    bundle=save_runtime_sources(args.output.parent/'calibration-runtime',dependencies,hashes)
    raw=json.dumps(rows,sort_keys=True,separators=(',',':')).encode()
    reference=_save_raw(args.output.parent/'calibration-inputs',raw)
    report=evaluate_migration_rows(rows,protocol_sha=receipt['protocol_sha256'],artifact_sha=protocol['artifact_sha256'],
        train_positive_rate=rate,frozen_at=datetime.fromisoformat(protocol['observed_at']),as_of=now,pairs=protocol['pairs'],threshold=protocol['threshold'])
    report.update(input_snapshot=reference,implementation_hashes=hashes,runtime_source_bundle=bundle,
        diagnostic_design_preregistered=False,baseline_origin='original_frozen_training_artifact_not_evaluation_prevalence')
    write_json_report(args.output,report)
    print(json.dumps({'endpoint_count':report['endpoint_count'],'all':report['diagnostics'].get('all')}))


if __name__=='__main__':main()
