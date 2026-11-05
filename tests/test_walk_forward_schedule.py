from datetime import datetime,UTC,timedelta,timezone
import pytest
from cryptoforge.walk_forward_schedule import make_schedule

NOW=datetime(2026,10,14,5,tzinfo=UTC)
FIRST=datetime(2026,10,16,tzinfo=UTC)


def test_six_complete_nonoverlapping_future_windows_do_not_claim_outcomes():
    result=make_schedule(observed_at=NOW,first_test_start=FIRST)
    assert len(result['folds'])==6
    for left,right in zip(result['folds'],result['folds'][1:]):
        assert left['test_end']==right['test_start']
    assert result['folds'][0]['test_start']==FIRST.isoformat()
    assert not result['selection_procedure_preregistered']
    assert not result['independent_results_completed']
    assert not result['live_promotion_allowed']


@pytest.mark.parametrize('first',[datetime(2026,10,15,tzinfo=UTC),datetime(2026,10,14,tzinfo=UTC)])
def test_viewed_information_cannot_enter_first_purge_boundary(first):
    with pytest.raises(ValueError,match='purge boundary'):
        make_schedule(observed_at=NOW,first_test_start=first)


def test_local_midnight_cannot_masquerade_as_utc_day_boundary():
    first=FIRST.replace(tzinfo=timezone(timedelta(hours=3)))
    with pytest.raises(ValueError,match='explicitly use UTC'):
        make_schedule(observed_at=NOW,first_test_start=first)


def test_fewer_windows_cannot_lower_independence_requirement():
    with pytest.raises(ValueError,match='at least six'):
        make_schedule(observed_at=NOW,first_test_start=FIRST,minimum_windows=5)
