"""Numerical replay of original window-study inputs without fitting or publication."""
from datetime import datetime
from math import isclose, sqrt

from cryptoforge.model_training import TrainingExample
from cryptoforge.net_regression import NetRegressor, evaluate_net_regressor
from cryptoforge.net_training_snapshot import load_net_training_snapshot
from cryptoforge.research_attempts import identity
from cryptoforge.source_contract import assert_source_dependencies
from cryptoforge.training_snapshot import load_runtime_sources
from cryptoforge.train_window import prepare_training_window
from cryptoforge.train_window_study import window_study_dependencies
from cryptoforge.training_cohorts import net_training_cohorts
from cryptoforge.research_evidence import verify_registered_report


def _rows(values):
    return [TrainingExample(**{**row, 'features':tuple(row['features']),
        'open_time':datetime.fromisoformat(row['open_time']),
        'label_end_time':datetime.fromisoformat(row['label_end_time']) if row['label_end_time'] else None})
        for row in values]


def _same(actual, expected):
    if not isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-12):
        raise ValueError('window study numerical mismatch')


def audit_train_window_study(report, *, ledger_path=None):
    if ledger_path is not None:
        verify_registered_report(report,ledger_path)
    manifest=report['manifest']
    if manifest.get('scope')!='development_net_prediction_error_only' or manifest.get('outer_test_evaluated') is not False:
        raise ValueError('development-only window audit required')
    if identity(manifest)!=report['study_sha256']:
        raise ValueError('window study manifest identity mismatch')
    expected=manifest['implementation_hashes']
    assert_source_dependencies(expected,window_study_dependencies())
    load_runtime_sources(manifest['original_runtime_sources'],expected)
    target=manifest['base_config']['target_version']
    snapshot=load_net_training_snapshot(manifest['original_input_snapshot'],target_version=target)
    train,validation=(_rows(snapshot['splits'][name]) for name in ('train','validation'))
    from dataclasses import asdict
    for name,rows in (('train',train),('validation',validation)):
        if identity([asdict(row) for row in rows])!=manifest[name+'_snapshot_sha256']:
            raise ValueError('original window input identity mismatch')
    grid={identity(candidate):candidate for candidate in manifest['grid']}
    results={identity(result['parameters']):result for result in report['results']}
    if len(grid)!=len(manifest['grid']) or len(results)!=len(report['results']) or set(grid)!=set(results):
        raise ValueError('complete unique window audit grid required')
    for key,candidate in grid.items():
        result=results[key]
        window=prepare_training_window(train,train_end=datetime.fromisoformat(manifest['train_end']),
            window_days=candidate['window_days'],half_life_days=candidate['half_life_days'])
        if (result['train_count']!=len(window.rows)
            or result['training_rows_sha256']!=identity([asdict(row) for row in window.rows])
            or result['sample_weights_sha256']!=identity(window.weights)):
            raise ValueError('original selected training window mismatch')
        _same(result['effective_sample_size'],window.effective_sample_size)
        if result['train_cohorts']!=net_training_cohorts(window.rows,
            as_of=datetime.fromisoformat(manifest['train_end']),target_version=target):
            raise ValueError('training cohort audit mismatch')
        model=NetRegressor(**result['model'])
        if model.target_version!=target or model.ridge!=manifest['base_config']['ridge'] or model.live_eligible:
            raise ValueError('fitted window model contract mismatch')
        weights=[weight/sum(window.weights) for weight in window.weights]
        means=[sum(w*row.features[i] for w,row in zip(weights,window.rows)) for i in range(7)]
        stds=[sqrt(sum(w*(row.features[i]-means[i])**2 for w,row in zip(weights,window.rows))) or 1. for i in range(7)]
        bias=sum(w*row.future_return for w,row in zip(weights,window.rows))
        if len(model.means)!=7 or len(model.stds)!=7 or len(model.weights)!=7:
            raise ValueError('seven-feature audited model required')
        for actual,reference in zip((*model.means,*model.stds,model.bias),(*means,*stds,bias)):
            _same(actual,reference)
        x=[[(row.features[i]-means[i])/stds[i] for i in range(7)] for row in window.rows]
        # Verify ridge first-order equations independently; never solve/refit.
        for i in range(7):
            lhs=sum(w*values[i]*sum(coef*value for coef,value in zip(model.weights,values))
                    for w,values in zip(weights,x))+model.ridge*model.weights[i]
            rhs=sum(w*values[i]*(row.future_return-bias) for w,values,row in zip(weights,x,window.rows))
            _same(lhs,rhs)
        metrics=evaluate_net_regressor(model,validation,target_version=target,
            as_of=datetime.fromisoformat(manifest['validation_end']))
        for name in ('mae','rmse'):_same(metrics[name],result['metrics'][name])
        if metrics['count']!=result['metrics']['count']:
            raise ValueError('validation audit count mismatch')
    if report['validation_cohorts']!=net_training_cohorts(validation,
        as_of=datetime.fromisoformat(manifest['validation_end']),target_version=target):
        raise ValueError('validation cohort audit mismatch')
    return {'status':'original_window_numerics_verified','audited_configurations':len(grid),
            'refitting_performed':False,'archived_code_executed':False,
            'ledger_authenticity_verified':ledger_path is not None,'live_promotion_allowed':False,
            'independent_profitability_established':False}
