"""Replay frozen ablation numerics and masks; never refit or publish."""
from dataclasses import replace
from datetime import datetime
from math import sqrt
from cryptoforge.ablation_study import dependencies
from cryptoforge.net_ablation import AblatedNetRegressor,ablation_description
from cryptoforge.net_regression import NetRegressor,evaluate_net_regressor
from cryptoforge.net_training_snapshot import load_net_training_snapshot
from cryptoforge.research_attempts import identity
from cryptoforge.research_evidence import verify_registered_report
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.train_window import prepare_training_window
from cryptoforge.train_window_audit import audit_train_window_study,_rows,_same
from cryptoforge.training_snapshot import load_runtime_sources


def audit_ablation_study(report, original, *, ledger_path):
    verify_registered_report(report,ledger_path)
    audit_train_window_study(original,ledger_path=ledger_path)
    manifest=report['manifest'];base=manifest['base_config']
    if (manifest['scope']!='viewed_development_leave_features_out'
            or manifest['outer_test_evaluated'] is not False or manifest['feature_selection_performed'] is not False):
        raise ValueError('development-only ablation audit required')
    assert_source_dependencies(manifest['implementation_hashes'],dependencies())
    load_runtime_sources(manifest['original_runtime_sources'],manifest['implementation_hashes'])
    controls=[r for r in original['results'] if r['parameters']==base['control_parameters']]
    if (len(controls)!=1 or manifest['original_study_sha256']!=original['study_sha256']
            or manifest['control_model_sha256']!=identity(controls[0]['model'])
            or manifest['original_input_snapshot']!=original['manifest']['original_input_snapshot']):
        raise ValueError('original ablation control mismatch')
    control=controls[0];target=base['target_version']
    if target!=original['manifest']['base_config']['target_version'] or base['ridge']!=original['manifest']['base_config']['ridge']:
        raise ValueError('ablation target/ridge mismatch')
    snapshot=load_net_training_snapshot(manifest['original_input_snapshot'],target_version=target)
    train,validation=(_rows(snapshot['splits'][name]) for name in ('train','validation'))
    end=datetime.fromisoformat(original['manifest']['train_end'])
    window=prepare_training_window(train,train_end=end,window_days=base['control_parameters']['window_days'],
                                    half_life_days=base['control_parameters']['half_life_days'])
    weights=[weight/sum(window.weights) for weight in window.weights]
    for result in report['results']:
        removed=tuple(result['parameters']['removed_indices']);saved=result['model']
        if (not removed or len(set(removed))!=len(removed) or len(removed)>=7
                or any(type(i) is not int or not 0<=i<7 for i in removed)
                or tuple(saved['removed_indices'])!=removed):raise ValueError('ablation mask mismatch')
        model=AblatedNetRegressor(NetRegressor(**saved['fitted']),removed,saved['target_version'],
            saved['model_family'],saved['live_eligible'])
        if (model.target_version!=target or model.fitted.target_version!=target
                or model.fitted.ridge!=base['ridge'] or model.live_eligible or model.fitted.live_eligible
                or model.model_family!='experimental-ablated-ridge-net-return-v1'
                or model.fitted.model_family!='experimental-ridge-net-return-v1'
                or result['ablation']!=ablation_description(model)):
            raise ValueError('ablation model contract mismatch')
        rows=[replace(row,features=tuple(0. if i in removed else value for i,value in enumerate(row.features))) for row in window.rows]
        if result['train_count']!=len(rows):raise ValueError('ablation train count mismatch')
        means=[sum(w*row.features[i] for w,row in zip(weights,rows)) for i in range(7)]
        stds=[sqrt(sum(w*(row.features[i]-means[i])**2 for w,row in zip(weights,rows))) or 1. for i in range(7)]
        bias=sum(w*row.future_return for w,row in zip(weights,rows))
        if any(len(values)!=7 for values in (model.fitted.means,model.fitted.stds,model.fitted.weights)):
            raise ValueError('seven-feature ablation head required')
        for actual,expected in zip((*model.fitted.means,*model.fitted.stds,model.fitted.bias),(*means,*stds,bias)):_same(actual,expected)
        x=[[(row.features[i]-means[i])/stds[i] for i in range(7)] for row in rows]
        for i in range(7):
            lhs=sum(w*v[i]*sum(c*value for c,value in zip(model.fitted.weights,v)) for w,v in zip(weights,x))+model.fitted.ridge*model.fitted.weights[i]
            rhs=sum(w*v[i]*(row.future_return-bias) for w,v,row in zip(weights,x,rows));_same(lhs,rhs)
        metrics=evaluate_net_regressor(model,validation,target_version=target,
            as_of=datetime.fromisoformat(original['manifest']['validation_end']))
        if metrics['count']!=result['metrics']['count']:raise ValueError('ablation validation count mismatch')
        for name in ('mae','rmse'):
            _same(metrics[name],result['metrics'][name])
            _same(metrics[name]-control['metrics'][name],result[name+'_difference_from_control'])
    if report['original_control_metrics']!=control['metrics']:raise ValueError('ablation control metrics mismatch')
    return {'status':'original_ablation_numerics_verified','audited_configurations':len(report['results']),
        'ledger_records_verified':True,'refitting_performed':False,'archived_code_executed':False,
        'feature_selection_performed':False,'live_promotion_allowed':False,'independent_profitability_established':False}
