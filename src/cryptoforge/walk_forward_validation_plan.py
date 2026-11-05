"""Declared validation-only head/threshold studies, distinct from executed folds."""
from datetime import datetime,timedelta
from cryptoforge.trade_labels import TARGET_VERSION


def validation_manifests(calendar,*,calendar_sha256,base_config,implementation_hashes,
                         selection_source_hashes,runtime_source_bundle,minimum_trades,maximum_drawdown):
    result=[]
    if len(calendar['folds'])!=6:raise ValueError('original six-fold calendar required')
    for index,fold in enumerate(calendar['folds']):
        embargo=timedelta(seconds=fold['embargo'])
        start=datetime.fromisoformat(fold['validation_start'])+embargo
        end=datetime.fromisoformat(fold['validation_end'])-embargo
        if start>=end:raise ValueError('nonempty purged validation window required')
        for balanced in (False,True):
            result.append({'scope':'validation_threshold_selection','calendar_sha256':calendar_sha256,
                'fold_index':index,'fold':fold,'base_config':base_config,
                'grid':[{'family':'net-class-balance','class_balance':balanced,'threshold':threshold,'fold_index':index}
                        for threshold in ('0.3','0.5','0.7')],
                'selection_policy':{'validation_start':start.isoformat(),'validation_end':end.isoformat(),
                    'minimum_trades':minimum_trades,'maximum_drawdown':maximum_drawdown},
                'training_policy':{'class_balance':balanced,'epochs':100,'learning_rate':.05,'l2':.001,
                    'train_label_cutoff':(datetime.fromisoformat(fold['train_end'])-embargo).isoformat(),
                    'preprocessing':'train_only','feature_source':'original offline trade-label builder',
                    'target':TARGET_VERSION,'changing_design_after_test_is_forbidden':True},
                'controls':['native_closed_bounded120_without_ML','cash_only'],
                'legacy_current_model_control_status':'unknown_feature_contract_not_reconstructed',
                'implementation_hashes':implementation_hashes,'selection_source_hashes':selection_source_hashes,
                'runtime_source_bundle':runtime_source_bundle,
                'no_eligible_trial_policy':'no_candidate_cash_only_no_forced_winner',
                'ranking':'stress_return_then_net_return_then_higher_threshold',
                'complete_execution_pipeline_preregistered':False,
                'historical_execution_rules_certified':False,'live_promotion_allowed':False})
    return result
