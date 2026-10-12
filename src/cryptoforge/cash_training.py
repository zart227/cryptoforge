"""Deterministic, manual-only fit of preregistered cash-recovery candidates."""
from datetime import timedelta
from decimal import Decimal
import hashlib,json,math

from cryptoforge.live_learning_protocol import evaluate_readiness,time,buy_key
from cryptoforge.model_training import TrainingExample,fit_standardizer,fit_logistic_head,predict_probability

FIT_POLICY={'version':'cash-logistic-fit-v1','epochs':100,'learning_rate':0.08,
            'selection':'minimum_validation_log_loss_then_original_l2_order',
            'normalization':'train_only','refit_on_validation':False}
FEATURE_NAMES=['return_1','return_3','range_12','volume_ratio','ema_gap','rsi_14','candle_body']


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()


def validation_diagnostics(rows,probabilities,*,threshold,train_positive_rate):
    if len(rows)!=len(probabilities) or not rows:raise ValueError('paired validation observations required')
    baseline=min(max(train_positive_rate,1e-12),1-1e-12)
    labels=[row['example']['label'] for row in rows]
    baseline_loss=sum(-label*math.log(baseline)-(1-label)*math.log(1-baseline) for label in labels)/len(rows)
    baseline_brier=sum((baseline-label)**2 for label in labels)/len(rows)
    accepted=[row for row,p in zip(rows,probabilities) if p>=threshold]
    rejected=[row for row,p in zip(rows,probabilities) if p<threshold]
    def cohort(values):
        return {'buy_orders':len(values),'cash_recovery_net_sum':str(sum((Decimal(row['cash_recovery_net']) for row in values),Decimal(0))),
                'acquisition_cost_sum':str(sum((Decimal(row['cost']) for row in values),Decimal(0)))}
    bins=[]
    for index in range(5):
        values=[(p,label) for p,label in zip(probabilities,labels) if min(int(p*5),4)==index]
        bins.append({'lower_probability':index/5,'upper_probability':(index+1)/5,'count':len(values),
            'mean_probability':sum(p for p,label in values)/len(values) if values else None,
            'positive_fraction':sum(label for p,label in values)/len(values) if values else None})
    return {'constant_train_rate_baseline':{'positive_rate':train_positive_rate,'log_loss':baseline_loss,'brier':baseline_brier},
        'fixed_threshold_factual_cohorts':{'threshold':threshold,'all':cohort(rows),'accepted':cohort(accepted),'rejected':cohort(rejected)},
        'calibration_bins':bins,'selection_uses_these_diagnostics':False,
        'scope':'observed_buy_cohorts_not_counterfactual_fills_or_shared_capital_portfolio',
        'live_profitability_established':False}


