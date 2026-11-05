from copy import deepcopy
from datetime import datetime,UTC
import pytest
from cryptoforge.live_experience import build_live_experiences
from cryptoforge.cash_recovery import build_cash_recovery
from test_live_experience import data


@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('cash',[False,True])
def test_conflicting_original_features_are_never_selected_by_last_row(reverse,cash):
    trades,decisions=data();other=deepcopy(decisions[0])
    other['features']['model_feature_values'][0]=.1
    decisions.extend([other,deepcopy(decisions[0])])
    if reverse:decisions.reverse()
    now=datetime(2026,10,7,6,tzinfo=UTC)
    if cash:
        result=build_cash_recovery(trades,decisions,{},observed_at=now,source_as_of=now,accounting_quality_verified=True)
    else:
        result=build_live_experiences(trades,decisions,observed_at=now,accounting_quality_verified=True)
    assert not result['examples']
    assert result['excluded'][0]['reason']=='conflicting_original_feature_context'


@pytest.mark.parametrize('cash',[False,True])
def test_identical_original_context_duplicates_do_not_remove_valid_outcome(cash):
    trades,decisions=data();decisions.append(deepcopy(decisions[0]))
    now=datetime(2026,10,7,6,tzinfo=UTC)
    if cash:
        result=build_cash_recovery(trades,decisions,{},observed_at=now,source_as_of=now,accounting_quality_verified=True)
    else:
        result=build_live_experiences(trades,decisions,observed_at=now,accounting_quality_verified=True)
    assert len(result['examples'])==1
