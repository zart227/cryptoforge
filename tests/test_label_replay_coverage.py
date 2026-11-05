from copy import deepcopy
import pytest
from scripts.replay_label_audit import validate_case_coverage


def report():
    case={'pair':'BTC/USDT','signal_time':'2026-10-01T00:00:00+00:00'}
    return {'pairs':[{'pair':'BTC/USDT','audited_samples':1,
                      'samples':[case], 'sample_source_references':[dict(case)]}]}


def test_repeated_market_group_cannot_double_completed_cases():
    value=report();value['pairs'].append(deepcopy(value['pairs'][0]))
    with pytest.raises(ValueError,match='unique source market'):
        validate_case_coverage(value)


def test_group_identity_is_verified():
    value=report();value['pairs'][0]['pair']='ETH/USDT'
    with pytest.raises(ValueError,match='group identity'):
        validate_case_coverage(value)


@pytest.mark.parametrize('count',[True,0,2])
def test_declared_count_must_be_positive_exact_integer(count):
    value=report();value['pairs'][0]['audited_samples']=count
    with pytest.raises(ValueError,match='coverage'):
        validate_case_coverage(value)


def test_same_timestamp_different_offsets_is_duplicate():
    value=report();group=value['pairs'][0];case=deepcopy(group['samples'][0])
    case['signal_time']='2026-10-01T03:00:00+03:00'
    group['samples'].append(case);group['sample_source_references'].append(dict(case));group['audited_samples']=2
    with pytest.raises(ValueError,match='globally unique'):
        validate_case_coverage(value)


def test_known_case_and_aware_timestamp():
    value=report();assert validate_case_coverage(value)==1
    value['pairs'][0]['samples'][0]['signal_time']='2026-10-01T00:00:00'
    with pytest.raises(ValueError,match='aware'):
        validate_case_coverage(value)
