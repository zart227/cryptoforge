"""Read-only comparison of research reports against completed ledger records."""
from pathlib import Path
import sqlite3

from cryptoforge.research_attempts import encoded, identity


def verify_registered_report(report, ledger_path):
    manifest = report['manifest']
    study = report['study_sha256']
    if identity(manifest) != study:
        raise ValueError('registered report study identity mismatch')
    db = sqlite3.connect(Path(ledger_path).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        original = db.execute('SELECT payload FROM studies WHERE id=?', (study,)).fetchone()
        if original is None or original[0] != encoded(manifest):
            raise ValueError('report manifest differs from registered study')
        grid = {identity(candidate) for candidate in manifest['grid']}
        results = {identity(result['parameters']): result for result in report['results']}
        if (not grid or len(grid) != len(manifest['grid'])
                or len(results) != len(report['results']) or set(results) != grid):
            raise ValueError('complete unique registered result grid required')
        for key, result in results.items():
            recorded = db.execute('SELECT status,payload FROM attempts WHERE study=? AND configuration=?',
                                  (study,key)).fetchone()
            if recorded is None or recorded != ('completed',encoded(result)):
                raise ValueError('report result differs from immutable completed attempt')
    finally:
        db.close()
    return {'registered_results_verified':True,'verified_configurations':len(grid),
            'ledger_modified':False,'live_promotion_allowed':False}
