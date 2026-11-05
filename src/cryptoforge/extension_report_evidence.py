"""Read-only verification of the complete registered extension result grid."""
import json,sqlite3
from pathlib import Path
from datetime import datetime
from cryptoforge.research_attempts import identity,encoded
from cryptoforge.training_snapshot import load_runtime_sources


def verify_extension_report(report,ledger_path):
    manifest=report['manifest'];study=report['study_sha256']
    if identity(manifest)!=study or manifest['scope']!='catalog_extensions_fixed_vs_atr_development':
        raise ValueError('original registered extension scope required')
    load_runtime_sources(manifest['runtime_source_bundle'],manifest['implementation_hashes'])
    grid={identity(candidate) for candidate in manifest['grid']}
    results={identity(result['candidate']):result for result in report['results']}
    if len(results)!=len(report['results']) or set(results)!=grid or report['completed_configurations']!=len(grid):
        raise ValueError('complete unique extension result grid required')
    db=sqlite3.connect(Path(ledger_path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        db.execute('BEGIN')
        original=db.execute('SELECT payload,observed_at FROM studies WHERE id=?',(study,)).fetchone()
        if original is None or original[0]!=encoded(manifest):raise ValueError('extension manifest differs from immutable registry')
        for key,result in results.items():
            saved=db.execute('SELECT status,payload,observed_at,completed_at FROM attempts WHERE study=? AND configuration=?',(study,key)).fetchone()
            if saved is None or saved[:2]!=('completed',encoded(result)):raise ValueError('extension result differs from completed attempt')
            stamps=[datetime.fromisoformat(stamp) for stamp in (original[1],saved[2],result['execution_started_at'],result['execution_finished_at'],saved[3])]
            if any(stamp.tzinfo is None for stamp in stamps) or stamps!=sorted(stamps):raise ValueError('execution must follow observed reservation')
            if result['study_sha256']!=study or result['live_promotion_allowed'] is not False:
                raise ValueError('research-only extension outcome required')
    finally:db.close()
    return {'registered_results_verified':True,'verified_configurations':len(grid),'ledger_modified':False,'live_promotion_allowed':False}
