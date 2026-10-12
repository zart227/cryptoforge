import hashlib,json
from pathlib import Path
import pytest
from cryptoforge.strategy_hypotheses import load_hypothesis_catalog


def test_catalog_describes_existing_unqualified_families_and_does_not_backdate_registration():
    catalog,sha=load_hypothesis_catalog(Path('config/strategy-hypothesis-catalog-v1.json'))
    assert {r['family'] for r in catalog['hypotheses']}=={'trend','breakout','reversion'}
    assert not catalog['preregistered_before_prior_results']
    assert all(r['expected_failures'] and not r['profitability_established'] for r in catalog['hypotheses'])


def test_changed_strategy_binding_is_not_silently_accepted(tmp_path):
    value=json.loads(Path('config/strategy-hypothesis-catalog-v1.json').read_bytes());value['strategy_source_sha256']='0'*64
    path=tmp_path/'catalog.json';raw=json.dumps(value).encode();path.write_bytes(raw)
    path.with_suffix('.sha256').write_text(hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError,match='code changes'):load_hypothesis_catalog(path)
