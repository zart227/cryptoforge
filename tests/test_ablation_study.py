from cryptoforge.ablation_study import run_registered_ablation
from cryptoforge.train_window_study import run_train_window_study
from cryptoforge.research_evidence import verify_registered_report
from test_train_window_study import examples,options
import pytest


def setup(tmp_path):
    kwargs=options(tmp_path)
    original=run_train_window_study(*examples(),**kwargs)
    return original,dict(control_parameters=original['results'][0]['parameters'],removed_grid=[[0],[1]],
        ledger=kwargs['ledger'],protocol_id='ablation-test',protocol_version='ablation-test-v1',
        maximum_per_family=2)


def test_registered_leave_out_models_keep_original_control_and_cached_results(tmp_path):
    original,kwargs=setup(tmp_path)
    report=run_registered_ablation(original,**kwargs)
    assert report==run_registered_ablation(original,**kwargs)
    assert report['results'][0]['rmse_difference_from_control']>0
    assert report['results'][1]['rmse_difference_from_control']==0
    assert not report['feature_selection_performed']
    assert verify_registered_report(report,kwargs['ledger'].path)['registered_results_verified']
    assert kwargs['ledger'].budget_usage('ablation-test')=={'net-feature-ablation':2}


@pytest.mark.parametrize('grid', [[[0],[0]],[[1,0],[0,1]],[[]],[[True]]])
def test_ambiguous_or_duplicate_feature_subsets_fail(tmp_path,grid):
    original,kwargs=setup(tmp_path);kwargs['removed_grid']=grid
    with pytest.raises(ValueError):run_registered_ablation(original,**kwargs)
    assert kwargs['ledger'].budget_usage('ablation-test')=={}
