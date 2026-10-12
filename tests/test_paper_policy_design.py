from pathlib import Path
import json
import pytest
from cryptoforge.paper_policy_design import validate_execution_design


def policy():return json.loads((Path(__file__).resolve().parents[1]/'config/paper-execution-policy-v1.json').read_bytes())


def test_disabled_draft_is_validated_without_initializing_execution():
    original=policy();config=validate_execution_design(original)
    assert config.max_positions==6 and original['enabled'] is False


@pytest.mark.parametrize('key,value',[('maximum_hold_seconds',0),('maximum_hold_seconds',True),('maximum_hold_seconds',1.5)])
def test_invalid_exit_timing_is_rejected_before_policy_freeze(key,value):
    draft=policy();draft['exits'][key]=value
    with pytest.raises(ValueError,match='integers'):validate_execution_design(draft)


def test_stop_reserve_mismatch_and_expired_polling_are_rejected():
    draft=policy();draft['exits']['stop_fraction']='.05'
    with pytest.raises(ValueError,match='reserve'):validate_execution_design(draft)
    draft=policy();draft['runtime']['poll_seconds']=draft['wallet']['signal_expiry_seconds']
    with pytest.raises(ValueError,match='expiry'):validate_execution_design(draft)
