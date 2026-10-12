from datetime import UTC,datetime,timedelta
import hashlib,json
import pytest
from cryptoforge.model_registry import ActiveModelRegistry
from cryptoforge.model_training import FEATURE_NAMES

NOW=datetime(2026,10,9,12,tzinfo=UTC)


class Registry(ActiveModelRegistry):
    def __init__(self,row):self.row=row
    def _latest_event(self,**kwargs):return self.row


def event(**changes):
    artifact={'model_family':'pure-python-logistic','model_version':'m1','feature_version':'candle-v1','feature_names':list(FEATURE_NAMES),
        'trained_at':(NOW-timedelta(hours=1)).isoformat(),'weights':[0.]*7,'means':[0.]*7,'stds':[1.]*7,'bias':0.,
        'config':{'fit_information_end':(NOW-timedelta(hours=2)).isoformat()}}
    artifact.update(changes)
    sha=hashlib.sha256(json.dumps(artifact,indent=2,sort_keys=True).encode()).hexdigest()
    return {'occurred_at':NOW.isoformat(),'payload':{'model_version':'m1','feature_version':'candle-v1',
        'artifact':artifact,'artifact_sha256':sha}}


def test_fresh_publication_cannot_refresh_stale_training_or_future_information():
    assert Registry(event()).latest(now=NOW) is not None
    assert Registry(event(trained_at=(NOW-timedelta(days=3)).isoformat())).latest(now=NOW) is None
    with pytest.raises(ValueError,match='future'):Registry(event(trained_at=(NOW+timedelta(minutes=1)).isoformat())).latest(now=NOW)
    with pytest.raises(ValueError,match='unavailable'):Registry(event(config={'fit_information_end':NOW.isoformat()})).latest(now=NOW)
    assert Registry(event(config={'evaluation_information_end':(NOW-timedelta(days=3)).isoformat()})).latest(now=NOW) is None


def test_metadata_version_and_feature_order_are_bound_to_artifact():
    row=event();row['payload']['feature_version']='candle-v2'
    with pytest.raises(ValueError,match='metadata'):Registry(row).latest(now=NOW)
    with pytest.raises(ValueError,match='ordering'):Registry(event(feature_names=list(reversed(FEATURE_NAMES)))).latest(now=NOW)


def test_naive_training_clock_and_future_evaluation_cannot_be_published():
    with pytest.raises(ValueError,match='aware'):Registry(event(trained_at=NOW.replace(tzinfo=None).isoformat())).latest(now=NOW)
    with pytest.raises(ValueError,match='publication'):Registry(event(config={'evaluation_information_end':(NOW+timedelta(minutes=1)).isoformat()})).latest(now=NOW)
    with pytest.raises(ValueError,match='history'):Registry(event(config={'evaluation_history_end':(NOW+timedelta(minutes=1)).isoformat()})).latest_candidate(now=NOW)



def test_research_only_or_wrong_family_artifact_cannot_be_active():
    with pytest.raises(ValueError,match='research-only'):Registry(event(live_eligible=False)).latest(now=NOW)
    with pytest.raises(ValueError,match='family'):Registry(event(model_family='experimental-ridge-net-return-v1')).latest(now=NOW)
    assert Registry(event(live_eligible=False)).latest_candidate(now=NOW) is not None


@pytest.mark.parametrize('target',['spot-long-trade-net-v2','spot-long-real-cash-recovery-dust-zero-v1','unknown-v9',None])
def test_other_target_cannot_enter_primary_registry_even_with_matching_family(target):
    with pytest.raises(ValueError,match='target'):
        Registry(event(config={'target_version':target},live_eligible=True)).latest(now=NOW)
    with pytest.raises(ValueError,match='target'):
        Registry(event(config={'target_version':target},live_eligible=False)).latest_candidate(now=NOW)


def test_cash_source_without_target_is_not_inferred_as_legacy_price():
    with pytest.raises(ValueError,match='migration'):
        Registry(event(config={'source':'observed_real_cash_recovery_memory'})).latest_candidate(now=NOW)


def test_conflicting_root_config_target_declarations_fail():
    with pytest.raises(ValueError,match='disagree'):
        Registry(event(target_version='spot-long-trade-net-v2',config={'target_version':'fixed-future-return-v1'})).latest(now=NOW)


def test_event_target_cannot_override_legacy_price_interpretation():
    row=event();row['payload']['target_version']='spot-long-real-cash-recovery-dust-zero-v1'
    with pytest.raises(ValueError,match='target metadata'):Registry(row).latest(now=NOW)
