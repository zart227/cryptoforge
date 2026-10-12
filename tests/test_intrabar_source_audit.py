from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import json
from pathlib import Path
import pytest
from cryptoforge.closed_timeframes import aggregate_closed
from cryptoforge.intrabar_source_audit import compare_intrabar_source
from test_intrabar_audit import rows,START


def run(fine,coarse=None):
    now=START+timedelta(minutes=10)
    if coarse is None:coarse=aggregate_closed(rows(),as_of=now,minutes=5,base_minutes=1)[0]
    protocol=json.loads((Path(__file__).resolve().parents[1]/'config/research-protocol-v1.json').read_text())
    return compare_intrabar_source(fine,coarse,protocol=protocol,as_of=now)


def test_exact_source_pass_and_mismatch_fail_are_not_execution_certification():
    result=run(rows())
    assert result['source_consistency_pass'] and not result['real_fill_certified']
    changed=rows();changed[1]=replace(changed[1],volume=D(21))
    result=run(changed)
    assert not result['source_consistency_pass'] and not result['checks'][0]['volume_matches']


@pytest.mark.parametrize('fine',[rows()[:-1],rows()[1:],rows()[:2]+rows()[3:],list(reversed(rows()))])
def test_incomplete_or_disordered_minute_range_is_rejected(fine):
    with pytest.raises(ValueError):run(fine)


def test_missing_coarse_bar_is_rejected():
    with pytest.raises(ValueError,match='coarse source'):run(rows(),[])