def fit_cash_candidate(protocol,snapshots,*,as_of,source_healthy):
    # No test/paper payload enters readiness, fitting, normalization, or ranking.
    if set(snapshots)-{'train','validation'}:raise ValueError('holdout payload forbidden in cash fitting')
    first_test=time(protocol['windows']['sealed_test']['start'])+timedelta(seconds=protocol['embargo_seconds'])
    if as_of>=first_test:raise ValueError('candidate fitting deadline has passed')
    ready=evaluate_readiness(protocol,snapshots,as_of=as_of,source_healthy=source_healthy,include_training_rows=True)
    selected=ready.pop('_training_rows')
    if not ready['data_ready_for_offline_fit']:raise ValueError('completed qualified train/validation required before fitting')
    budget=protocol['configuration_budget']
    if budget['model_family']!='pure-python-logistic' or len(budget['thresholds'])!=1 or len(budget['l2_values'])>budget['maximum_configurations']:
        raise ValueError('unsupported preregistered fitting budget')
    rows={split:sorted(values,key=lambda row:(time(row['entry_at']),buy_key(row))) for split,values in selected.items()}
    examples={}
    for split,values in rows.items():
        examples[split]=[]
        for row in values:
            cost=Decimal(row['cost']);net=Decimal(row['cash_recovery_net']);label=row['example']['label']
            if not cost.is_finite() or cost<=0 or not net.is_finite() or label!=int(net>0):
                raise ValueError('cash outcome/label/cost mismatch')
            examples[split].append(TrainingExample(row['pair'],time(row['example']['open_time']),
                tuple(float(value) for value in row['example']['features']),label,0,
                float(net/cost),time(row['label_available_at'])))
    means,stds=fit_standardizer([row.features for row in examples['train']]);trials=[]
    for l2 in budget['l2_values']:
        weights,bias=fit_logistic_head(examples['train'],means,stds,learning_rate=FIT_POLICY['learning_rate'],
            epochs=FIT_POLICY['epochs'],label_attr='label',l2=float(l2))
        probabilities=[predict_probability(row.features,weights,bias,means,stds) for row in examples['validation']]
        loss=sum(-row.label*math.log(max(p,1e-12))-(1-row.label)*math.log(max(1-p,1e-12))
                 for row,p in zip(examples['validation'],probabilities))/len(probabilities)
        brier=sum((p-row.label)**2 for row,p in zip(examples['validation'],probabilities))/len(probabilities)
        trials.append({'l2':l2,'validation_log_loss':loss,'validation_brier':brier,'weights':weights,'bias':bias})
    if not all(math.isfinite(value) for trial in trials for value in [trial['validation_log_loss'],trial['validation_brier'],trial['bias'],*trial['weights'],*means,*stds]):
        raise ValueError('nonfinite fitted model or validation metrics')
    winner=min(trials,key=lambda trial:trial['validation_log_loss'])
    provenance={split:{'snapshot_sha256':digest(values),'buy_keys':[buy_key(row) for row in values],
                       'count':len(values)} for split,values in rows.items()}
    artifact={'model_family':'pure-python-logistic','feature_version':protocol['feature_version'],
        'model_version':'cash-recovery-'+digest({'provenance':provenance,'policy':FIT_POLICY,'winner':winner})[:20],
        'trained_at':as_of.isoformat(),'feature_names':FEATURE_NAMES,'means':means,'stds':stds,
        'weights':winner['weights'],'bias':winner['bias'],'selected_l2':winner['l2'],
        'threshold':float(budget['thresholds'][0]),'live_eligible':False,'short_model_available':False,
        'pairs':sorted({row['pair'] for values in rows.values() for row in values}),
        'validation_search':[{k:v for k,v in trial.items() if k not in {'weights','bias'}} for trial in trials],
        'config':{'target_version':protocol['target_version'],'input_candle_state':protocol['input_candle_state'],
            **({'feature_input_contract':protocol['feature_input_contract']} if protocol.get('feature_input_contract') is not None else {}),
            'fit_information_end':max(row.label_end_time for values in examples.values() for row in values).isoformat(),
            'protocol_version':protocol['protocol_version'],'fit_policy':FIT_POLICY,'fit_policy_sha256':digest(FIT_POLICY),
            'training_provenance':provenance,'source':'observed_real_cash_recovery_memory',
            'holdout_used':False,'publication_allowed':False},
        'scope':'real_buy_cohort_classifier_not_counterfactual_portfolio_profit',
        'validation_diagnostics':validation_diagnostics(rows['validation'],
            [predict_probability(row.features,winner['weights'],winner['bias'],means,stds) for row in examples['validation']],
            threshold=float(budget['thresholds'][0]),train_positive_rate=sum(row.label for row in examples['train'])/len(examples['train']))}
    return artifact



def verify_fit_provenance(raw,report,protocol,snapshots,*,as_of,source_healthy):
    """Bind registration to all original trials and the same eligible snapshots."""
    if set(snapshots)-{'train','validation'}:raise ValueError('holdout payload forbidden in fit verification')
    artifact=json.loads(raw)
    if (report.get('artifact_payload')!=raw.decode() or hashlib.sha256(raw).hexdigest()!=report.get('artifact_sha256') or
        report.get('trials')!=artifact.get('validation_search') or report.get('live_promotion_allowed') is not False):
        raise ValueError('candidate does not match original offline fit report')
    ready=evaluate_readiness(protocol,snapshots,as_of=as_of,source_healthy=source_healthy,include_training_rows=True)
    rows=ready.pop('_training_rows')
    if not ready['data_ready_for_offline_fit']:raise ValueError('qualified collection required for fit verification')
    actual={split:{'snapshot_sha256':digest(sorted(values,key=lambda row:(time(row['entry_at']),buy_key(row)))),
                  'buy_keys':[buy_key(row) for row in sorted(values,key=lambda row:(time(row['entry_at']),buy_key(row)))],
                  'count':len(values)} for split,values in rows.items()}
    if artifact['config'].get('training_provenance')!=actual or artifact['config'].get('fit_policy_sha256')!=digest(FIT_POLICY):
        raise ValueError('candidate fitted snapshots or fit policy differ from original study')
    if artifact.get('feature_names')!=FEATURE_NAMES or artifact.get('live_eligible') is not False:
        raise ValueError('unsupported cash candidate schema')
