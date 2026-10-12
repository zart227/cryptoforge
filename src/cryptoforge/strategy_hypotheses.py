"""Source-bound descriptions for future experiments, never profit evidence."""
import hashlib,json,inspect
from cryptoforge.strategy_search import signal
from pathlib import Path


def load_hypothesis_catalog(path):
    raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if sha!=path.with_suffix('.sha256').read_text().strip():raise ValueError('hypothesis catalog checksum mismatch')
    catalog=json.loads(raw)
    if catalog.get('schema_version')!='strategy-hypothesis-catalog-v1' or catalog.get('live_promotion_allowed') is not False:
        raise ValueError('research-only hypothesis catalog required')
    if hashlib.sha256(Path(inspect.getfile(signal)).read_bytes()).hexdigest()!=catalog['strategy_source_sha256']:
        raise ValueError('hypothesis description requires review after strategy code changes')
    families=set()
    for row in catalog['hypotheses']:
        if row['family'] in families or not row['entry_conditions'] or not row['expected_failures'] or row['profitability_established'] is not False:
            raise ValueError('unique explicit unqualified strategy hypotheses required')
        families.add(row['family'])
    if families!={'trend','breakout','reversion'}:raise ValueError('existing strategy families must be described explicitly')
    return catalog,sha
