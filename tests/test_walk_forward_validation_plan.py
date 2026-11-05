from datetime import datetime,UTC
from cryptoforge.walk_forward_schedule import make_schedule
from cryptoforge.walk_forward_validation_plan import validation_manifests
from cryptoforge.trade_labels import TARGET_VERSION
from cryptoforge.net_regression import NET_TARGETS


def manifests():
    calendar=make_schedule(observed_at=datetime(2026,10,14,tzinfo=UTC),first_test_start=datetime(2026,10,16,tzinfo=UTC))
    return validation_manifests(calendar,calendar_sha256='a'*64,base_config={},implementation_hashes={},
        selection_source_hashes={},runtime_source_bundle={},minimum_trades=200,maximum_drawdown=.05)


def test_complete_declared_grid_has_two_heads_and_three_unique_thresholds_per_fold():
    result=manifests()
    assert len(result)==12 and sum(len(item['grid']) for item in result)==36
    for item in result:
        assert {row['threshold'] for row in item['grid']}=={'0.3','0.5','0.7'}
        assert len({row['class_balance'] for row in item['grid']})==1
        assert not item['complete_execution_pipeline_preregistered']


def test_target_is_the_actual_label_producer_contract():
    for item in manifests():
        assert item['training_policy']['target']==TARGET_VERSION
        assert TARGET_VERSION in NET_TARGETS


def test_training_and_validation_use_purged_boundaries_not_test_rewards():
    for item in manifests():
        fold=item['fold'];policy=item['selection_policy']
        assert policy['validation_start']>fold['validation_start']
        assert policy['validation_end']<fold['test_start']
        assert item['training_policy']['train_label_cutoff']<fold['train_end']
        assert item['no_eligible_trial_policy'].startswith('no_candidate')
